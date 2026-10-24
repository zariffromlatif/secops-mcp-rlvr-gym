"""Late fees on invoices.

GET /invoices/{id}/late-fee?as_of=YYYY-MM-DD computes the late fee on a given day:

- The outstanding balance is the invoice total minus the payments made on or before as_of.
  An invoice with nothing outstanding has no fee.
- There is a 5-day grace period: no fee up to and including due_date + 5 days. Days late are
  counted from the end of the grace period (due_date + 6 days is 1 day late).
- The fee is 2% of the OUTSTANDING balance for every started 30-day period of lateness
  (1-30 days late is 1 period, 31-60 days is 2, ...), capped at 5 periods (10%).
- The fee is rounded to the nearest cent, halves rounded up.
- Unknown invoices are 404.
"""

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Late fees")


def load_invoice(db, invoice_id: str, as_of: date) -> dict:
    invoice = db.execute(
        text("SELECT id, total_cents, due_date FROM invoices WHERE id = :id"), {"id": invoice_id}
    ).mappings().first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    paid = db.execute(
        text("SELECT COALESCE(SUM(amount_cents), 0) FROM payments WHERE invoice_id = :id AND paid_on <= :day"),
        {"id": invoice_id, "day": as_of},
    ).scalar_one()
    return {**invoice, "outstanding": invoice["total_cents"] - paid}


def percent_of(cents: int, percent: int) -> int:
    return int((Decimal(cents) * percent / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@app.get("/invoices/{invoice_id}/late-fee")
def late_fee(invoice_id: str, as_of: date = Query(), db=Depends(get_db)):
    invoice = load_invoice(db, invoice_id, as_of)
    days_late = (as_of - invoice["due_date"]).days
    if invoice["outstanding"] <= 0 or days_late <= 0:
        periods = 0
    else:
        periods = math.ceil(days_late / 30)
    return {
        "invoice_id": invoice_id,
        "as_of": as_of.isoformat(),
        "outstanding_cents": invoice["outstanding"],
        "periods": periods,
        "fee_cents": percent_of(invoice["total_cents"], 2 * periods),
    }
