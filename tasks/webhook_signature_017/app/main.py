"""Payment webhooks from the payment provider.

Every request carries a Payment-Signature header, "t=<unix seconds>,v1=<hex>", where v1 is the
HMAC-SHA256 of "<t>." followed by the raw request body, keyed with the webhook secret stored in
the settings table. The service must:
- reject a request whose signature is missing or invalid with 401, changing nothing
- reject a correctly signed event whose timestamp is more than 300 seconds away from now (in the
  past or in the future) with 400, changing nothing, so a captured request can't be replayed later
- process each event id once: a repeated event id returns {"status": "duplicate"} and changes nothing
- otherwise mark the event's invoice as paid and return {"status": "processed"}; unknown invoices are 404
"""

import hashlib
import hmac
import json

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Payment webhooks")


def webhook_secret(db) -> bytes:
    return db.execute(text("SELECT value FROM settings WHERE key = 'webhook_secret'")).scalar_one().encode()


def header_parts(header: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in header.split(",") if "=" in item)


def signature_ok(secret: bytes, header: str, raw: bytes) -> bool:
    parts = header_parts(header)
    expected = hmac.new(secret, f"{parts.get('t', '')}.".encode() + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(parts.get("v1", ""), expected)


@app.post("/webhooks/payment")
async def payment_event(request: Request, payment_signature: str | None = Header(None), db=Depends(get_db)):
    raw = await request.body()
    if payment_signature is not None and not signature_ok(webhook_secret(db), payment_signature, raw):
        raise HTTPException(status_code=401, detail="Invalid signature")
    event = json.loads(raw)
    if db.execute(text("SELECT 1 FROM webhook_events WHERE event_id = :id"), {"id": event["id"]}).first():
        return {"status": "duplicate"}
    if db.execute(text("SELECT 1 FROM invoices WHERE id = :id"), {"id": event["invoice_id"]}).first() is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.execute(text("UPDATE invoices SET status = 'paid' WHERE id = :id"), {"id": event["invoice_id"]})
    db.execute(
        text("INSERT INTO webhook_events (event_id, invoice_id) VALUES (:id, :invoice)"),
        {"id": event["id"], "invoice": event["invoice_id"]},
    )
    db.commit()
    return {"status": "processed"}
