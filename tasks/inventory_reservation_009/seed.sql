DROP TABLE IF EXISTS reservations CASCADE;
DROP TABLE IF EXISTS products CASCADE;

CREATE TABLE products (sku TEXT PRIMARY KEY, name TEXT NOT NULL, stock INTEGER NOT NULL);
CREATE TABLE reservations (
    id SERIAL PRIMARY KEY,
    order_ref TEXT NOT NULL,
    sku TEXT NOT NULL REFERENCES products(sku),
    qty INTEGER NOT NULL,
    status TEXT NOT NULL
);

INSERT INTO products VALUES ('PEN-01', 'Gel pen', 5), ('BOOK-02', 'Notebook', 10), ('LAMP-03', 'Desk lamp', 2);
