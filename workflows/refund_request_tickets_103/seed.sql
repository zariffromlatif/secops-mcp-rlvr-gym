INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1, 2000, 'succeeded', 'wh_3001', '2026-03-20 10:00:00'),  -- 1 eligible
    (2, 3500, 'succeeded', 'wh_3002', '2026-02-10 10:00:00'),  -- 2 too old
    (3, 1800, 'refunded',  'wh_3003', '2026-03-15 10:00:00'),  -- 3 already refunded
    (4,  900, 'succeeded', 'wh_3004', '2026-03-29 10:00:00'),  -- 4 eligible
    (5, 1200, 'succeeded', 'wh_3005', '2026-03-25 10:00:00'),  -- 5 not part of any request
    (5, 5000, 'succeeded', 'wh_3006', '2026-03-28 10:00:00');  -- 6 linked to an already closed ticket

INSERT INTO ledger_credits (customer_id, payment_id, amount_cents, reason) VALUES
    (3, 3, 1800, 'refunded by phone on 2026-03-16');

INSERT INTO tickets (customer_id, title, body, status, linked_payment_id, resolution) VALUES
    (1, 'Refund request: double-charged order', 'I was charged twice.', 'open', 1, NULL),
    (2, 'Refund request: cancelled subscription', 'I cancelled in February.', 'open', 2, NULL),
    (3, 'Refund request: item not received', 'Never arrived.', 'open', 3, NULL),
    (4, 'Refund request: wrong plan purchased', 'Bought the wrong plan.', 'open', 4, NULL),
    (5, 'Login problem', 'Cannot log in.', 'open', NULL, NULL),
    (5, 'Refund request: duplicate order', 'Ordered twice.', 'closed', 6, 'handled by phone');
