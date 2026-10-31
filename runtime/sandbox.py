"""Run one scoring episode in isolated Docker containers.

Each episode gets its own internal network (no internet) with three containers:

    db    postgres, data on tmpfs, fresh every episode
    app   the agent's (patched) code served by uvicorn, read-only mount; its database role
          may only read and write rows (no DDL, no superuser)
    test  public + hidden tests, talking to `app` over HTTP

The agent's code never runs inside the test process, so it cannot tamper with
test results. The database owner the tests use is a superuser, so its password is random per
episode: the agent's code can reach the database host but cannot log in as the owner. Everything
is removed afterwards, even on errors or Ctrl+C.

run_episode(..., warm=True) gives the same isolation with the network, Postgres and test runner
kept warm between episodes (warm_sandbox.py).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent
DB_IMAGE = "postgres:16-alpine"
# local: tests import the app in-process (fast, not isolated); docker: a fresh sandbox per episode;
# warm: the same sandbox with the network, Postgres and test runner reused (warm_sandbox.py)
SANDBOXES = ("local", "docker", "warm")


def app_grants(role: str) -> list[str]:
    """Rows only: tables and sequences the owner creates are readable and writable, nothing else."""
    return [
        f"ALTER DEFAULT PRIVILEGES FOR ROLE gym IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}",
        f"ALTER DEFAULT PRIVILEGES FOR ROLE gym IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}",
    ]

LOCKDOWN = [
    "--read-only",
    "--tmpfs", "/tmp:size=64m",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--pids-limit", "128",
    "--memory", "512m",
    "--cpus", "1",
    "--user", "1000:1000",
]


def _docker(*args: str, timeout: float = 120, check: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=check, input=input
    )


def psql(container: str, database: str, *statements: str) -> None:
    """Run statements one by one as the owner, over the container's local socket."""
    args = [arg for statement in statements for arg in ("-c", statement)]
    _docker("exec", container, "psql", "-U", "gym", "-d", database, "-q", "-v", "ON_ERROR_STOP=1", *args)


def sandbox_image() -> str:
    """Image tag derived from the Dockerfile + pinned deps; built on first use."""
    digest = hashlib.sha256()
    for name in ("Dockerfile.sandbox", "requirements-sandbox.txt"):
        digest.update((RUNTIME / name).read_bytes())
    tag = f"secops-gym-sandbox:{digest.hexdigest()[:12]}"
    if _docker("image", "inspect", tag, check=False).returncode != 0:
        _docker("build", "-q", "-f", str(RUNTIME / "Dockerfile.sandbox"), "-t", tag, str(RUNTIME), timeout=900)
    return tag


def _bind(source: Path, target: str, readonly: bool = True) -> list[str]:
    spec = f"type=bind,source={source},target={target}"
    return ["--mount", spec + (",readonly" if readonly else "")]


def parse_junit(report: Path) -> tuple[int, int]:
    if not report.exists():
        return 0, 1
    suite = ET.parse(report).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    total = int(suite.get("tests", 0))
    failed = sum(int(suite.get(k, 0)) for k in ("failures", "errors", "skipped"))
    return total - failed, max(total, 1)


def _wait_for_db(name: str, deadline_s: float = 30) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if _docker("exec", name, "pg_isready", "-U", "gym", "-h", "127.0.0.1", check=False).returncode == 0:
            return
        time.sleep(0.3)
    raise RuntimeError("database did not become ready")


def start_db(net: str, name: str, labels: tuple[str, ...] = ()) -> tuple[str, str]:
    """Postgres on `net` (alias `db`). Returns the owner's URL (tests) and a row-only URL (the app)."""
    owner, app = secrets.token_hex(16), secrets.token_hex(16)
    _docker(
        "run", "-d", "--name", name, *labels, "--network", net, "--network-alias", "db",
        "--tmpfs", "/var/lib/postgresql/data",
        "-e", "POSTGRES_USER=gym", "-e", f"POSTGRES_PASSWORD={owner}", "-e", "POSTGRES_DB=gym",
        DB_IMAGE,
    )
    _wait_for_db(name)
    psql(name, "gym", f"CREATE ROLE app LOGIN PASSWORD '{app}'", *app_grants("app"))
    return f"postgresql+psycopg://gym:{owner}@db:5432/gym", f"postgresql+psycopg://app:{app}@db:5432/gym"


def run_episode(workdir: Path, targets: list[str], test_timeout: float = 300, warm: bool = False) -> list[tuple[int, int]]:
    """Serve workdir/app and run each pytest target against it. Returns (passed, total) per target."""
    if warm:
        from warm_sandbox import run_episode_warm

        return run_episode_warm(workdir, targets, test_timeout)
    image = sandbox_image()
    run_id = f"gym-{uuid.uuid4().hex[:10]}"
    net, db, app, test = run_id, f"{run_id}-db", f"{run_id}-app", f"{run_id}-test"
    results = workdir / "results"
    results.mkdir(exist_ok=True)
    os.chmod(results, 0o777)  # container user 1000 must be able to write reports on Linux hosts

    try:
        _docker("network", "create", "--internal", net)
        owner_url, app_url = start_db(net, db)

        _docker(
            "run", "-d", "--name", app, "--network", net, "--network-alias", "app",
            *LOCKDOWN,
            *_bind(workdir / "app", "/work/app"),
            "-e", f"DATABASE_URL={app_url}",
            image, "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",
        )

        commands = [
            f"python -m pytest -q -p no:cacheprovider --timeout=60 --junitxml=/results/{i}.xml {target}"
            for i, target in enumerate(targets)
        ]
        mounts = _bind(workdir / "seed.sql", "/work/seed.sql") + _bind(results, "/results", readonly=False)
        for folder in {t.split("/")[0] for t in targets}:
            mounts += _bind(workdir / folder, f"/work/{folder}")
        _docker(
            "run", "--name", test, "--network", net,
            *LOCKDOWN,
            *mounts,
            "-e", f"DATABASE_URL={owner_url}", "-e", "APP_URL=http://app:8000",
            image, "sh", "-c", " ; ".join(commands),
            timeout=test_timeout, check=False,
        )
        return [parse_junit(results / f"{i}.xml") for i in range(len(targets))]
    except subprocess.TimeoutExpired:
        return [(0, 1)] * len(targets)
    finally:
        _docker("rm", "-f", test, app, db, check=False)
        _docker("network", "rm", net, check=False)
