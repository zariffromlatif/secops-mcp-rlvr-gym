from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def seed_db():
    sql = (ROOT / "seed.sql").read_text()
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def as_tenant(tenant):
    return {"X-Tenant-ID": str(tenant)}


def status_of(invoice_id):
    with engine.connect() as conn:
        return conn.exec_driver_sql(
            "SELECT status FROM invoices WHERE id = %(id)s", {"id": invoice_id}
        ).scalar_one()
