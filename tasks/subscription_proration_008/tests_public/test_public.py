from conftest import amounts, change


def test_upgrade_mid_april(client):
    r = change(client, 1, 2, "2026-04-16")
    assert r.status_code == 200
    assert amounts(r) == (1450, 4500, 3050)


def test_same_plan_rejected(client):
    assert change(client, 1, 1, "2026-04-10").status_code == 422


def test_date_outside_period_rejected(client):
    assert change(client, 1, 2, "2026-05-01").status_code == 422


def test_missing_subscription(client):
    assert change(client, 99, 2, "2026-04-10").status_code == 404
