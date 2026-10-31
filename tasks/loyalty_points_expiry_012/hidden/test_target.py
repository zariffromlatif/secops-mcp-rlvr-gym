"""Expiry, and redemptions using the oldest points first."""

from conftest import balance, redeem


def test_old_points_expire(client):
    assert balance(client, 3, "2026-01-10").json()["balance"] == 120


def test_redeemed_points_cannot_expire_again(client):
    assert balance(client, 4, "2026-02-01").json()["balance"] == 50


def test_redemptions_use_oldest_points_first(client):
    assert balance(client, 5, "2026-02-01").json()["balance"] == 100


def test_expire_on_day_365(client):
    assert balance(client, 6, "2026-02-01").json()["balance"] == 0


def test_cannot_redeem_expired_points(client):
    assert redeem(client, 3, 200, "2026-01-10").status_code == 409
    assert balance(client, 3, "2026-01-10").json()["balance"] == 120


def test_redemption_spanning_two_lots(client):
    # 50 points use all 30 from January 2025, then 20 of the 100 from June 2025.
    assert balance(client, 7, "2026-01-15").json()["balance"] == 80
    # The June lot (80 left) expires on 2026-06-01.
    assert balance(client, 7, "2026-06-01").json()["balance"] == 0
