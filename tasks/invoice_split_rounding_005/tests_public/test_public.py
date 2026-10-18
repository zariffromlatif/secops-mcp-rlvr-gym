from conftest import split


def test_even_split(client):
    r = split(client, 1, 4)
    assert r.status_code == 200
    assert r.json()["shares"] == [3000, 3000, 3000, 3000]


def test_missing_invoice(client):
    assert split(client, 999, 2).status_code == 404


def test_zero_payers_rejected(client):
    assert split(client, 1, 0).status_code == 422
