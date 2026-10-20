from conftest import reserve, stock_of


def test_multi_sku_order(client):
    r = reserve(client, "ORD-5", ("PEN-01", 2), ("BOOK-02", 1), ("LAMP-03", 2))
    assert r.status_code == 200
    assert (stock_of("PEN-01"), stock_of("BOOK-02"), stock_of("LAMP-03")) == (3, 9, 0)


def test_failed_line_rolls_back_whole_order(client):
    assert reserve(client, "ORD-6", ("PEN-01", 1), ("LAMP-03", 5)).status_code == 409
    assert (stock_of("PEN-01"), stock_of("LAMP-03")) == (5, 2)


def test_release_unknown_order(client):
    assert client.post("/orders/NOPE/release").json()["released"] == 0


def test_duplicate_sku_lines_within_stock(client):
    assert reserve(client, "ORD-8", ("PEN-01", 2), ("PEN-01", 2)).status_code == 200
    assert stock_of("PEN-01") == 1
