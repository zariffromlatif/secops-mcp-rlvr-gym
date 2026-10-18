INSERT INTO customers (name, email, phone) VALUES
    ('Rahim Uddin',   'rahim.uddin@example.com',   '+8801711000001'),
    ('Nadia Islam',   'nadia.islam@example.com',   '+8801711000002'),
    ('Karim Hossain', 'karim.hossain@example.com', '+8801711000003'),
    ('Sadia Ahmed',   'sadia.ahmed@example.com',   '+8801711000004'),
    ('Tanvir Rahman', 'tanvir.rahman@example.com', '+8801711000005');

INSERT INTO payments (customer_id, amount_cents, status, webhook_id, created_at) VALUES
    (1, 2000, 'failed',    'wh_2001', '2026-03-05 10:00:00'),  -- 1
    (1, 2000, 'failed',    'wh_2002', '2026-03-12 10:00:00'),  -- 2
    (1, 2000, 'succeeded', 'wh_2003', '2026-03-13 10:00:00'),  -- 3
    (1, 2000, 'failed',    'wh_2004', '2026-03-20 10:00:00'),  -- 4 Rahim: 3 failures, latest
    (2, 1500, 'failed',    'wh_2005', '2026-03-02 09:00:00'),  -- 5
    (2, 1500, 'failed',    'wh_2006', '2026-03-09 09:00:00'),  -- 6
    (2, 1500, 'failed',    'wh_2007', '2026-03-16 09:00:00'),  -- 7
    (2, 1500, 'failed',    'wh_2008', '2026-03-23 09:00:00'),  -- 8 Nadia: already has an open ticket
    (3, 3000, 'failed',    'wh_2009', '2026-03-10 14:00:00'),  -- 9
    (3, 3000, 'failed',    'wh_2010', '2026-03-11 14:00:00'),  -- 10
    (3, 3000, 'succeeded', 'wh_2011', '2026-03-12 14:00:00'),  -- 11 Karim: only 2 failures
    (4,  800, 'failed',    'wh_2012', '2026-02-25 08:00:00'),  -- 12 February, does not count
    (4,  800, 'failed',    'wh_2013', '2026-03-03 08:00:00'),  -- 13
    (4,  800, 'failed',    'wh_2014', '2026-03-04 08:00:00'),  -- 14 Sadia: only 2 in March
    (5, 4500, 'failed',    'wh_2015', '2026-03-01 00:30:00'),  -- 15
    (5, 4500, 'failed',    'wh_2016', '2026-03-15 12:00:00'),  -- 16
    (5, 4500, 'failed',    'wh_2017', '2026-03-31 23:00:00');  -- 17 Tanvir: 3 failures, latest

INSERT INTO tickets (customer_id, title, body, status, linked_payment_id, resolution) VALUES
    (2, 'Repeated payment failures: Nadia Islam', 'Card keeps declining.', 'open', 7, NULL),
    (5, 'Repeated payment failures: Tanvir Rahman', 'Card expired.', 'closed', NULL, 'card replaced in January'),
    (3, 'Invoice address change', 'Please update billing address.', 'open', NULL, NULL);
