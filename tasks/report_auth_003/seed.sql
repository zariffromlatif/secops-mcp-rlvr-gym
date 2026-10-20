DROP TABLE IF EXISTS invoices CASCADE;

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

INSERT INTO invoices (tenant_id, customer, amount_cents, status, created_at) VALUES
    (1, 'Acme Ltd',      12000, 'paid',    '2026-01-05 10:00:00'),
    (1, 'Bolt Traders',   4500, 'pending', '2026-01-09 09:30:00'),
    (1, 'Cedar Foods',   98000, 'paid',    '2026-02-01 14:15:00'),
    (1, 'Delta Print',    2300, 'overdue', '2026-02-11 08:00:00'),
    (1, 'Echo Labs',     51000, 'pending', '2026-03-03 16:45:00'),
    (2, 'Falcon Air',    77000, 'paid',    '2026-01-07 11:00:00'),
    (2, 'Grove Cafe',     1900, 'pending', '2026-01-20 12:00:00'),
    (2, 'Harbor Steel', 150000, 'overdue', '2026-02-14 10:30:00'),
    (2, 'Iris Health',   33000, 'paid',    '2026-03-01 09:00:00');

DROP TABLE IF EXISTS api_keys CASCADE;

CREATE TABLE api_keys (
    key TEXT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO api_keys (key, tenant_id, revoked) VALUES
    ('key-tenant-1-live',    1, FALSE),
    ('key-tenant-2-live',    2, FALSE),
    ('key-tenant-1-revoked', 1, TRUE);
