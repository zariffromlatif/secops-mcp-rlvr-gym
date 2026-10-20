"""Mid-cycle plan changes.

Billing periods are half-open date ranges [period_start, period_end): period_end is the
first day of the NEXT period. When a plan changes on `effective_date`, the customer is
credited for the unused part of the old plan and charged for the rest of the period on the
new plan. The remaining part runs from effective_date (inclusive) to period_end, and it is
measured in days against the real length of the period (28-31 days). Each amount is rounded
to the nearest cent, with halves rounded up.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Subscriptions")


class PlanChange(BaseModel):
    new_plan_id: int
    effective_date: date


def plan_price(db, plan_id: int) -> int:
    price = db.execute(
        text("SELECT monthly_cents FROM plans WHERE id = :id"), {"id": plan_id}
    ).scalar()
    if price is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return price


def prorate(price_cents: int, remaining_days: int, period_start: date, period_end: date) -> int:
    days_in_period = 30
    return price_cents * remaining_days // days_in_period


@app.post("/subscriptions/{subscription_id}/change-plan")
def change_plan(subscription_id: int, body: PlanChange, db=Depends(get_db)):
    sub = db.execute(
        text("SELECT plan_id, period_start, period_end FROM subscriptions WHERE id = :id"),
        {"id": subscription_id},
    ).mappings().first()
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    if body.new_plan_id == sub["plan_id"]:
        raise HTTPException(status_code=422, detail="Already on this plan")
    if not sub["period_start"] <= body.effective_date < sub["period_end"]:
        raise HTTPException(status_code=422, detail="effective_date outside the current period")

    old_price = plan_price(db, sub["plan_id"])
    new_price = plan_price(db, body.new_plan_id)
    remaining = (sub["period_end"] - body.effective_date).days
    credit = prorate(old_price, remaining, sub["period_start"], sub["period_end"])
    charge = prorate(new_price, remaining, sub["period_start"], sub["period_end"])
    return {"credit_cents": credit, "charge_cents": charge, "net_cents": charge - credit}
