from conftest import TENANT_1, TENANT_2


def test_summary_requires_key(client):
    assert client.get("/reports/summary").status_code == 401


def test_summary_for_tenant(client):
    body = client.get("/reports/summary", headers=TENANT_1).json()
    assert body["tenant_id"] == 1
    assert {s["status"]: s["count"] for s in body["by_status"]} == {"overdue": 1, "paid": 2, "pending": 2}


def test_export_returns_tenant_invoices(client):
    r = client.get("/reports/export", params={"tenant_id": 2}, headers=TENANT_2)
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["invoices"]] == [6, 7, 8, 9]
