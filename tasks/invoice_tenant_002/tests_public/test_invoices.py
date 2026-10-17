from conftest import as_tenant


def test_list_only_own_invoices(client):
    rows = client.get("/invoices", headers=as_tenant(1)).json()
    assert [r["id"] for r in rows] == [1, 2, 3, 4, 5]


def test_get_own_invoice(client):
    r = client.get("/invoices/3", headers=as_tenant(1))
    assert r.status_code == 200
    assert r.json()["customer"] == "Cedar Foods"


def test_get_missing_invoice_is_404(client):
    assert client.get("/invoices/999", headers=as_tenant(1)).status_code == 404


def test_update_own_invoice_status(client):
    r = client.patch("/invoices/2/status", json={"status": "paid"}, headers=as_tenant(1))
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_invalid_status_rejected(client):
    r = client.patch("/invoices/2/status", json={"status": "refunded"}, headers=as_tenant(1))
    assert r.status_code == 422
