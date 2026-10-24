"""Shipping quotes.

- Every package is priced on its billable weight: the larger of its actual weight and its
  volumetric weight (length x width x height in cm, divided by 5000, in kg).
- The billable weight is rounded UP to the next 0.5 kg (1.01 kg bills as 1.5 kg; exactly
  1.5 kg stays 1.5 kg). The minimum is 0.5 kg.
- A package costs the zone's rate for every 0.5 kg of billable weight. Packages are priced
  separately, and the quote total is the sum of the package prices.
- Unknown zones are 404.
"""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Shipping")


class Package(BaseModel):
    weight_g: int = Field(gt=0)
    length_cm: int = Field(gt=0)
    width_cm: int = Field(gt=0)
    height_cm: int = Field(gt=0)


class QuoteRequest(BaseModel):
    zone: str
    packages: list[Package] = Field(min_length=1)


def zone_rate(db, zone: str) -> int:
    rate = db.execute(
        text("SELECT cents_per_half_kg FROM zones WHERE code = :code"), {"code": zone}
    ).scalar()
    if rate is None:
        raise HTTPException(status_code=404, detail="Unknown zone")
    return rate


def billable_halves(package: Package) -> int:
    """Billable weight as a number of 0.5 kg steps."""
    return max(1, round(package.weight_g / 500))


@app.post("/quotes")
def quote(body: QuoteRequest, db=Depends(get_db)):
    rate = zone_rate(db, body.zone)
    lines = []
    for package in body.packages:
        halves = billable_halves(package)
        lines.append({"billable_kg": halves / 2, "cents": halves * rate})
    return {"zone": body.zone, "packages": lines, "total_cents": sum(line["cents"] for line in lines)}
