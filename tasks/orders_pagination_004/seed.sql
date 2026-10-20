DROP TABLE IF EXISTS orders CASCADE;

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    total_cents INTEGER NOT NULL
);

INSERT INTO orders (customer, total_cents) VALUES
    ('Acme Ltd', 1200), ('Bolt Traders', 450), ('Cedar Foods', 9800),
    ('Delta Print', 230), ('Echo Labs', 5100), ('Falcon Air', 7700),
    ('Grove Cafe', 190), ('Harbor Steel', 15000), ('Iris Health', 3300);
