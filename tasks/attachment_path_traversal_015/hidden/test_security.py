"""Names must never reach outside the tenant's own folder (CWE-22)."""

import pytest

from conftest import read


@pytest.mark.parametrize("name", ["../2/contract.txt", "receipts/../../2/contract.txt", "./../2/contract.txt"])
def test_cannot_read_another_tenants_file(client, name):
    r = read(client, 1, name)
    assert r.status_code == 404 and "Confidential" not in r.text


@pytest.mark.parametrize("name", ["../../main.py", "../../db.py"])
def test_cannot_read_the_service_code(client, name):
    r = read(client, 1, name)
    assert r.status_code == 404 and "import" not in r.text


def test_absolute_path_is_404(client):
    r = read(client, 1, "/etc/passwd")
    assert r.status_code == 404 and "root:" not in r.text
