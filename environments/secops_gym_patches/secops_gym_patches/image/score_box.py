"""In-box scorer, run as root after the agent has finished.

    python /opt/gym/score_box.py /opt/gym/task/spec.json

spec.json: {"regression": [targets], "security": [targets],
            "originals": {"tests_public/...": text, "seed.sql": text}}
Hidden tests must already be at /opt/gym/task/hidden/.

The agent's processes are killed first. Its app/ is copied to a scratch dir and
served by uvicorn as `nobody`, against a fresh database the agent never touched,
through a role that may only read and write rows. pytest runs as root against it
over HTTP using pristine copies of the tests and seed data, and writes its
reports to a root-only directory, so neither edited tests, leftover processes,
database changes nor in-process tricks in the app can change the results.
Prints one JSON line.
"""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path("/app")
WORK = Path("/srv/gymwork")
HIDDEN = Path("/opt/gym/task/hidden")
REPORTS = Path("/opt/gym/reports")  # root-only: the app runs while tests write their reports
DB = "gymscore"


def junit(report: Path) -> tuple[int, int]:
    if not report.exists():
        return 0, 1
    suite = ET.parse(report).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    total = int(suite.get("tests", 0))
    failed = sum(int(suite.get(k, 0)) for k in ("failures", "errors", "skipped"))
    return total - failed, max(total, 1)


def wait_for_app(deadline_s: float = 20) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1)
            return
        except urllib.error.HTTPError:
            return  # any HTTP response means the server is up
        except Exception:
            time.sleep(0.3)


def psql(database: str, sql: str) -> None:
    subprocess.run(
        ["su", "postgres", "-s", "/bin/sh", "-c", f"psql -p 5433 -d {database} -q -v ON_ERROR_STOP=1"],
        input=sql, text=True, check=True, stdout=subprocess.DEVNULL,
    )


def fresh_database() -> tuple[str, str]:
    """Create a database the agent never touched. Returns (owner URL for tests, row-only URL for the app)."""
    owner, app = secrets.token_hex(16), secrets.token_hex(16)
    psql("postgres", f"""
        SET client_min_messages = warning;
        DROP DATABASE IF EXISTS {DB} WITH (FORCE);
        DROP ROLE IF EXISTS {DB}_app;
        DROP ROLE IF EXISTS {DB};
        CREATE ROLE {DB} LOGIN PASSWORD '{owner}';
        CREATE ROLE {DB}_app LOGIN PASSWORD '{app}';
        CREATE DATABASE {DB} OWNER {DB};
    """)
    # The tests create the tables (seed.sql) as the owner; the app may only use their rows.
    psql(DB, f"""
        ALTER DEFAULT PRIVILEGES FOR ROLE {DB} IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {DB}_app;
        ALTER DEFAULT PRIVILEGES FOR ROLE {DB} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {DB}_app;
    """)
    url = "postgresql+psycopg://{}:{}@127.0.0.1:5433/" + DB
    return url.format(DB, owner), url.format(f"{DB}_app", app)


def main(spec_path: str) -> None:
    spec = json.loads(Path(spec_path).read_text())
    originals = spec["originals"]

    # The agent is done: nothing it left running may serve on the app's port or touch scoring files.
    for user in ("agent", "nobody"):
        subprocess.run(["pkill", "-KILL", "-u", user], check=False)

    agent_tests = {
        p.relative_to(APP).as_posix(): p.read_text(errors="replace")
        for p in (APP / "tests_public").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    expected_tests = {k: v for k, v in originals.items() if k.startswith("tests_public/")}
    tests_modified = sorted(
        {k for k in expected_tests if agent_tests.get(k) != expected_tests[k]}
        | {k for k in agent_tests if k not in expected_tests and k.endswith(".py")}
    )

    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    if (APP / "app").is_dir():
        shutil.copytree(APP / "app", WORK / "app", ignore=shutil.ignore_patterns("__pycache__"))
    else:
        (WORK / "app").mkdir()
    for rel, text in originals.items():
        target = WORK / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    shutil.copytree(HIDDEN, WORK / "hidden")

    app_files = {
        p.relative_to(WORK).as_posix(): p.read_text(errors="replace")
        for p in (WORK / "app").rglob("*.py")
    }

    # The app process may read app/ only; tests, seed and hidden checks stay root-only.
    os.chmod(WORK, 0o755)
    for root, dirs, files in os.walk(WORK / "app"):
        os.chmod(root, 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)
    for name in ("hidden", "tests_public"):
        os.chmod(WORK / name, 0o700)
    os.chmod(WORK / "seed.sql", 0o600)

    subprocess.run(["sh", "/opt/gym/start_db.sh"], check=True)
    owner_url, app_url = fresh_database()
    shutil.rmtree(REPORTS, ignore_errors=True)
    REPORTS.mkdir(mode=0o700, parents=True)
    env = {k: v for k, v in os.environ.items() if k not in {"APP_URL", "DATABASE_URL"}}
    env.update(PYTHONDONTWRITEBYTECODE="1")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=WORK, env={**env, "DATABASE_URL": app_url}, user="nobody", group="nobody",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    results = {}
    try:
        wait_for_app()
        serving = server.poll() is None  # our uvicorn, not whatever else answered on the port
        for group in ("regression", "security"):
            passed = total = 0
            for i, target in enumerate(spec[group]):
                report = REPORTS / f"{group}-{i}.xml"
                if serving:
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                             "--timeout=60", f"--junitxml={report}", target],
                            cwd=WORK, env={**env, "DATABASE_URL": owner_url, "APP_URL": "http://127.0.0.1:8000"},
                            capture_output=True, timeout=300,
                        )
                    except subprocess.TimeoutExpired:
                        pass
                p, t = junit(report)
                passed, total = passed + p, total + t
            results[group] = [passed, total]
    finally:
        server.kill()
        subprocess.run(["pkill", "-u", "nobody"], check=False)

    print(json.dumps({"tests_modified": tests_modified, "app_files": app_files, **results}))


if __name__ == "__main__":
    main(sys.argv[1])
