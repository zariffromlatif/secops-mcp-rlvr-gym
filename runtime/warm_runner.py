"""Processes inside the warm sandbox's containers (see warm_sandbox.py). Standard library only at
the top: each mode imports what it needs.

    app     import the web stack, wait for the agent's code (/work/READY), then serve /work/app
            exactly like `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` in /work
    serve   the test runner: import the test stack once, then fork a fresh process per pytest
            target, so no state carries from one target or episode to the next
    client  send one job (JSON on stdin) to the test runner and print its reply
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time

SOCKET = "/tmp/runner.sock"


def app() -> None:
    import fastapi  # noqa: F401  the slow imports happen before the code arrives
    import psycopg  # noqa: F401
    import pydantic  # noqa: F401
    import sqlalchemy.dialects.postgresql.psycopg  # noqa: F401
    import uvicorn

    while not os.path.exists("/work/READY"):
        time.sleep(0.01)
    os.chdir("/work")
    sys.path.insert(0, "/work")  # what `python -m` does with the working directory
    uvicorn.main(["app.main:app", "--host", "0.0.0.0", "--port", "8000"])


def _read(conn: socket.socket) -> bytes:
    chunks = []
    while chunk := conn.recv(65536):
        chunks.append(chunk)
    return b"".join(chunks)


def _run(job: dict, inherited: list[socket.socket]) -> dict:
    """Each target in its own forked process, like one `python -m pytest` per target."""
    import pytest

    deadline = time.monotonic() + job["timeout"]
    codes = []
    for i, target in enumerate(job["targets"]):
        pid = os.fork()
        if pid == 0:
            os.setpgid(0, 0)
            for s in inherited:
                s.close()
            os.chdir(job["dir"])
            sys.path.insert(0, job["dir"])
            os.environ.update(job["env"])
            log = os.open(f"{job['dir']}/results/{i}.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.dup2(log, 1)
            os.dup2(log, 2)
            # The filter drops pytest's note that anyio, imported in advance by serve(), was not
            # assert-rewritten; otherwise the run is `python -m pytest` as in sandbox.run_episode.
            code = pytest.main(["-q", "-p", "no:cacheprovider", "--timeout=60",
                                "-W", "ignore::pytest.PytestAssertRewriteWarning",
                                f"--junitxml={job['dir']}/results/{i}.xml", target])
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(int(code))
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                codes.append(os.waitstatus_to_exitcode(status))
                break
            if time.monotonic() > deadline:
                os.killpg(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                return {"finished": False, "codes": codes}
            time.sleep(0.005)
    return {"finished": True, "codes": codes}


def serve() -> None:
    # Everything the tests import, loaded once. Not the pytest plugins themselves (pytest_timeout,
    # anyio.pytest_plugin): pytest wants to import those itself, to rewrite their asserts.
    import anyio._backends._asyncio  # noqa: F401  what anyio's plugin spends most of its import on
    import httpx  # noqa: F401
    import psycopg  # noqa: F401
    import pytest  # noqa: F401
    import sqlalchemy.dialects.postgresql.psycopg  # noqa: F401
    from _pytest import junitxml  # noqa: F401

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET)
    server.listen(1)
    while True:
        conn, _ = server.accept()
        with conn:
            reply = _run(json.loads(_read(conn)), [server, conn])
            conn.sendall(json.dumps(reply).encode())


def client() -> None:
    job = sys.stdin.read().encode()
    for _ in range(600):  # the runner may still be importing
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            conn.connect(SOCKET)
            break
        except (FileNotFoundError, ConnectionRefusedError):
            conn.close()
            time.sleep(0.05)
    else:
        raise SystemExit("test runner did not start")
    conn.sendall(job)
    conn.shutdown(socket.SHUT_WR)
    print(_read(conn).decode())


if __name__ == "__main__":
    {"app": app, "serve": serve, "client": client}[sys.argv[1]]()
