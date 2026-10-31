DROP TABLE IF EXISTS attachments CASCADE;

CREATE TABLE attachments (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    uploaded_at TIMESTAMP NOT NULL
);

INSERT INTO attachments (tenant_id, name, uploaded_at) VALUES
    (1, 'invoice-001.txt',      '2026-01-05 10:00:00'),
    (1, 'receipts/2026-01.txt', '2026-02-01 09:00:00'),
    (2, 'contract.txt',         '2026-01-10 12:00:00'),
    (2, 'invoice-104.txt',      '2026-01-12 15:30:00');
