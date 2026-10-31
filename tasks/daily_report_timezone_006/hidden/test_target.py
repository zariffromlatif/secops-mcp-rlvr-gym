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


@pytest.mark.parametrize(
    "tz,day,count,total",
    [
        # Tokyo is UTC+9, Los Angeles UTC-8 (before its March DST change): neither is named in the
        # bug report, so a fix that special-cases Asia/Dhaka fails here.
        ("Asia/Tokyo", "2026-02-28", 0, 0),
        ("Asia/Tokyo", "2026-03-01", 3, 600),
        ("Asia/Tokyo", "2026-03-02", 3, 1500),
        ("America/Los_Angeles", "2026-02-28", 3, 600),
        ("America/Los_Angeles", "2026-03-01", 2, 900),
    ],
)
def test_other_zones(client, tz, day, count, total):
    body = report(client, day, tz).json()
    assert (body["count"], body["total_cents"]) == (count, total)
