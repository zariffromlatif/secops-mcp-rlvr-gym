from conftest import pay, payment_count


def test_first_request_creates(client):
    r = pay(client, 1, "k-1")
    assert r.status_code == 201
    assert r.json()["amount_cents"] == 1000


def test_retry_returns_original(client):
    first = pay(client, 1, "k-2").json()
    again = pay(client, 1, "k-2")
    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert payment_count() == 1


def test_missing_key_rejected(client):
    r = client.post("/payments", json={"amount_cents": 5, "description": "x"}, headers={"X-Tenant-ID": "1"})
    assert r.status_code == 422
