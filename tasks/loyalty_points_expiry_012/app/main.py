"""Loyalty points.

Customers earn points on purchases and redeem them for discounts. The rules:

- Points expire 365 days after the day they were earned: points earned on day D can be used
  up to and including day D + 364, and are gone from day D + 365.
- A redemption always uses the OLDEST unexpired points first. Points that were redeemed before
  their expiry date are used up, so they can't expire later.
- GET /customers/{id}/points?as_of=YYYY-MM-DD returns the balance on that day, counting only
  events on or before it (on the same day, earnings count before redemptions).
- POST /customers/{id}/redemptions redeems points on a given day. It is rejected with 409,
  changing nothing, if the customer's balance on that day is lower than the points asked for.
- Unknown customers are 404.
"""

from collections import deque
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Loyalty")

EXPIRY = timedelta(days=365)


class Redemption(BaseModel):
    points: int = Field(ge=1)
    redeemed_on: date


def require_customer(db, customer_id: int) -> None:
    found = db.execute(text("SELECT 1 FROM customers WHERE id = :id"), {"id": customer_id}).scalar()
    if found is None:
        raise HTTPException(status_code=404, detail="Customer not found")


def balance_on(db, customer_id: int, day: date) -> int:
    rows = db.execute(
        text(
            "SELECT kind, points FROM point_events "
            "WHERE customer_id = :id AND occurred_on <= :day"
        ),
        {"id": customer_id, "day": day},
    ).mappings().all()
    earned = sum(r["points"] for r in rows if r["kind"] == "earn")
    redeemed = sum(r["points"] for r in rows if r["kind"] == "redeem")
    return earned - redeemed


@app.get("/customers/{customer_id}/points")
def points(customer_id: int, as_of: date = Query(), db=Depends(get_db)):
    require_customer(db, customer_id)
    return {"customer_id": customer_id, "as_of": as_of.isoformat(), "balance": balance_on(db, customer_id, as_of)}


@app.post("/customers/{customer_id}/redemptions", status_code=201)
def redeem(customer_id: int, body: Redemption, db=Depends(get_db)):
    require_customer(db, customer_id)
    available = balance_on(db, customer_id, body.redeemed_on)
    if available < body.points:
        raise HTTPException(status_code=409, detail="Not enough points")
    db.execute(
        text(
            "INSERT INTO point_events (customer_id, kind, points, occurred_on) "
            "VALUES (:id, 'redeem', :points, :day)"
        ),
        {"id": customer_id, "points": body.points, "day": body.redeemed_on},
    )
    db.commit()
    return {"customer_id": customer_id, "balance": available - body.points}
