DROP TABLE IF EXISTS webhook_events CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS settings CASCADE;

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    customer TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE webhook_events (
    event_id TEXT PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    received_at TIMESTAMP NOT NULL DEFAULT now()
);

INSERT INTO settings VALUES ('webhook_secret', 'whsec_test_9f3c');
INSERT INTO invoices VALUES
    (1, 'Acme Ltd',     12000, 'open'),
    (2, 'Bolt Traders',  4500, 'open'),
    (3, 'Cedar Foods',   9800, 'paid');
