from conftest import fee


def test_unpaid_invoice_late(client):
    r = fee(client, "INV-10", "2026-01-20")
    assert r.status_code == 200
    assert r.json() == {"invoice_id": "INV-10", "as_of": "2026-01-20", "outstanding_cents": 50000,
                        "periods": 1, "fee_cents": 1000}


def test_not_due_yet(client):
    assert fee(client, "INV-10", "2025-12-20").json()["fee_cents"] == 0


def test_paid_in_full_has_no_fee(client):
    assert fee(client, "INV-11", "2026-03-01").json()["fee_cents"] == 0


def test_unknown_invoice(client):
    assert fee(client, "INV-99", "2026-01-20").status_code == 404
