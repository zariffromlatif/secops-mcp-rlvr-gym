from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Invoice splitting")


class SplitRequest(BaseModel):
    payers: int = Field(ge=1, le=20)


@app.post("/invoices/{invoice_id}/split")
def split_invoice(invoice_id: int, body: SplitRequest, db=Depends(get_db)):
    amount = db.execute(
        text("SELECT amount_cents FROM invoices WHERE id = :id"), {"id": invoice_id}
    ).scalar()
    if amount is None:
        raise HTTPException(status_code=404, detail="Invoice not found")

    share = amount // body.payers
    shares = [share] * body.payers
    return {"invoice_id": invoice_id, "amount_cents": amount, "shares": shares}
