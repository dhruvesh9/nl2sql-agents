-- Sample database: telecom billing (small).
-- It has four deliberate learning cases. See agent-service/knowledge_base/runbooks.
--   1. usage_records.msisdn links to subscriptions.msisdn, but there is NO foreign key.
--   2. "Active customer" is a business rule: status = 'A' AND closed_date IS NULL.
--   3. invoices.status uses codes: O open, P paid, C cancelled.
--   4. customers links to addresses twice (billing and installation), so a wrong JOIN is possible.

CREATE TABLE addresses (
    id          INTEGER PRIMARY KEY,
    line1       VARCHAR(100) NOT NULL,
    city        VARCHAR(60)  NOT NULL,
    postcode    VARCHAR(10)  NOT NULL,
    country     VARCHAR(2)   NOT NULL DEFAULT 'GB'
);

CREATE TABLE customers (
    id                         INTEGER PRIMARY KEY,
    name                       VARCHAR(100) NOT NULL,
    email                      VARCHAR(120) NOT NULL,
    status                     CHAR(1)      NOT NULL,
    created_date               DATE         NOT NULL,
    closed_date                DATE,
    billing_address_id         INTEGER NOT NULL REFERENCES addresses (id),
    installation_address_id    INTEGER NOT NULL REFERENCES addresses (id)
);

CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers (id),
    account_number  VARCHAR(20) NOT NULL UNIQUE,
    status          VARCHAR(10) NOT NULL,
    opened_date     DATE NOT NULL,
    currency        CHAR(3) NOT NULL DEFAULT 'GBP'
);

CREATE TABLE products (
    id             INTEGER PRIMARY KEY,
    name           VARCHAR(80) NOT NULL,
    product_type   VARCHAR(20) NOT NULL,
    monthly_price  NUMERIC(10, 2) NOT NULL
);

CREATE TABLE subscriptions (
    id          INTEGER PRIMARY KEY,
    account_id  INTEGER NOT NULL REFERENCES accounts (id),
    product_id  INTEGER NOT NULL REFERENCES products (id),
    msisdn      VARCHAR(15) NOT NULL UNIQUE,
    start_date  DATE NOT NULL,
    end_date    DATE,
    status      VARCHAR(10) NOT NULL
);

CREATE TABLE orders (
    id            INTEGER PRIMARY KEY,
    account_id    INTEGER NOT NULL REFERENCES accounts (id),
    order_date    DATE NOT NULL,
    status        VARCHAR(10) NOT NULL,
    total_amount  NUMERIC(10, 2) NOT NULL
);

CREATE TABLE order_items (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders (id),
    product_id  INTEGER NOT NULL REFERENCES products (id),
    quantity    INTEGER NOT NULL,
    unit_price  NUMERIC(10, 2) NOT NULL
);

CREATE TABLE invoices (
    id              INTEGER PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts (id),
    invoice_number  VARCHAR(20) NOT NULL UNIQUE,
    invoice_date    DATE NOT NULL,
    due_date        DATE NOT NULL,
    total_amount    NUMERIC(10, 2) NOT NULL,
    status          CHAR(1) NOT NULL
);

CREATE TABLE invoice_lines (
    id               INTEGER PRIMARY KEY,
    invoice_id       INTEGER NOT NULL REFERENCES invoices (id),
    subscription_id  INTEGER REFERENCES subscriptions (id),
    description      VARCHAR(120) NOT NULL,
    amount           NUMERIC(10, 2) NOT NULL
);

CREATE TABLE payments (
    id            INTEGER PRIMARY KEY,
    invoice_id    INTEGER NOT NULL REFERENCES invoices (id),
    payment_date  DATE NOT NULL,
    amount        NUMERIC(10, 2) NOT NULL,
    method        VARCHAR(20) NOT NULL
);

-- No foreign key on msisdn on purpose (learning case 1).
CREATE TABLE usage_records (
    id          INTEGER PRIMARY KEY,
    msisdn      VARCHAR(15) NOT NULL,
    usage_type  VARCHAR(10) NOT NULL,
    quantity    NUMERIC(12, 2) NOT NULL,
    unit        VARCHAR(10) NOT NULL,
    usage_time  TIMESTAMP NOT NULL,
    cost        NUMERIC(10, 4) NOT NULL
);

-- Table comments
COMMENT ON TABLE addresses     IS 'Postal addresses. A customer points to two of them: billing and installation.';
COMMENT ON TABLE customers     IS 'People or companies that buy services.';
COMMENT ON TABLE accounts      IS 'Billing accounts. One customer can have many accounts.';
COMMENT ON TABLE products      IS 'Catalogue of services and devices that we sell.';
COMMENT ON TABLE subscriptions IS 'A product that an account uses. Each subscription has one phone number (msisdn).';
COMMENT ON TABLE orders        IS 'Orders placed by an account.';
COMMENT ON TABLE order_items   IS 'Products inside an order.';
COMMENT ON TABLE invoices      IS 'Monthly bills sent to an account.';
COMMENT ON TABLE invoice_lines IS 'Charges on an invoice. A line can point to a subscription.';
COMMENT ON TABLE payments      IS 'Money received against an invoice.';
COMMENT ON TABLE usage_records IS 'Calls, SMS, and data usage per phone number. Links to subscriptions by msisdn (no foreign key).';

-- Column comments
COMMENT ON COLUMN addresses.line1    IS 'First line of the street address.';
COMMENT ON COLUMN addresses.postcode IS 'Postal code.';
COMMENT ON COLUMN addresses.country  IS 'ISO 3166 two-letter country code.';

COMMENT ON COLUMN customers.status                  IS 'Status code: A active, S suspended, C closed.';
COMMENT ON COLUMN customers.created_date            IS 'Date when the customer was created.';
COMMENT ON COLUMN customers.closed_date             IS 'Date when the customer left. NULL while the customer is open.';
COMMENT ON COLUMN customers.billing_address_id      IS 'Address where invoices go.';
COMMENT ON COLUMN customers.installation_address_id IS 'Address where the service is installed.';

COMMENT ON COLUMN accounts.account_number IS 'Public account number shown on invoices.';
COMMENT ON COLUMN accounts.status         IS 'Account status: ACTIVE, SUSPENDED, or CLOSED.';
COMMENT ON COLUMN accounts.currency       IS 'ISO 4217 currency code.';

COMMENT ON COLUMN products.product_type  IS 'Type: MOBILE, BROADBAND, or DEVICE.';
COMMENT ON COLUMN products.monthly_price IS 'Recurring price per month.';

COMMENT ON COLUMN subscriptions.msisdn   IS 'Phone number in international format. Used to link usage_records.';
COMMENT ON COLUMN subscriptions.end_date IS 'End date. NULL while the subscription runs.';
COMMENT ON COLUMN subscriptions.status   IS 'Subscription status: ACTIVE, SUSPENDED, or ENDED.';

COMMENT ON COLUMN orders.status       IS 'Order status: NEW, SHIPPED, or DONE.';
COMMENT ON COLUMN orders.total_amount IS 'Total value of the order.';

COMMENT ON COLUMN order_items.unit_price IS 'Price of one unit when the order was placed.';

COMMENT ON COLUMN invoices.invoice_number IS 'Public invoice number.';
COMMENT ON COLUMN invoices.total_amount   IS 'Total amount on the invoice.';
COMMENT ON COLUMN invoices.status         IS 'Status code: O open, P paid, C cancelled.';

COMMENT ON COLUMN invoice_lines.subscription_id IS 'Subscription that caused this charge. Can be NULL.';
COMMENT ON COLUMN invoice_lines.amount          IS 'Charge amount for this line.';

COMMENT ON COLUMN payments.method IS 'Payment method: CARD, BANK, or CASH.';

COMMENT ON COLUMN usage_records.msisdn     IS 'Phone number. Matches subscriptions.msisdn. No foreign key exists.';
COMMENT ON COLUMN usage_records.usage_type IS 'Type: VOICE, SMS, or DATA.';
COMMENT ON COLUMN usage_records.quantity   IS 'Amount used, in the given unit.';
COMMENT ON COLUMN usage_records.unit       IS 'Unit: MIN, COUNT, or MB.';
COMMENT ON COLUMN usage_records.cost       IS 'Cost of this usage record.';

-- ---------------------------------------------------------------------------
-- Extra tables (14). They make the schema bigger, so the Table Classifier has real work to do.
-- Groups: payments and collections, discounts, support, and devices. The total is 25 tables.
-- ---------------------------------------------------------------------------

-- Payments and collections
CREATE TABLE payment_methods (
    id            INTEGER PRIMARY KEY,
    account_id    INTEGER NOT NULL REFERENCES accounts (id),
    method_type   VARCHAR(10) NOT NULL,
    last4         CHAR(4) NOT NULL,
    is_default    BOOLEAN NOT NULL,
    created_date  DATE NOT NULL
);

CREATE TABLE refunds (
    id           INTEGER PRIMARY KEY,
    payment_id   INTEGER NOT NULL REFERENCES payments (id),
    amount       NUMERIC(10, 2) NOT NULL,
    reason       VARCHAR(40) NOT NULL,
    refund_date  DATE NOT NULL,
    status       VARCHAR(10) NOT NULL
);

CREATE TABLE credit_notes (
    id           INTEGER PRIMARY KEY,
    invoice_id   INTEGER NOT NULL REFERENCES invoices (id),
    amount       NUMERIC(10, 2) NOT NULL,
    reason       VARCHAR(40) NOT NULL,
    issued_date  DATE NOT NULL
);

CREATE TABLE payment_plans (
    id                INTEGER PRIMARY KEY,
    account_id        INTEGER NOT NULL REFERENCES accounts (id),
    total_amount      NUMERIC(10, 2) NOT NULL,
    instalment_count  INTEGER NOT NULL,
    start_date        DATE NOT NULL,
    status            VARCHAR(10) NOT NULL
);

CREATE TABLE payment_plan_installments (
    id               INTEGER PRIMARY KEY,
    payment_plan_id  INTEGER NOT NULL REFERENCES payment_plans (id),
    due_date         DATE NOT NULL,
    amount           NUMERIC(10, 2) NOT NULL,
    status           VARCHAR(10) NOT NULL
);

CREATE TABLE direct_debit_mandates (
    id           INTEGER PRIMARY KEY,
    account_id   INTEGER NOT NULL REFERENCES accounts (id),
    bank_name    VARCHAR(40) NOT NULL,
    signed_date  DATE NOT NULL,
    status       VARCHAR(10) NOT NULL
);

CREATE TABLE collections_cases (
    id           INTEGER PRIMARY KEY,
    account_id   INTEGER NOT NULL REFERENCES accounts (id),
    invoice_id   INTEGER REFERENCES invoices (id),
    amount_due   NUMERIC(10, 2) NOT NULL,
    opened_date  DATE NOT NULL,
    closed_date  DATE,
    status       VARCHAR(12) NOT NULL
);

-- Discounts
CREATE TABLE discounts (
    id           INTEGER PRIMARY KEY,
    code         VARCHAR(20) NOT NULL UNIQUE,
    description  VARCHAR(80) NOT NULL,
    percent_off  NUMERIC(5, 2) NOT NULL,
    valid_from   DATE NOT NULL,
    valid_to     DATE
);

CREATE TABLE subscription_discounts (
    id               INTEGER PRIMARY KEY,
    subscription_id  INTEGER NOT NULL REFERENCES subscriptions (id),
    discount_id      INTEGER NOT NULL REFERENCES discounts (id),
    applied_date     DATE NOT NULL
);

-- Support
CREATE TABLE support_agents (
    id    INTEGER PRIMARY KEY,
    name  VARCHAR(60) NOT NULL,
    team  VARCHAR(20) NOT NULL
);

CREATE TABLE support_tickets (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (id),
    account_id   INTEGER REFERENCES accounts (id),
    agent_id     INTEGER REFERENCES support_agents (id),
    subject      VARCHAR(80) NOT NULL,
    status       VARCHAR(10) NOT NULL,
    priority     VARCHAR(10) NOT NULL,
    opened_date  DATE NOT NULL,
    closed_date  DATE
);

-- Devices
CREATE TABLE sim_cards (
    id               INTEGER PRIMARY KEY,
    subscription_id  INTEGER NOT NULL REFERENCES subscriptions (id),
    iccid            VARCHAR(22) NOT NULL UNIQUE,
    status           VARCHAR(10) NOT NULL,
    activated_date   DATE NOT NULL
);

CREATE TABLE devices (
    id               INTEGER PRIMARY KEY,
    subscription_id  INTEGER NOT NULL REFERENCES subscriptions (id),
    imei             VARCHAR(15) NOT NULL UNIQUE,
    model            VARCHAR(40) NOT NULL,
    status           VARCHAR(10) NOT NULL
);

-- Tax rates by country. No foreign key (country is a plain code).
CREATE TABLE tax_rates (
    id            INTEGER PRIMARY KEY,
    country       CHAR(2) NOT NULL,
    tax_name      VARCHAR(20) NOT NULL,
    rate_percent  NUMERIC(5, 2) NOT NULL,
    valid_from    DATE NOT NULL
);

-- Table comments (extra tables)
COMMENT ON TABLE payment_methods           IS 'Cards and bank accounts that an account saved for paying.';
COMMENT ON TABLE refunds                   IS 'Money paid back to a customer for a payment.';
COMMENT ON TABLE credit_notes              IS 'Credit given against an invoice, for example after a billing error.';
COMMENT ON TABLE payment_plans             IS 'Agreements to pay an overdue amount in parts.';
COMMENT ON TABLE payment_plan_installments IS 'The parts of a payment plan. Each part has a due date.';
COMMENT ON TABLE direct_debit_mandates     IS 'Permission from an account to take money from its bank account.';
COMMENT ON TABLE collections_cases         IS 'Cases for unpaid money that the collections team follows up.';
COMMENT ON TABLE discounts                 IS 'Discount codes with a percentage and a validity period.';
COMMENT ON TABLE subscription_discounts    IS 'Discounts that were applied to a subscription.';
COMMENT ON TABLE support_agents            IS 'Staff members who work on support tickets.';
COMMENT ON TABLE support_tickets           IS 'Support requests from customers.';
COMMENT ON TABLE sim_cards                 IS 'SIM cards. Each one belongs to a subscription.';
COMMENT ON TABLE devices                   IS 'Phones and routers (by IMEI) used with a subscription.';
COMMENT ON TABLE tax_rates                 IS 'Tax rates by country and start date.';

-- Column comments (extra tables)
COMMENT ON COLUMN payment_methods.method_type   IS 'Type: CARD or BANK.';
COMMENT ON COLUMN payment_methods.last4         IS 'Last four digits of the card or bank account.';
COMMENT ON COLUMN refunds.status                IS 'Refund status: PENDING, DONE, or REJECTED.';
COMMENT ON COLUMN payment_plans.status          IS 'Plan status: ACTIVE, DONE, or DEFAULTED.';
COMMENT ON COLUMN payment_plan_installments.status IS 'Part status: PAID, DUE, or LATE.';
COMMENT ON COLUMN direct_debit_mandates.status  IS 'Mandate status: ACTIVE or CANCELLED.';
COMMENT ON COLUMN collections_cases.invoice_id  IS 'Invoice that caused the case. Can be NULL.';
COMMENT ON COLUMN collections_cases.status      IS 'Case status: OPEN, CLOSED, or WRITTEN_OFF.';
COMMENT ON COLUMN discounts.percent_off         IS 'Discount in percent, for example 10.00.';
COMMENT ON COLUMN discounts.valid_to            IS 'Last valid day. NULL means no end date.';
COMMENT ON COLUMN support_agents.team           IS 'Team: BILLING, TECHNICAL, or SALES.';
COMMENT ON COLUMN support_tickets.agent_id      IS 'Agent who works on the ticket. NULL while unassigned.';
COMMENT ON COLUMN support_tickets.status        IS 'Ticket status: OPEN, PENDING, or RESOLVED.';
COMMENT ON COLUMN support_tickets.priority      IS 'Priority: LOW, MEDIUM, or HIGH.';
COMMENT ON COLUMN sim_cards.status              IS 'SIM status: ACTIVE or BLOCKED.';
COMMENT ON COLUMN devices.status                IS 'Device status: ACTIVE, LOST, or RETURNED.';
COMMENT ON COLUMN tax_rates.country             IS 'ISO 3166 two-letter country code.';
