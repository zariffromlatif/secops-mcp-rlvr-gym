"""The scoring sandbox with its slow parts kept warm: same isolation as sandbox.run_episode, a
fraction of the time per episode. Used by `--sandbox warm`.

Kept warm in a pool (one pool per concurrent episode):

    network  internal, no internet
    db       Postgres on tmpfs. Every episode gets its own database and its own row-only role,
             with random passwords, and nobody else may connect to that database. Both are
             dropped after the episode.
    test     the test runner (warm_runner.py serve): imports the test libraries once, then forks
             a fresh process per pytest target. It only ever runs the task's own tests.

New for every episode:

    app      the agent's code, in a fresh locked-down container (sandbox.LOCKDOWN). It is started
             one episode ahead with the web stack imported, waits for the code, and is removed
             before the next episode's code is let in, so two agents' code never run side by side.

A pool is rebuilt after RECYCLE episodes, a timeout or any error; an episode that fails for an
infrastructure reason is retried once on a fresh pool. Pools are removed at exit, and pools left
by dead processes are removed when a new one starts.
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import secrets
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from sandbox import DB_IMAGE, LOCKDOWN, _bind, _docker, _wait_for_db, app_grants, parse_junit, psql, sandbox_image

RUNTIME = Path(__file__).resolve().parent
TMP_ROOT = RUNTIME.parent / ".tmp"
LABEL = "secops-gym.warm-pool"
RUNNER = "/runner/warm_runner.py"
RECYCLE = 200


@dataclass
class Slot:
    """An app container started ahead of its episode, with the episode's database and role."""

    name: str
    folder: Path  # mounted read-only at /work in the app container
    database: str
    role: str
    owner_url: str  # for the tests only


class WarmPool:
    def __init__(self) -> None:
        self.id = f"gymw-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.labels = ("--label", f"{LABEL}={os.getpid()}")
        self.net, self.db, self.test = self.id, f"{self.id}-db", f"{self.id}-test"
        self.root = TMP_ROOT / self.id
        self.owner = secrets.token_hex(16)
        self.episodes, self.broken = 0, False
        self.background = ThreadPoolExecutor(1)
        self.next: Future | None = None
        self.image = sandbox_image()
        try:
            self._start()
        except BaseException:
            self.close()
            raise

    def _start(self) -> None:
        (self.root / "apps").mkdir(parents=True)
        (self.root / "tests").mkdir()
        os.chmod(self.root / "tests", 0o777)  # the runner (uid 1000) writes reports there
        runner = _bind(RUNTIME / "warm_runner.py", RUNNER)
        _docker("network", "create", "--internal", *self.labels, self.net)
        _docker(
            "run", "-d", "--name", self.db, *self.labels, "--network", self.net, "--network-alias", "db",
            "--tmpfs", "/var/lib/postgresql/data",
            "-e", "POSTGRES_USER=gym", "-e", f"POSTGRES_PASSWORD={self.owner}", "-e", "POSTGRES_DB=gym",
            DB_IMAGE,
        )
        _docker(
            "run", "-d", "--name", self.test, *self.labels, "--network", self.net, *LOCKDOWN, *runner,
            *_bind(self.root / "tests", "/episodes", readonly=False),
            self.image, "python", RUNNER, "serve",
        )
        _wait_for_db(self.db)
        psql(self.db, "gym", *(f"REVOKE CONNECT ON DATABASE {d} FROM PUBLIC" for d in ("gym", "postgres", "template1")))
        self.next = self.background.submit(self._prepare)

    def _prepare(self) -> Slot:
        tag = uuid.uuid4().hex[:12]
        name, database, role, password = f"{self.id}-app-{tag}", f"ep_{tag}", f"app_{tag}", secrets.token_hex(16)
        psql(self.db, "gym",
             f"CREATE ROLE {role} LOGIN PASSWORD '{password}'", f"CREATE DATABASE {database}",
             f"REVOKE CONNECT ON DATABASE {database} FROM PUBLIC", f"GRANT CONNECT ON DATABASE {database} TO {role}",
             f"\\connect {database}", *app_grants(role))
        folder = self.root / "apps" / tag
        folder.mkdir()
        _docker(
            "run", "-d", "--name", name, *self.labels, "--network", self.net, *LOCKDOWN,
            *_bind(folder, "/work"), *_bind(RUNTIME / "warm_runner.py", RUNNER),
            "-e", f"DATABASE_URL=postgresql+psycopg://{role}:{password}@db:5432/{database}",
            self.image, "python", RUNNER, "app",
        )
        return Slot(name, folder, database, role, f"postgresql+psycopg://gym:{self.owner}@db:5432/{database}")

    def _drop(self, slot: Slot, tests: Path) -> None:
        try:
            psql(self.db, "gym", f"DROP DATABASE IF EXISTS {slot.database} WITH (FORCE)", f"DROP ROLE IF EXISTS {slot.role}")
        except Exception:
            self.broken = True
        shutil.rmtree(slot.folder, ignore_errors=True)
        shutil.rmtree(tests, ignore_errors=True)

    def run(self, workdir: Path, targets: list[str], timeout: float) -> list[tuple[int, int]]:
        slot, self.next = self.next.result(), None
        tests = self.root / "tests" / slot.folder.name
        try:
            # Tests first, in a folder only the runner sees; then the code; then the go signal.
            # Symlinks stay links, resolved inside the container as with the cold sandbox's bind
            # mount: a patch that links app/x to a host file must not get the file's contents.
            (tests / "results").mkdir(parents=True)
            for folder in (tests, tests / "results"):
                os.chmod(folder, 0o777)
            shutil.copy2(workdir / "seed.sql", tests / "seed.sql")
            for folder in sorted({t.split("/")[0] for t in targets}):
                shutil.copytree(workdir / folder, tests / folder, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(workdir / "app", slot.folder / "app", symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
            (slot.folder / "READY").touch()
            self.next = self.background.submit(self._prepare)

            job = {"dir": f"/episodes/{tests.name}", "targets": targets, "timeout": timeout,
                   "env": {"DATABASE_URL": slot.owner_url, "APP_URL": f"http://{slot.name}:8000"}}
            try:
                done = _docker("exec", "-i", self.test, "python", RUNNER, "client",
                               input=json.dumps(job), timeout=timeout + 60, check=False)
            except subprocess.TimeoutExpired:  # the runner's own deadline failed: as in the cold sandbox
                self.broken = True
                return [(0, 1)] * len(targets)
            if done.returncode != 0:
                raise RuntimeError(f"test runner failed: {done.stderr.strip()[-500:]}")
            if not json.loads(done.stdout)["finished"]:
                self.broken = True  # a runaway test process: start over with a fresh pool
                return [(0, 1)] * len(targets)
            return [parse_junit(tests / "results" / f"{i}.xml") for i in range(len(targets))]
        finally:
            _docker("rm", "-f", slot.name, check=False)  # gone before the next code is let in
            self.background.submit(self._drop, slot, tests)
            self.episodes += 1

    def close(self) -> None:
        self.background.shutdown(wait=True, cancel_futures=True)
        names = _docker("ps", "-aq", "--filter", f"name={self.id}", check=False).stdout.split()
        if names:
            _docker("rm", "-f", *names, check=False)
        _docker("network", "rm", self.net, check=False)
        shutil.rmtree(self.root, ignore_errors=True)


_free: queue.SimpleQueue[WarmPool] = queue.SimpleQueue()
_all: list[WarmPool] = []
_lock = threading.Lock()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_stale_pools() -> None:
    """Containers and networks of pools whose process is gone (killed, crashed)."""
    fmt = f'{{{{.ID}}}} {{{{.Label "{LABEL}"}}}}'
    for ls, rm in ((("container", "ls", "-a"), ("container", "rm", "-f")), (("network", "ls"), ("network", "rm"))):
        listing = _docker(*ls, "--filter", f"label={LABEL}", "--format", fmt, check=False).stdout.splitlines()
        stale = [line.split()[0] for line in listing if len(line.split()) == 2 and not _alive(int(line.split()[1]))]
        if stale:
            _docker(*rm, *stale, check=False)


def _new_pool() -> WarmPool:
    with _lock:
        if not _all:
            remove_stale_pools()
    pool = WarmPool()
    with _lock:
        _all.append(pool)
    return pool


def _retire(pool: WarmPool) -> None:
    with _lock:
        if pool in _all:
            _all.remove(pool)
    pool.close()


@atexit.register
def close_all() -> None:
    for pool in list(_all):
        _retire(pool)


def run_episode_warm(workdir: Path, targets: list[str], test_timeout: float = 300) -> list[tuple[int, int]]:
    """sandbox.run_episode on a warm pool; safe to call from several threads at once."""
    for attempt in range(2):
        try:
            pool = _free.get_nowait()
        except queue.Empty:
            pool = _new_pool()
        try:
            counts = pool.run(workdir, targets, test_timeout)
        except Exception:
            _retire(pool)
            if attempt:
                raise
            continue
        if pool.broken or pool.episodes >= RECYCLE:
            _retire(pool)
        else:
            _free.put(pool)
        return counts
    raise AssertionError("unreachable")
