DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS plans CASCADE;

CREATE TABLE plans (id INTEGER PRIMARY KEY, name TEXT NOT NULL, monthly_cents INTEGER NOT NULL);
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    customer TEXT NOT NULL,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL
);

INSERT INTO plans VALUES (1, 'Basic', 2900), (2, 'Pro', 9000), (3, 'Team', 30000), (4, 'Starter', 1001);
INSERT INTO subscriptions VALUES
    (1, 'Acme Ltd',     1, '2026-04-01', '2026-05-01'),
    (2, 'Bolt Traders', 1, '2028-02-01', '2028-03-01'),
    (3, 'Cedar Foods',  2, '2026-01-01', '2026-02-01'),
    (4, 'Delta Print',  2, '2026-06-01', '2026-07-01'),
    (5, 'Echo Labs',    4, '2026-09-01', '2026-10-01');
