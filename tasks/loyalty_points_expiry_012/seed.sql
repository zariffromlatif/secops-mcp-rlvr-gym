DROP TABLE IF EXISTS point_events CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE point_events (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    kind TEXT NOT NULL CHECK (kind IN ('earn', 'redeem')),
    points INTEGER NOT NULL CHECK (points > 0),
    occurred_on DATE NOT NULL
);

INSERT INTO customers VALUES
    (1, 'Ayesha'), (2, 'Bashir'), (3, 'Chandni'), (4, 'Dipu'), (5, 'Esha'), (6, 'Farhan'), (7, 'Gita');

INSERT INTO point_events (customer_id, kind, points, occurred_on) VALUES
    (1, 'earn',   200, '2025-11-01'),
    (1, 'redeem',  50, '2025-12-01'),
    (1, 'earn',   100, '2026-01-15'),
    (2, 'earn',    80, '2025-12-10'),
    (3, 'earn',   300, '2024-06-01'),
    (3, 'earn',   120, '2025-10-01'),
    (4, 'earn',   100, '2025-01-10'),
    (4, 'redeem',  60, '2025-06-01'),
    (4, 'earn',    50, '2025-09-01'),
    (5, 'earn',   100, '2025-01-10'),
    (5, 'earn',   100, '2025-12-01'),
    (5, 'redeem',  70, '2025-12-15'),
    (6, 'earn',    40, '2025-02-01'),
    (7, 'earn',    30, '2025-01-10'),
    (7, 'earn',   100, '2025-06-01'),
    (7, 'redeem',  50, '2025-12-15');
