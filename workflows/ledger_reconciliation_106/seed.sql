INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1, 2000, 'refunded',  'wh_6001', '2026-04-02 10:00:00'),  -- 1  credit 2000          -> ok
    (2, 3000, 'refunded',  'wh_6002', '2026-04-03 10:00:00'),  -- 2  no credit            -> missing credit
    (3, 4000, 'refunded',  'wh_6003', '2026-04-04 10:00:00'),  -- 3  credit 1500          -> amount mismatch
    (4, 2500, 'succeeded', 'wh_6004', '2026-04-05 10:00:00'),  -- 4  credit 2500          -> credit without refund
    (5, 1800, 'refunded',  'wh_6005', '2026-04-06 10:00:00'),  -- 5  credits 1000 + 800   -> ok (partial credits)
    (1, 5000, 'failed',    'wh_6006', '2026-04-07 10:00:00'),  -- 6  failed, no credit    -> ok
    (2, 1200, 'succeeded', 'wh_6007', '2026-04-08 10:00:00'),  -- 7  succeeded, no credit -> ok
    (3,  900, 'refunded',  'wh_6008', '2026-04-09 10:00:00'),  -- 8  no credit, open ticket exists -> counted, no new ticket
    (4,  700, 'refunded',  'wh_6009', '2026-04-10 10:00:00'),  -- 9  credit 700 twice     -> amount mismatch
    (5, 3300, 'refunded',  'wh_6010', '2026-04-11 10:00:00'),  -- 10 no credit, only a closed ticket -> missing credit
    (1,  600, 'succeeded', 'wh_6011', '2026-04-12 10:00:00');  -- 11 credit 600          -> credit without refund

INSERT INTO ledger_credits (customer_id, payment_id, amount_cents, reason) VALUES
    (1,  1, 2000, 'refund'),
    (3,  3, 1500, 'refund'),
    (4,  4, 2500, 'refund'),
    (5,  5, 1000, 'partial refund'),
    (5,  5,  800, 'partial refund'),
    (4,  9,  700, 'refund'),
    (4,  9,  700, 'refund (retried)'),
    (1, 11,  600, 'refund');

INSERT INTO tickets (customer_id, title, body, status, linked_payment_id, resolution) VALUES
    (3, 'Ledger: missing credit', 'Payment 8 has no ledger credit.', 'open', 8, NULL),                       -- 1
    (5, 'Ledger: missing credit', 'Payment 10 has no ledger credit.', 'closed', 10, 'credit will be added'), -- 2
    (2, 'Where is my refund?', 'My refund for the April order has not arrived.', 'open', 2, NULL);           -- 3
