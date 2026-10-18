from conftest import report


def test_utc_day(client):
    r = report(client, "2026-03-01", "UTC")
    assert r.status_code == 200
    assert (r.json()["count"], r.json()["total_cents"]) == (3, 1200)


def test_default_zone_is_utc(client):
    assert report(client, "2026-03-01").json()["tz"] == "UTC"


def test_unknown_zone_rejected(client):
    assert report(client, "2026-03-01", "Mars/Olympus").status_code == 422
