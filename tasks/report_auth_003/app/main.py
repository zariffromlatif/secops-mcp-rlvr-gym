from fastapi import Depends, FastAPI
from sqlalchemy import text

from app.auth import require_tenant
from app.db import get_db

app = FastAPI(title="Reports")


@app.get("/reports/summary")
def summary(tenant: int = Depends(require_tenant), db=Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT status, COUNT(*) AS count, SUM(amount_cents) AS total_cents "
            "FROM invoices WHERE tenant_id = :tenant GROUP BY status ORDER BY status"
        ),
        {"tenant": tenant},
    ).mappings().all()
    return {"tenant_id": tenant, "by_status": [dict(r) for r in rows]}


# Added for the finance team's nightly export job.
@app.get("/reports/export")
def export(tenant_id: int, db=Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT id, customer, amount_cents, status, created_at "
            "FROM invoices WHERE tenant_id = :tenant ORDER BY id"
        ),
        {"tenant": tenant_id},
    ).mappings().all()
    return {
        "tenant_id": tenant_id,
        "invoices": [{**r, "created_at": r["created_at"].isoformat()} for r in rows],
    }
