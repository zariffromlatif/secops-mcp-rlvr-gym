INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1, 2000, 'succeeded', 'wh_5001', '2026-03-25 10:00:00'),  -- 1  6 days old        -> refund
    (2, 3000, 'succeeded', 'wh_5002', '2026-03-10 10:00:00'),  -- 2  21 days, no prior -> refund
    (3, 4000, 'succeeded', 'wh_5003', '2026-03-05 10:00:00'),  -- 3  26 days, prior credit -> deny
    (4, 1500, 'succeeded', 'wh_5004', '2026-02-20 10:00:00'),  -- 4  39 days            -> deny (too old)
    (5, 2500, 'succeeded', 'wh_5005', '2026-03-28 10:00:00'),  -- 5  newest of Tanvir's -> refund
    (5, 1800, 'succeeded', 'wh_5006', '2026-03-20 10:00:00'),  -- 6  Tanvir's second    -> deny (one per batch)
    (3,  900, 'refunded',  'wh_5007', '2026-01-15 10:00:00'),  -- 7  Karim's earlier refund
    (1, 5000, 'failed',    'wh_5008', '2026-03-29 10:00:00'),  -- 8  failed             -> deny
    (4, 1100, 'succeeded', 'wh_5009', '2026-03-17 00:00:00'),  -- 9  exactly 14 days    -> refund
    (2,  700, 'succeeded', 'wh_5010', '2026-03-30 10:00:00');  -- 10 no request

INSERT INTO ledger_credits (customer_id, payment_id, amount_cents, reason) VALUES
    (3, 7, 900, 'refunded by phone in January');

INSERT INTO tickets (customer_id, title, body, status, linked_payment_id, resolution) VALUES
    (1, 'Refund request: wrong size', 'Too small.', 'open', 1, NULL),                     -- 1
    (2, 'Refund request: not as described', 'Different colour.', 'open', 2, NULL),        -- 2
    (3, 'Refund request: changed mind', 'No longer needed.', 'open', 3, NULL),            -- 3
    (4, 'Refund request: late delivery', 'Arrived late.', 'open', 4, NULL),               -- 4
    (5, 'Refund request: duplicate order', 'Ordered twice by mistake.', 'open', 5, NULL), -- 5
    (5, 'Refund request: damaged item', 'Box was crushed.', 'open', 6, NULL),             -- 6
    (1, 'Refund request: charged twice', 'Saw two charges.', 'open', 8, NULL),            -- 7
    (4, 'Refund request: wrong colour', 'Blue not green.', 'open', 9, NULL),              -- 8
    (2, 'Billing address', 'Please update my address.', 'open', NULL, NULL),              -- 9
    (3, 'Refund request: old order', 'January order.', 'closed', 7, 'refunded by phone'); -- 10
