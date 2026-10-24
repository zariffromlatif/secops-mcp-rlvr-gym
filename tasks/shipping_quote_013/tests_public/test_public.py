from conftest import box, quote


def test_single_small_package(client):
    r = quote(client, "DHK", box(1000))
    assert r.status_code == 200
    assert r.json() == {"zone": "DHK", "packages": [{"billable_kg": 1.0, "cents": 300}], "total_cents": 300}


def test_two_packages(client):
    assert quote(client, "CTG", box(500), box(500)).json()["total_cents"] == 400


def test_unknown_zone(client):
    assert quote(client, "MARS", box(500)).status_code == 404


def test_no_packages(client):
    assert quote(client, "DHK").status_code == 422
