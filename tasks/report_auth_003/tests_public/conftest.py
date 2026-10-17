from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

TENANT_1 = {"X-API-Key": "key-tenant-1-live"}
TENANT_2 = {"X-API-Key": "key-tenant-2-live"}
REVOKED = {"X-API-Key": "key-tenant-1-revoked"}


@pytest.fixture(scope="session", autouse=True)
def seed_db():
    sql = (ROOT / "seed.sql").read_text()
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)
