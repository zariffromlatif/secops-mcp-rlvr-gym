from fastapi import Depends, FastAPI
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Revenue report")


@app.get("/reports/revenue")
def revenue(db=Depends(get_db)):
    """Revenue per customer: paid invoices that have at least one recorded payment."""
    rows = db.execute(
        text(
            "SELECT i.customer, COUNT(i.id) AS invoices, SUM(i.amount_cents) AS revenue_cents "
            "FROM invoices i JOIN payments p ON p.invoice_id = i.id "
            "WHERE i.status = 'paid' "
            "GROUP BY i.customer ORDER BY i.customer"
        )
    ).mappings().all()
    return [dict(r) for r in rows]
