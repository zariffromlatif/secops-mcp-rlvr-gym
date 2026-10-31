from conftest import events, send, signed, status_of


def test_signed_event_marks_invoice_paid(client):
    r = send(client, *signed({"id": "evt_1", "invoice_id": 1}))
    assert r.status_code == 200 and r.json() == {"status": "processed"}
    assert status_of(1) == "paid"


def test_repeated_event_is_a_duplicate(client):
    send(client, *signed({"id": "evt_2", "invoice_id": 2}))
    assert send(client, *signed({"id": "evt_2", "invoice_id": 2})).json() == {"status": "duplicate"}
    assert events() == 1


def test_unknown_invoice_is_404(client):
    assert send(client, *signed({"id": "evt_3", "invoice_id": 99})).status_code == 404
