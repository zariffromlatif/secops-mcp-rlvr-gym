"""Volumetric weight, and rounding up to the next 0.5 kg."""

from conftest import box, quote


def test_large_light_box_uses_volumetric_weight(client):
    r = quote(client, "DHK", box(1000, 40, 40, 40)).json()
    assert r["packages"] == [{"billable_kg": 13.0, "cents": 3900}]


def test_rounds_up_not_to_nearest(client):
    assert quote(client, "DHK", box(1200)).json()["packages"] == [{"billable_kg": 1.5, "cents": 450}]


def test_volumetric_rounded_up(client):
    assert quote(client, "CTG", box(700, 30, 20, 15)).json()["total_cents"] == 800


def test_volumetric_exactly_one_kilo(client):
    assert quote(client, "DHK", box(300, 50, 10, 10)).json()["total_cents"] == 300


def test_each_package_rounded_separately(client):
    r = quote(client, "DHK", box(600), box(600)).json()
    assert r["total_cents"] == 600


def test_one_gram_over_a_step_bills_the_next_step(client):
    assert quote(client, "DHK", box(5001)).json()["packages"] == [{"billable_kg": 5.5, "cents": 1650}]
