# Title
Invoice status codes

# Keywords
invoice, unpaid, open invoice, paid, cancelled, overdue, outstanding, status

# When to use
Use this runbook when a question filters invoices by payment state.

# Rule
- `invoices.status` is a one-letter code: `O` open (unpaid), `P` paid, `C` cancelled.
- "Unpaid" or "outstanding" means `status = 'O'`.
- Do not count cancelled invoices (`C`) as unpaid. Exclude them from money totals.
- "Overdue" means `status = 'O'` AND `due_date < CURRENT_DATE`.

# SQL example
```sql
-- Total unpaid invoice amount per account
SELECT account_id, SUM(total_amount) AS unpaid_amount
FROM invoices
WHERE status = 'O'
GROUP BY account_id;
```
