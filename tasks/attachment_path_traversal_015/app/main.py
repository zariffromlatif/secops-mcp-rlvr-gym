from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Attachments")

STORAGE = Path(__file__).resolve().parent / "storage"


@app.get("/attachments")
def list_attachments(x_tenant_id: int = Header(...), db=Depends(get_db)):
    rows = db.execute(
        text("SELECT name, uploaded_at FROM attachments WHERE tenant_id = :tenant ORDER BY name"),
        {"tenant": x_tenant_id},
    ).mappings().all()
    return [{"name": r["name"], "uploaded_at": r["uploaded_at"].isoformat()} for r in rows]


@app.get("/attachments/content")
def read_attachment(name: str, x_tenant_id: int = Header(...)):
    path = STORAGE / str(x_tenant_id) / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {"name": name, "content": path.read_text()}
