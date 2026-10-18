"""Days must follow the requested time zone (Asia/Dhaka is UTC+6), not the UTC calendar."""

import pytest

from conftest import report


@pytest.mark.parametrize(
    "day,count,total",
    [("2026-02-28", 1, 100), ("2026-03-01", 3, 900), ("2026-03-02", 2, 1100)],
)
def test_dhaka_days(client, day, count, total):
    body = report(client, day, "Asia/Dhaka").json()
    assert (body["count"], body["total_cents"]) == (count, total)


def test_midnight_boundary_belongs_to_new_day(client):
    # 2026-03-01 18:00 UTC is exactly 00:00 on 2 March in Dhaka.
    assert report(client, "2026-03-02", "Asia/Dhaka").json()["count"] == 2
