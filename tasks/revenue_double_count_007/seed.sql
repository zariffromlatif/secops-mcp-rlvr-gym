DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount_cents INTEGER NOT NULL
);

INSERT INTO invoices (customer, amount_cents, status) VALUES
    ('Acme Ltd',     10000, 'paid'),     -- 1: one payment
    ('Acme Ltd',      5000, 'paid'),     -- 2: two payments
    ('Bolt Traders',  8000, 'paid'),     -- 3: one payment
    ('Cedar Foods',   3000, 'pending'),  -- 4: not paid
    ('Bolt Traders',  6000, 'paid'),     -- 5: three payments
    ('Dune Studio',   4000, 'paid'),     -- 6: one payment
    ('Eve Logistics', 7000, 'paid');     -- 7: marked paid but no payment recorded

INSERT INTO payments (invoice_id, amount_cents) VALUES
    (1, 10000),
    (2, 2000), (2, 3000),
    (3, 8000),
    (5, 1000), (5, 2000), (5, 3000),
    (6, 4000);
