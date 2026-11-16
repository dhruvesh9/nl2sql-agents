# Title
Join customers to addresses (two join paths)

# Keywords
address, billing address, installation address, city, postcode, customers in a city

# When to use
Use this runbook when a question needs an address of a customer.

# Rule
- `customers` has two foreign keys to `addresses`: `billing_address_id` and `installation_address_id`.
- Choose the path from the words in the question:
  - "billing address", "invoice address", or no clear word: use `billing_address_id`.
  - "installation address", "service address", or "where the service is installed": use `installation_address_id`.
- To use both addresses in one query, join `addresses` twice with two different aliases.
- Never join with both conditions on one alias.

# SQL example
```sql
-- Customers with an installation address in London
SELECT c.name
FROM customers c
JOIN addresses a ON a.id = c.installation_address_id
WHERE a.city = 'London';
```
