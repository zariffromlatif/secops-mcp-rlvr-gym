"""Invoices with several payments must be counted once."""

from conftest import by_customer


def test_acme_counted_once_per_invoice(client):
    acme = by_customer(client)["Acme Ltd"]
    assert (acme["invoices"], acme["revenue_cents"]) == (2, 15000)


def test_bolt_counted_once_per_invoice(client):
    bolt = by_customer(client)["Bolt Traders"]
    assert (bolt["invoices"], bolt["revenue_cents"]) == (2, 14000)


def test_total_revenue(client):
    assert sum(r["revenue_cents"] for r in by_customer(client).values()) == 33000
