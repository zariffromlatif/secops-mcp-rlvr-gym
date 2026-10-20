DROP TABLE IF EXISTS invoices CASCADE;

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    amount_cents INTEGER NOT NULL
);

INSERT INTO invoices (customer, amount_cents) VALUES
    ('Acme Ltd', 12000),
    ('Bolt Traders', 10000),
    ('Cedar Foods', 101),
    ('Delta Print', 5);
