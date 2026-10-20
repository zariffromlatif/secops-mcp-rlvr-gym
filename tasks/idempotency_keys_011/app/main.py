"""Payment creation with idempotency keys.

Clients send an Idempotency-Key header with every POST /payments. Keys are scoped per tenant
(X-Tenant-ID): two tenants may use the same key string independently.
- first request for a key: create the payment, respond 201
- same tenant, same key, same body: return the ORIGINAL payment with 200; create nothing
- same tenant, same key, different body: respond 409; create nothing
"""

import hashlib
import json

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Payments")


class PaymentIn(BaseModel):
    amount_cents: int = Field(gt=0)
    description: str


def body_hash(body: PaymentIn) -> str:
    return hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()


def get_payment(db, payment_id: int) -> dict:
    return dict(db.execute(
        text("SELECT id, tenant_id, amount_cents, description FROM payments WHERE id = :id"),
        {"id": payment_id},
    ).mappings().one())


@app.post("/payments", status_code=201)
def create_payment(
    body: PaymentIn,
    response: Response,
    idempotency_key: str = Header(...),
    x_tenant_id: int = Header(...),
    db=Depends(get_db),
):
    existing = db.execute(
        text("SELECT payment_id FROM idempotency_keys WHERE key = :k"),
        {"k": idempotency_key},
    ).mappings().first()
    if existing:
        response.status_code = 200
        return get_payment(db, existing["payment_id"])

    payment_id = db.execute(
        text(
            "INSERT INTO payments (tenant_id, amount_cents, description) "
            "VALUES (:t, :a, :d) RETURNING id"
        ),
        {"t": x_tenant_id, "a": body.amount_cents, "d": body.description},
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO idempotency_keys (tenant_id, key, request_hash, payment_id) "
            "VALUES (:t, :k, :h, :p)"
        ),
        {"t": x_tenant_id, "k": idempotency_key, "h": body_hash(body), "p": payment_id},
    )
    db.commit()
    response.status_code = 201
    return get_payment(db, payment_id)
