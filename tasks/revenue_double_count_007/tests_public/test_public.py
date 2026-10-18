from conftest import by_customer


def test_customers_listed(client):
    assert list(by_customer(client)) == ["Acme Ltd", "Bolt Traders", "Dune Studio"]


def test_single_payment_customer(client):
    assert by_customer(client)["Dune Studio"] == {
        "customer": "Dune Studio", "invoices": 1, "revenue_cents": 4000,
    }
