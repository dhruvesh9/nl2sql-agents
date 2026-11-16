# Title
Join usage_records to subscriptions (missing foreign key)

# Keywords
usage, calls, SMS, data, msisdn, phone number, subscription, usage by customer

# When to use
Use this runbook when a question needs usage data together with subscription, account, or customer data.

# Rule
- `usage_records.msisdn` matches `subscriptions.msisdn`.
- The database has NO foreign key for this link. The schema does not show it.
- Join on `msisdn` only. Do not join on `id` columns.
- To reach the account or customer, go on from subscriptions: `subscriptions.account_id` -> `accounts.id` -> `accounts.customer_id` -> `customers.id`.

# SQL example
```sql
-- Total data usage in MB per account
SELECT s.account_id, SUM(u.quantity) AS total_mb
FROM usage_records u
JOIN subscriptions s ON s.msisdn = u.msisdn
WHERE u.usage_type = 'DATA'
GROUP BY s.account_id;
```
