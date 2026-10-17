from conftest import get


def test_tenant_only_sees_own_invoices(client):
    r = get(client, 1)
    assert r.status_code == 200
    assert {row["customer"] for row in r.json()} == {
        "Acme Ltd", "Bolt Traders", "Cedar Foods", "Delta Print", "Echo Labs",
    }


def test_default_sort_is_newest_first(client):
    rows = get(client, 1).json()
    dates = [row["created_at"] for row in rows]
    assert dates == sorted(dates, reverse=True)


def test_sort_by_amount_ascending(client):
    rows = get(client, 2, sort_by="amount_cents", order="asc").json()
    assert [row["amount_cents"] for row in rows] == [1900, 33000, 77000, 150000]


def test_status_filter(client):
    rows = get(client, 1, status="paid").json()
    assert {row["customer"] for row in rows} == {"Acme Ltd", "Cedar Foods"}


def test_missing_tenant_header_rejected(client):
    assert client.get("/invoices").status_code == 422
