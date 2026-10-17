from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Invoices")

class StatusUpdate(BaseModel):
    status: Literal["paid", "pending", "overdue", "void"]


def serialize(row):
    return {**row, "created_at": row["created_at"].isoformat()}


@app.get("/invoices")
def list_invoices(x_tenant_id: int = Header(...), db=Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT id, tenant_id, customer, amount_cents, status, created_at "
            "FROM invoices WHERE tenant_id = :tenant ORDER BY id"
        ),
        {"tenant": x_tenant_id},
    ).mappings().all()
    return [serialize(r) for r in rows]


@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, x_tenant_id: int = Header(...), db=Depends(get_db)):
    row = db.execute(
        text(
            "SELECT id, tenant_id, customer, amount_cents, status, created_at "
            "FROM invoices WHERE id = :id"
        ),
        {"id": invoice_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize(row)


@app.patch("/invoices/{invoice_id}/status")
def update_status(
    invoice_id: int, body: StatusUpdate, x_tenant_id: int = Header(...), db=Depends(get_db)
):
    row = db.execute(
        text(
            "UPDATE invoices SET status = :status WHERE id = :id "
            "RETURNING id, tenant_id, customer, amount_cents, status, created_at"
        ),
        {"status": body.status, "id": invoice_id},
    ).mappings().first()
    db.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize(row)
