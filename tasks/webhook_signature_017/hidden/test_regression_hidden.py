import time

from conftest import SECRET, events, send, signed, status_of


def test_wrong_secret_rejected(client):
    assert send(client, *signed({"id": "evt_4", "invoice_id": 1}, secret=b"guess")).status_code == 401
    assert status_of(1) == "open" and events() == 0


def test_tampered_body_rejected(client):
    _, headers = signed({"id": "evt_5", "invoice_id": 1})
    raw, _ = signed({"id": "evt_5", "invoice_id": 2})
    assert send(client, raw, headers).status_code == 401
    assert status_of(2) == "open"


def test_signature_for_another_timestamp_rejected(client):
    raw, headers = signed({"id": "evt_6", "invoice_id": 1})
    now = int(time.time())
    forged = headers["Payment-Signature"].replace(f"t={now}", f"t={now + 1}")
    assert send(client, raw, {**headers, "Payment-Signature": forged}).status_code == 401


def test_already_paid_invoice_stays_paid(client):
    assert send(client, *signed({"id": "evt_7", "invoice_id": 3})).json() == {"status": "processed"}
    assert status_of(3) == "paid"


def test_secret_is_read_from_settings(client):
    assert SECRET == b"whsec_test_9f3c"


def test_events_within_the_tolerance_accepted(client):
    now = int(time.time())
    assert send(client, *signed({"id": "evt_8", "invoice_id": 1}, t=now - 250)).status_code == 200
    assert send(client, *signed({"id": "evt_9", "invoice_id": 2}, t=now + 250)).status_code == 200


def test_malformed_signature_header_rejected(client):
    raw, headers = signed({"id": "evt_13", "invoice_id": 1})
    assert send(client, raw, {**headers, "Payment-Signature": "t=1,v1=abc=def"}).status_code == 401
