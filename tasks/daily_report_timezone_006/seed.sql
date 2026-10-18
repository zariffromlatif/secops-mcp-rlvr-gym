DROP TABLE IF EXISTS invoices;

-- created_at is stored in UTC.
CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    amount_cents INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL
);

INSERT INTO invoices (amount_cents, created_at) VALUES
    (100, '2026-02-28 17:30:00'),
    (200, '2026-02-28 18:30:00'),
    (300, '2026-03-01 05:00:00'),
    (400, '2026-03-01 17:59:00'),
    (500, '2026-03-01 18:00:00'),
    (600, '2026-03-02 09:00:00');
