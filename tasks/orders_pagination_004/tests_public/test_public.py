from conftest import ids


def test_first_page(client):
    r = client.get("/orders")
    assert r.status_code == 200
    assert ids(r) == [1, 2, 3, 4]
    assert r.json()["total"] == 9


def test_second_page(client):
    assert ids(client.get("/orders", params={"page": 2})) == [5, 6, 7, 8]


def test_exact_division(client):
    r = client.get("/orders", params={"page": 3, "page_size": 3})
    assert ids(r) == [7, 8, 9]
    assert r.json()["total_pages"] == 3


def test_page_zero_rejected(client):
    assert client.get("/orders", params={"page": 0}).status_code == 422
