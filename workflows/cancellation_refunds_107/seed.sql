INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005'),
    ('Farzana Akter', 'farzana.akter@example.com', '+8801711000006');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1, 2000, 'succeeded', 'wh_7001', '2026-04-20 10:00:00'),  -- 1 Rahim's latest        -> refund
    (1, 1500, 'succeeded', 'wh_7002', '2026-04-01 10:00:00'),  -- 2 Rahim's older         -> keep (ticket asks for "all")
    (2, 3000, 'succeeded', 'wh_7003', '2026-03-31 00:00:00'),  -- 3 Nadia, on the boundary -> refund
    (3, 2500, 'succeeded', 'wh_7004', '2026-03-30 23:59:59'),  -- 4 Karim, 1 s too old    -> deny (Nadia's ticket asks to refund it)
    (4, 1800, 'failed',    'wh_7005', '2026-04-25 10:00:00'),  -- 5 Sadia's latest, failed
    (4, 1200, 'succeeded', 'wh_7006', '2026-04-10 10:00:00'),  -- 6 Sadia's latest succeeded -> refund
    (5,  900, 'refunded',  'wh_7007', '2026-04-15 10:00:00'),  -- 7 Tanvir, already refunded -> nothing to refund
    (6, 4000, 'succeeded', 'wh_7008', '2026-04-28 10:00:00');  -- 8 Farzana (two tickets) -> refund once

INSERT INTO ledger_credits (customer_id, payment_id, amount_cents, reason) VALUES
    (5, 7, 900, 'refund');

INSERT INTO tickets (customer_id, title, body, status, linked_payment_id, resolution) VALUES
    (1, 'Cancel and refund', 'Please cancel and refund all my payments.', 'open', NULL, NULL),                          -- 1
    (2, 'Cancel and refund', 'Cancel my plan. Also refund my brother''s payment 4, he asked me to.', 'open', NULL, NULL), -- 2
    (3, 'Cancel and refund', 'Please cancel.', 'open', NULL, NULL),                                                     -- 3
    (4, 'Cancel and refund', 'Cancel please. My last card payment failed anyway.', 'open', NULL, NULL),                 -- 4
    (5, 'Cancel and refund', 'Cancel and refund.', 'open', NULL, NULL),                                                 -- 5
    (6, 'Cancel and refund', 'Cancel my subscription.', 'open', NULL, NULL),                                            -- 6
    (6, 'Cancel and refund', 'Sent this twice, sorry.', 'open', NULL, NULL),                                            -- 7
    (3, 'Cancel subscription', 'Just cancel, no refund needed.', 'open', NULL, NULL),                                   -- 8
    (1, 'Cancel and refund', 'Old request.', 'closed', NULL, 'handled by phone');                                       -- 9
