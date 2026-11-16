# Title
Active customer rule

# Keywords
active customer, current customer, open customer, customers who left, closed customer

# When to use
Use this runbook when a question says "active", "current", or "open" customers.
Use it also for "inactive" or "closed" customers (use the opposite condition).

# Rule
- A customer is active when `customers.status = 'A'` AND `customers.closed_date IS NULL`.
- Use both conditions. Some customers with another status still have a closed_date, so one condition alone gives wrong results.
- Status codes: `A` active, `S` suspended, `C` closed.

# SQL example
```sql
-- Count of active customers
SELECT COUNT(*)
FROM customers
WHERE status = 'A' AND closed_date IS NULL;
```
