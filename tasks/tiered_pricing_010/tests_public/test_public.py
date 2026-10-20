from conftest import quote


def test_small_quote(client):
    body = quote(client, "api_calls", 500).json()
    assert body["total_cents"] == 5000
    assert body["lines"] == [{"units": 500, "unit_cents": 10}]


def test_seats_in_first_tier(client):
    assert quote(client, "seats", 3).json()["total_cents"] == 6000


def test_unknown_product(client):
    assert quote(client, "gpus", 1).status_code == 404


def test_zero_quantity_rejected(client):
    assert quote(client, "api_calls", 0).status_code == 422
