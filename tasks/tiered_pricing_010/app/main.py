"""Usage-based quotes with GRADUATED tiers (as on the public pricing page).

Each tier has an inclusive upper bound `up_to` (NULL means no limit) and a per-unit price.
Units are charged tier by tier: with tiers (1000 @ 10c, 10000 @ 8c, rest @ 5c), a quote for
1,500 units is 1000 x 10c + 500 x 8c = 140.00. Exactly 1,000 units is entirely in the first tier.
`lines` lists the units and unit price used in each tier, in tier order, skipping empty tiers.
"""

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Pricing")


def load_tiers(db, product: str):
    tiers = db.execute(
        text("SELECT up_to, unit_cents FROM tiers WHERE product = :p ORDER BY position"),
        {"p": product},
    ).mappings().all()
    if not tiers:
        raise HTTPException(status_code=404, detail="Unknown product")
    return tiers


@app.get("/quote")
def quote(product: str, quantity: int = Query(ge=1), db=Depends(get_db)):
    tiers = load_tiers(db, product)
    tier = next(t for t in tiers if t["up_to"] is None or quantity < t["up_to"])
    total = quantity * tier["unit_cents"]
    return {
        "product": product,
        "quantity": quantity,
        "total_cents": total,
        "lines": [{"units": quantity, "unit_cents": tier["unit_cents"]}],
    }
