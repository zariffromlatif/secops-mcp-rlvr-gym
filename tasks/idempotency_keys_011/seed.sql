DROP TABLE IF EXISTS idempotency_keys CASCADE;
DROP TABLE IF EXISTS payments CASCADE;

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE idempotency_keys (
    tenant_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payment_id INTEGER NOT NULL REFERENCES payments(id),
    PRIMARY KEY (tenant_id, key)
);
