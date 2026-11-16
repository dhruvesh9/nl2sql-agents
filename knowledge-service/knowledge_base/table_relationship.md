Each line "A -> B" means that table A has a foreign key to table B, so A and B can be joined directly.
A link works in both directions. To connect two tables, follow the lines from one to the other.

customers -> addresses
accounts -> customers
subscriptions -> accounts
subscriptions -> products

orders -> accounts
order_items -> orders
order_items -> products

invoices -> accounts
invoice_lines -> invoices
invoice_lines -> subscriptions
payments -> invoices
refunds -> payments
credit_notes -> invoices

payment_methods -> accounts
payment_plans -> accounts
payment_plan_installments -> payment_plans
direct_debit_mandates -> accounts
collections_cases -> accounts
collections_cases -> invoices

subscription_discounts -> subscriptions
subscription_discounts -> discounts

support_tickets -> customers
support_tickets -> accounts
support_tickets -> support_agents

sim_cards -> subscriptions
devices -> subscriptions