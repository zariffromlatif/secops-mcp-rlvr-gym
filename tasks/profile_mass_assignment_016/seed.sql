DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    role TEXT NOT NULL,
    credit_cents INTEGER NOT NULL
);

INSERT INTO users VALUES
    (1, 1, 'rahim@acme.test', 'Rahim', 'Asia/Dhaka',    'member', 0),
    (2, 1, 'nadia@acme.test', 'Nadia', 'UTC',           'admin',  5000),
    (3, 2, 'karim@bolt.test', 'Karim', 'Europe/London', 'member', 1200);
