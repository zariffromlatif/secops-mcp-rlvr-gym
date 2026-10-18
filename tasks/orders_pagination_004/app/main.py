from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Orders")


@app.get("/orders")
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(4, ge=1, le=50),
    db=Depends(get_db),
):
    total = db.execute(text("SELECT COUNT(*) FROM orders")).scalar_one()
    total_pages = max(1, total // page_size)
    if page > total_pages:
        raise HTTPException(status_code=404, detail="Page out of range")

    rows = db.execute(
        text("SELECT id, customer, total_cents FROM orders ORDER BY id LIMIT :limit OFFSET :offset"),
        {"limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "items": [dict(r) for r in rows],
    }
