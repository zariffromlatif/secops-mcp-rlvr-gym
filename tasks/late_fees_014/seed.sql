DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;

CREATE TABLE invoices (id TEXT PRIMARY KEY, customer TEXT NOT NULL, total_cents INTEGER NOT NULL, due_date DATE NOT NULL);
CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    invoice_id TEXT NOT NULL REFERENCES invoices(id),
    amount_cents INTEGER NOT NULL,
    paid_on DATE NOT NULL
);

INSERT INTO invoices VALUES
    ('INV-10', 'Meghna Traders', 50000, '2026-01-01'),
    ('INV-11', 'Padma Foods',    30000, '2026-01-01'),
    ('INV-12', 'Jamuna Textiles', 80000, '2026-01-01'),
    ('INV-13', 'Karnaphuli Ltd', 10000, '2025-01-01'),
    ('INV-14', 'Surma Tea',      12325, '2026-01-01');

INSERT INTO payments (invoice_id, amount_cents, paid_on) VALUES
    ('INV-11', 30000, '2026-01-03'),
    ('INV-12', 50000, '2026-01-02');
