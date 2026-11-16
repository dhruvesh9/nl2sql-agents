-- Sample data. Only generate_series and fixed formulas are used, so the data is the same on every load.

-- 150 addresses
INSERT INTO addresses (id, line1, city, postcode, country)
SELECT g,
       (10 + g) || ' High Street',
       (ARRAY['London','Manchester','Leeds','Bristol','Glasgow'])[1 + g % 5],
       'AB' || lpad((g % 90 + 10)::text, 2, '0') || ' ' || (1 + g % 9) || 'XY',
       'GB'
FROM generate_series(1, 150) AS g;

-- 100 customers. About 70% active, 15% suspended, 15% closed.
-- Closed customers have a closed_date. One suspended customer in ten has a closed_date too (dirty data on purpose).
INSERT INTO customers (id, name, email, status, created_date, closed_date, billing_address_id, installation_address_id)
SELECT g,
       'Customer ' || lpad(g::text, 3, '0'),
       'customer' || g || '@example.com',
       CASE WHEN g % 20 < 14 THEN 'A' WHEN g % 20 < 17 THEN 'S' ELSE 'C' END,
       DATE '2022-01-01' + (g * 7),
       CASE WHEN g % 20 >= 17 OR g % 20 = 14 THEN DATE '2024-06-01' + (g * 3) ELSE NULL END,
       g,
       101 + (g % 50)
FROM generate_series(1, 100) AS g;

-- 120 accounts
INSERT INTO accounts (id, customer_id, account_number, status, opened_date, currency)
SELECT g,
       (g - 1) % 100 + 1,
       'ACC' || lpad(g::text, 6, '0'),
       CASE WHEN g % 10 = 0 THEN 'CLOSED' WHEN g % 10 = 1 THEN 'SUSPENDED' ELSE 'ACTIVE' END,
       DATE '2022-02-01' + (g * 6),
       'GBP'
FROM generate_series(1, 120) AS g;

-- 12 products
INSERT INTO products (id, name, product_type, monthly_price)
SELECT g,
       CASE g % 3 WHEN 0 THEN 'Mobile Plan ' WHEN 1 THEN 'Broadband Plan ' ELSE 'Device Plan ' END || g,
       CASE g % 3 WHEN 0 THEN 'MOBILE' WHEN 1 THEN 'BROADBAND' ELSE 'DEVICE' END,
       (9 + g * 3)::numeric(10, 2)
FROM generate_series(1, 12) AS g;

-- 150 subscriptions. msisdn has a fixed pattern: 447700 + 4 digits.
INSERT INTO subscriptions (id, account_id, product_id, msisdn, start_date, end_date, status)
SELECT g,
       (g - 1) % 120 + 1,
       (g - 1) % 12 + 1,
       '447700' || lpad(g::text, 4, '0'),
       DATE '2023-01-01' + (g * 4),
       CASE WHEN g % 8 = 0 THEN DATE '2025-03-01' + g ELSE NULL END,
       CASE WHEN g % 8 = 0 THEN 'ENDED' WHEN g % 11 = 0 THEN 'SUSPENDED' ELSE 'ACTIVE' END
FROM generate_series(1, 150) AS g;

-- 100 orders
INSERT INTO orders (id, account_id, order_date, status, total_amount)
SELECT g,
       (g - 1) % 120 + 1,
       DATE '2024-01-01' + (g * 5),
       CASE g % 3 WHEN 0 THEN 'DONE' WHEN 1 THEN 'SHIPPED' ELSE 'NEW' END,
       0
FROM generate_series(1, 100) AS g;

-- 200 order items (two per order)
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price)
SELECT g,
       (g - 1) % 100 + 1,
       (g - 1) % 12 + 1,
       1 + g % 3,
       (9 + ((g - 1) % 12 + 1) * 3)::numeric(10, 2)
FROM generate_series(1, 200) AS g;

-- Set order totals from the items, so the data is consistent.
UPDATE orders o
SET total_amount = (SELECT sum(quantity * unit_price) FROM order_items i WHERE i.order_id = o.id);

-- 200 invoices. Status codes: P paid (60%), O open (30%), C cancelled (10%).
INSERT INTO invoices (id, account_id, invoice_number, invoice_date, due_date, total_amount, status)
SELECT g,
       (g - 1) % 120 + 1,
       'INV' || lpad(g::text, 6, '0'),
       DATE '2025-01-01' + (g % 360),
       DATE '2025-01-01' + (g % 360) + 30,
       (20 + (g * 7) % 90)::numeric(10, 2),
       CASE WHEN g % 10 < 6 THEN 'P' WHEN g % 10 < 9 THEN 'O' ELSE 'C' END
FROM generate_series(1, 200) AS g;

-- 200 invoice lines (two lines for each of the first 100 invoices)
INSERT INTO invoice_lines (id, invoice_id, subscription_id, description, amount)
SELECT g,
       (g - 1) % 100 + 1,
       (g - 1) % 150 + 1,
       'Monthly charge ' || g,
       (10 + (g * 3) % 40)::numeric(10, 2)
FROM generate_series(1, 200) AS g;

-- 120 payments, one for each paid invoice
INSERT INTO payments (id, invoice_id, payment_date, amount, method)
SELECT row_number() OVER (ORDER BY i.id),
       i.id,
       i.invoice_date + 10,
       i.total_amount,
       CASE i.id % 3 WHEN 0 THEN 'CARD' WHEN 1 THEN 'BANK' ELSE 'CASH' END
FROM invoices i
WHERE i.status = 'P';

-- 200 usage records. msisdn values match subscriptions.msisdn, but no foreign key exists.
INSERT INTO usage_records (id, msisdn, usage_type, quantity, unit, usage_time, cost)
SELECT g,
       '447700' || lpad(((g - 1) % 150 + 1)::text, 4, '0'),
       CASE g % 3 WHEN 0 THEN 'VOICE' WHEN 1 THEN 'SMS' ELSE 'DATA' END,
       (1 + (g * 13) % 500)::numeric(12, 2),
       CASE g % 3 WHEN 0 THEN 'MIN' WHEN 1 THEN 'COUNT' ELSE 'MB' END,
       TIMESTAMP '2025-01-01 00:00:00' + (g * interval '37 hours'),
       ((1 + (g * 13) % 500) * 0.01)::numeric(10, 4)
FROM generate_series(1, 200) AS g;

-- ---------------------------------------------------------------------------
-- Extra tables. Same rule: fixed formulas only, so the data is the same on every load.
-- ---------------------------------------------------------------------------

-- 120 payment methods, one for each account
INSERT INTO payment_methods (id, account_id, method_type, last4, is_default, created_date)
SELECT g, g,
       CASE g % 2 WHEN 0 THEN 'CARD' ELSE 'BANK' END,
       lpad(((g * 37) % 10000)::text, 4, '0'),
       TRUE,
       DATE '2022-03-01' + (g * 5)
FROM generate_series(1, 120) AS g;

-- Refunds: one for every 8th payment (15 rows). The refund is half of the payment.
INSERT INTO refunds (id, payment_id, amount, reason, refund_date, status)
SELECT row_number() OVER (ORDER BY p.id),
       p.id,
       round(p.amount / 2, 2),
       CASE p.id % 3 WHEN 0 THEN 'Billing error' WHEN 1 THEN 'Service outage' ELSE 'Customer request' END,
       p.payment_date + 5,
       CASE p.id % 4 WHEN 0 THEN 'PENDING' WHEN 1 THEN 'REJECTED' ELSE 'DONE' END
FROM payments p
WHERE p.id % 8 = 0;

-- Credit notes: one for every 20th invoice (10 rows). The credit is 25% of the invoice.
INSERT INTO credit_notes (id, invoice_id, amount, reason, issued_date)
SELECT row_number() OVER (ORDER BY i.id),
       i.id,
       round(i.total_amount * 0.25, 2),
       CASE i.id % 2 WHEN 0 THEN 'Billing error' ELSE 'Goodwill' END,
       i.invoice_date + 20
FROM invoices i
WHERE i.id % 20 = 0;

-- 20 payment plans, each with 3 instalments
INSERT INTO payment_plans (id, account_id, total_amount, instalment_count, start_date, status)
SELECT g, g * 5,
       (100 + g * 20)::numeric(10, 2),
       3,
       DATE '2025-02-01' + (g * 10),
       CASE WHEN g % 5 = 0 THEN 'DEFAULTED' WHEN g % 2 = 0 THEN 'DONE' ELSE 'ACTIVE' END
FROM generate_series(1, 20) AS g;

-- 60 instalments (3 for each plan)
INSERT INTO payment_plan_installments (id, payment_plan_id, due_date, amount, status)
SELECT (p.id - 1) * 3 + k,
       p.id,
       p.start_date + k * 30,
       round(p.total_amount / 3, 2),
       CASE WHEN k = 1 THEN 'PAID' WHEN k = 2 AND p.id % 3 = 0 THEN 'LATE' ELSE 'DUE' END
FROM payment_plans p
CROSS JOIN generate_series(1, 3) AS k;

-- 60 direct debit mandates
INSERT INTO direct_debit_mandates (id, account_id, bank_name, signed_date, status)
SELECT g, g * 2,
       (ARRAY['Barclays','Lloyds','HSBC','NatWest'])[1 + g % 4],
       DATE '2022-06-01' + (g * 9),
       CASE WHEN g % 6 = 0 THEN 'CANCELLED' ELSE 'ACTIVE' END
FROM generate_series(1, 60) AS g;

-- Collections cases: every 4th open invoice. Cases get the status OPEN, CLOSED, or WRITTEN_OFF.
INSERT INTO collections_cases (id, account_id, invoice_id, amount_due, opened_date, closed_date, status)
SELECT n,
       account_id,
       invoice_id,
       total_amount,
       due_date + 15,
       CASE WHEN n % 3 = 0 THEN NULL ELSE due_date + 60 END,
       CASE n % 3 WHEN 0 THEN 'OPEN' WHEN 1 THEN 'CLOSED' ELSE 'WRITTEN_OFF' END
FROM (
    SELECT row_number() OVER (ORDER BY i.id) AS n,
           i.account_id, i.id AS invoice_id, i.total_amount, i.due_date
    FROM invoices i
    WHERE i.status = 'O' AND i.id % 4 = 0
) AS open_invoices;

-- 8 discounts
INSERT INTO discounts (id, code, description, percent_off, valid_from, valid_to)
SELECT g,
       'DISC' || lpad(g::text, 2, '0'),
       (5 * g) || ' percent off for new customers',
       (5 * g)::numeric(5, 2),
       DATE '2025-01-01',
       CASE WHEN g % 3 = 0 THEN DATE '2025-06-30' ELSE NULL END
FROM generate_series(1, 8) AS g;

-- 40 discounts applied to subscriptions
INSERT INTO subscription_discounts (id, subscription_id, discount_id, applied_date)
SELECT g, g * 3, (g - 1) % 8 + 1, DATE '2025-01-15' + (g * 5)
FROM generate_series(1, 40) AS g;

-- 10 support agents
INSERT INTO support_agents (id, name, team)
SELECT g,
       'Agent ' || lpad(g::text, 2, '0'),
       (ARRAY['BILLING','TECHNICAL','SALES'])[1 + g % 3]
FROM generate_series(1, 10) AS g;

-- 150 support tickets. Every 10th ticket has no account. Every 7th ticket has no agent.
INSERT INTO support_tickets (id, customer_id, account_id, agent_id, subject, status, priority, opened_date, closed_date)
SELECT g,
       (g - 1) % 100 + 1,
       CASE WHEN g % 10 = 0 THEN NULL ELSE (g - 1) % 100 + 1 END,
       CASE WHEN g % 7 = 0 THEN NULL ELSE (g - 1) % 10 + 1 END,
       (ARRAY['Wrong invoice amount','No signal','Slow broadband','Change my plan','Lost phone'])[1 + g % 5],
       (ARRAY['OPEN','PENDING','RESOLVED'])[1 + g % 3],
       (ARRAY['LOW','MEDIUM','HIGH','MEDIUM'])[1 + (g * 5) % 4],
       DATE '2025-01-01' + (g * 2),
       CASE WHEN g % 3 = 2 THEN DATE '2025-01-01' + (g * 2) + 3 ELSE NULL END
FROM generate_series(1, 150) AS g;

-- 150 SIM cards, one for each subscription
INSERT INTO sim_cards (id, subscription_id, iccid, status, activated_date)
SELECT g, g,
       '894410' || lpad(g::text, 12, '0'),
       CASE WHEN g % 15 = 0 THEN 'BLOCKED' ELSE 'ACTIVE' END,
       DATE '2023-01-01' + (g * 4)
FROM generate_series(1, 150) AS g;

-- 60 devices on every second subscription
INSERT INTO devices (id, subscription_id, imei, model, status)
SELECT g, g * 2,
       '35' || lpad(g::text, 13, '0'),
       (ARRAY['Pixel 8','iPhone 15','Galaxy S24','Home Router X'])[1 + g % 4],
       CASE WHEN g % 10 = 0 THEN 'LOST' WHEN g % 10 = 1 THEN 'RETURNED' ELSE 'ACTIVE' END
FROM generate_series(1, 60) AS g;

-- Tax rates
INSERT INTO tax_rates (id, country, tax_name, rate_percent, valid_from) VALUES
    (1, 'GB', 'VAT',         20.00, DATE '2011-01-04'),
    (2, 'GB', 'VAT reduced',  5.00, DATE '2011-01-04'),
    (3, 'IE', 'VAT',         23.00, DATE '2012-01-01'),
    (4, 'FR', 'TVA',         20.00, DATE '2014-01-01');
