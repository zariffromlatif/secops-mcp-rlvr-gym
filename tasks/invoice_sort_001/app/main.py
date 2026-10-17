from typing import Optional

from fastapi import Depends, FastAPI, Header
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Invoices")


@app.get("/invoices")
def list_invoices(
    sort_by: str = "created_at",
    order: str = "desc",
    status: Optional[str] = None,
    x_tenant_id: int = Header(...),
    db=Depends(get_db),
):
    params = {"tenant": x_tenant_id}
    status_clause = ""
    if status:
        status_clause = "AND status = :status"
        params["status"] = status

    query = text(
        f"SELECT id, customer, amount_cents, status, created_at FROM invoices "
        f"WHERE tenant_id = :tenant {status_clause} ORDER BY {sort_by} {order}"
    )
    rows = db.execute(query, params).mappings().all()
    return [
        {**row, "created_at": row["created_at"].isoformat()}
        for row in rows
    ]
