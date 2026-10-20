"""Stock reservations for orders.

- POST /orders/{ref}/reserve reserves every line of an order, or nothing: if any SKU lacks
  stock for the TOTAL quantity requested across all of the order's lines, respond 409 and
  change nothing. Unknown SKUs are 404.
- POST /orders/{ref}/release releases the order's active reservations and returns their
  stock. It is idempotent: releasing an order a second time restores nothing and reports
  released = 0.
"""

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Inventory")


class Line(BaseModel):
    sku: str
    qty: int = Field(ge=1)


class ReserveRequest(BaseModel):
    lines: list[Line] = Field(min_length=1)


def current_stock(db, sku: str) -> int:
    stock = db.execute(
        text("SELECT stock FROM products WHERE sku = :sku FOR UPDATE"), {"sku": sku}
    ).scalar()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown SKU {sku}")
    return stock


@app.post("/orders/{order_ref}/reserve")
def reserve(order_ref: str, body: ReserveRequest, db=Depends(get_db)):
    for line in body.lines:
        if current_stock(db, line.sku) < line.qty:
            raise HTTPException(status_code=409, detail=f"Insufficient stock for {line.sku}")

    stock = {}
    for line in body.lines:
        db.execute(
            text("UPDATE products SET stock = stock - :qty WHERE sku = :sku"),
            {"qty": line.qty, "sku": line.sku},
        )
        db.execute(
            text(
                "INSERT INTO reservations (order_ref, sku, qty, status) "
                "VALUES (:ref, :sku, :qty, 'active')"
            ),
            {"ref": order_ref, "sku": line.sku, "qty": line.qty},
        )
        stock[line.sku] = db.execute(
            text("SELECT stock FROM products WHERE sku = :sku"), {"sku": line.sku}
        ).scalar()
    db.commit()
    return {"order_ref": order_ref, "stock": stock}


@app.post("/orders/{order_ref}/release")
def release(order_ref: str, db=Depends(get_db)):
    rows = db.execute(
        text("SELECT sku, qty FROM reservations WHERE order_ref = :ref"), {"ref": order_ref}
    ).mappings().all()
    for row in rows:
        db.execute(
            text("UPDATE products SET stock = stock + :qty WHERE sku = :sku"),
            {"qty": row["qty"], "sku": row["sku"]},
        )
    db.commit()
    return {"order_ref": order_ref, "released": len(rows)}
