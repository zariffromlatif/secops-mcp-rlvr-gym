from conftest import listing, read


def test_list_own_attachments(client):
    assert [a["name"] for a in listing(client, 1).json()] == ["invoice-001.txt", "receipts/2026-01.txt"]


def test_read_own_file(client):
    r = read(client, 1, "invoice-001.txt")
    assert r.status_code == 200
    assert r.json() == {"name": "invoice-001.txt", "content": "Invoice 001 for Acme Ltd: 120.00\n"}


def test_missing_file_is_404(client):
    assert read(client, 1, "nope.txt").status_code == 404
