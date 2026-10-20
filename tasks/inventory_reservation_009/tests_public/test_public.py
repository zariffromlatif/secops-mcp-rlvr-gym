from conftest import reserve, stock_of


def test_reserve_single_line(client):
    r = reserve(client, "ORD-1", ("BOOK-02", 3))
    assert r.status_code == 200
    assert r.json()["stock"] == {"BOOK-02": 7}


def test_insufficient_stock_changes_nothing(client):
    assert reserve(client, "ORD-2", ("LAMP-03", 3)).status_code == 409
    assert stock_of("LAMP-03") == 2


def test_unknown_sku(client):
    assert reserve(client, "ORD-3", ("NOPE-9", 1)).status_code == 404


def test_release_returns_stock(client):
    reserve(client, "ORD-4", ("BOOK-02", 4))
    r = client.post("/orders/ORD-4/release")
    assert r.json()["released"] == 1
    assert stock_of("BOOK-02") == 10
