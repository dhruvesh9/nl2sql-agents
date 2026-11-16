# Knowledge base index

This is a telecom billing database. Use this file to find the runbooks that apply to a question.
The list of tables is in `tables.md`. The columns of each table come live from the database.

## Runbooks

| Runbook | Keywords | Description |
|---|---|---|
| `usage_subscriptions_link` | usage, calls, SMS, data, msisdn, phone number, subscription | How to join usage_records to subscriptions. There is no foreign key. |
| `active_customer` | active customer, current customer, open customer, closed customer | The business rule for an active customer. |
| `invoice_status` | invoice, unpaid, open, paid, cancelled, overdue, status | The meaning of the invoices.status codes O, P, and C. |
| `customer_address_join` | address, billing address, installation address, city, postcode | How to join customers to addresses. Two join paths exist. |

## Tables

See `tables.md` for one line per table.
