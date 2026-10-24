DROP TABLE IF EXISTS zones CASCADE;

CREATE TABLE zones (code TEXT PRIMARY KEY, name TEXT NOT NULL, cents_per_half_kg INTEGER NOT NULL);

INSERT INTO zones VALUES ('DHK', 'Dhaka city', 150), ('CTG', 'Chattogram', 200), ('INTL', 'International', 900);
