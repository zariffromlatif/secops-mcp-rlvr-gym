"""Fee on the outstanding balance, the grace period, and the cap."""

from conftest import fee


def test_fee_on_outstanding_balance(client):
    r = fee(client, "INV-12", "2026-02-15").json()
    assert (r["periods"], r["fee_cents"]) == (2, 1200)


def test_no_fee_during_grace_period(client):
    assert fee(client, "INV-10", "2026-01-04").json()["fee_cents"] == 0
    assert fee(client, "INV-10", "2026-01-06").json()["fee_cents"] == 0


def test_periods_counted_after_grace(client):
    r = fee(client, "INV-10", "2026-02-05").json()
    assert (r["periods"], r["fee_cents"]) == (1, 1000)


def test_fee_capped_at_five_periods(client):
    r = fee(client, "INV-13", "2026-01-01").json()
    assert (r["periods"], r["fee_cents"]) == (5, 1000)


def test_first_day_after_grace_is_one_period(client):
    # due 2026-01-01 + 5 grace days: the 7th is 1 day late; INV-12 has 300.00 outstanding
    r = fee(client, "INV-12", "2026-01-07").json()
    assert (r["periods"], r["fee_cents"]) == (1, 600)


def test_thirty_one_days_late_starts_a_second_period(client):
    r = fee(client, "INV-12", "2026-02-06").json()
    assert (r["periods"], r["fee_cents"]) == (2, 1200)
