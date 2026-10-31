"""Copied in as hidden/test_probe_pool.py, warm sandbox only: one Postgres holds every episode's
database, so no other may be reachable."""

import pytest


@pytest.fixture(scope="module")
def found(client):
    return client.get("/probe").json()


def test_other_databases_refused(found):
    assert found["other_db"] == {"gym": False, "postgres": False}
