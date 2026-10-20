from conftest import amounts, change


def test_downgrade_gives_negative_net(client):
    assert amounts(change(client, 4, 1, "2026-06-11")) == (6000, 1933, -4067)


def test_change_on_first_day_prorates_whole_period(client):
    assert amounts(change(client, 1, 2, "2026-04-01")) == (2900, 9000, 6100)


def test_unknown_new_plan(client):
    assert change(client, 1, 42, "2026-04-10").status_code == 404
