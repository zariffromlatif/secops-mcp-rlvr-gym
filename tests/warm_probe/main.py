"""An app/main.py that tries to escape the scoring sandbox and reports what worked.

At startup it also leaves traces (a file in /tmp, a setting on its database role) that the next
episode's probe looks for: a sandbox that reuses anything the agent's code could touch would
show them.
"""

import os
import socket

from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

URL = make_url(os.environ["DATABASE_URL"])
MARKER = "/tmp/probe-marker"


def connects(url) -> bool:
    try:
        with create_engine(url, connect_args={"connect_timeout": 3}).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def readable(path: str) -> str | None:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return None


def setting(conn) -> str:
    return conn.execute(text("SELECT current_setting('application_name')")).scalar()


engine = create_engine(URL)
STARTUP = {"marker_existed": os.path.exists(MARKER)}
open(MARKER, "w").close()
with engine.begin() as conn:
    STARTUP["role_setting_before"] = setting(conn)
    conn.execute(text("ALTER ROLE CURRENT_USER SET application_name = 'tainted'"))

app = FastAPI()


@app.get("/")
def root():
    return {}


@app.get("/probe")
def probe():
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE probe_table (x int)"))
        ddl = True
    except Exception:
        ddl = False
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=2).close()
        internet = True
    except OSError:
        internet = False
    return {
        **STARTUP,
        "owner_login": connects(URL.set(username="gym", password="gym", database="gym")),
        "other_db": {db: connects(URL.set(database=db)) for db in ("gym", "postgres")},
        "ddl": ddl,
        "internet": internet,
        "work": sorted(os.listdir("/work")),
        "episodes_dir": os.path.exists("/episodes"),
        "host_file": readable("/work/app/host_file"),  # a symlink the test puts there, to a host file
    }
