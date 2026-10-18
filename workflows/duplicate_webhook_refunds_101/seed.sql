INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1, 2500, 'succeeded', 'wh_1001', '2026-03-30 09:00:00'),  -- 1 original
    (1, 2500, 'succeeded', 'wh_1001', '2026-03-30 09:00:04'),  -- 2 duplicate
    (2, 4000, 'succeeded', 'wh_1002', '2026-03-30 10:00:00'),  -- 3 single
    (3, 1500, 'succeeded', 'wh_1003', '2026-03-30 11:00:00'),  -- 4 original
    (3, 1500, 'succeeded', 'wh_1003', '2026-03-30 11:00:02'),  -- 5 duplicate
    (3, 1500, 'succeeded', 'wh_1003', '2026-03-30 11:00:09'),  -- 6 duplicate
    (4, 1500, 'succeeded', 'wh_1004', '2026-03-30 12:00:00'),  -- 7 single
    (4, 1500, 'succeeded', 'wh_1005', '2026-03-30 12:30:00'),  -- 8 real second purchase (different webhook)
    (5, 3000, 'failed',    'wh_1006', '2026-03-30 13:00:00'),  -- 9 failed attempt
    (5, 3000, 'succeeded', 'wh_1006', '2026-03-30 13:01:00');  -- 10 retry that succeeded (only one charge)
