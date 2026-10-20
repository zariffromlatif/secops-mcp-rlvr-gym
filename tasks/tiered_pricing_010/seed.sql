DROP TABLE IF EXISTS tiers CASCADE;

CREATE TABLE tiers (
    product TEXT NOT NULL,
    position INTEGER NOT NULL,
    up_to INTEGER,
    unit_cents INTEGER NOT NULL,
    PRIMARY KEY (product, position)
);

INSERT INTO tiers VALUES
    ('api_calls', 1, 1000, 10),
    ('api_calls', 2, 10000, 8),
    ('api_calls', 3, NULL, 5),
    ('seats', 1, 5, 2000),
    ('seats', 2, NULL, 1500);
