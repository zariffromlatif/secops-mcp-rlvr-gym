INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005'),
    ('Mitu Akter',    'mitu.akter@example.com',    '+8801711000006');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1,  6000, 'succeeded', 'wh_4001', '2026-01-10 09:00:00'),  -- 1  Rahim Q1
    (1,  5000, 'succeeded', 'wh_4002', '2026-03-02 09:00:00'),  -- 2  Rahim Q1      -> Rahim 110.00
    (2,  8000, 'succeeded', 'wh_4003', '2026-02-14 09:00:00'),  -- 3  Nadia Q1
    (2,  4000, 'refunded',  'wh_4004', '2026-02-20 09:00:00'),  -- 4  refunded: not spend -> Nadia 80.00
    (3,  2000, 'succeeded', 'wh_4005', '2026-02-01 09:00:00'),  -- 5  Karim Q1
    (3, 12000, 'succeeded', 'wh_4006', '2026-04-01 00:10:00'),  -- 6  Q2, not Q1    -> Karim 20.00
    (4, 15000, 'succeeded', 'wh_4007', '2026-03-31 23:30:00'),  -- 7  last minutes of Q1 -> Sadia 150.00
    (5, 20000, 'succeeded', 'wh_4008', '2026-01-05 09:00:00'),  -- 8  Tanvir 200.00 but no open ticket
    (6,  9000, 'succeeded', 'wh_4009', '2026-01-20 09:00:00'),  -- 9  Mitu
    (6,  1000, 'succeeded', 'wh_4010', '2026-03-15 09:00:00'),  -- 10 Mitu           -> exactly 100.00
    (6,  5000, 'failed',    'wh_4011', '2026-03-16 09:00:00'),  -- 11 failed: not spend
    (1,  5000, 'succeeded', 'wh_4012', '2025-12-31 23:50:00');  -- 12 Q4 2025, not Q1

INSERT INTO tickets (customer_id, title, body, status, linked_payment_id, resolution) VALUES
    (1, 'Invoice copy needed', 'Please resend January invoice.', 'open', NULL, NULL),      -- 1
    (2, 'Card declined', 'My card keeps failing.', 'open', NULL, NULL),                    -- 2
    (4, 'Change plan', 'Want to move to annual.', 'open', NULL, NULL),                     -- 3
    (1, 'Invoice copy needed', 'Still waiting for the invoice.', 'open', NULL, NULL),      -- 4 duplicate of 1
    (2, 'Card declined', 'Same problem as before.', 'closed', NULL, 'resolved by phone'),  -- 5
    (4, 'Change plan', 'Following up on plan change.', 'open', NULL, NULL),                -- 6 duplicate of 3
    (1, 'invoice copy needed', 'Need the February one too.', 'open', NULL, NULL),          -- 7 different title (case)
    (4, 'Change plan', 'Any update?', 'open', NULL, NULL),                                 -- 8 duplicate of 3
    (3, 'Login issue', 'Cannot sign in.', 'open', NULL, NULL),                             -- 9
    (6, 'Refund status', 'Where is my refund?', 'open', NULL, NULL),                       -- 10
    (5, 'Upgrade question', 'Which plan fits?', 'closed', NULL, 'answered');               -- 11
