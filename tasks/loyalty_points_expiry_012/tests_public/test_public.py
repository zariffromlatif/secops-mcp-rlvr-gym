from conftest import balance, redeem


def test_balance_subtracts_redemptions(client):
    r = balance(client, 1, "2026-01-01")
    assert r.status_code == 200
    assert r.json() == {"customer_id": 1, "as_of": "2026-01-01", "balance": 150}


def test_later_events_not_counted_yet(client):
    assert balance(client, 1, "2026-02-01").json()["balance"] == 250


def test_unknown_customer(client):
    assert balance(client, 99, "2026-01-01").status_code == 404


def test_redeem_more_than_balance_rejected(client):
    assert redeem(client, 2, 100, "2026-01-05").status_code == 409
    assert balance(client, 2, "2026-01-05").json()["balance"] == 80


def test_redeem_within_balance(client):
    r = redeem(client, 2, 30, "2026-01-05")
    assert r.status_code == 201
    assert r.json()["balance"] == 50
    assert balance(client, 2, "2026-01-06").json()["balance"] == 50
