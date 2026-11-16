"""Tests for the SQL guard. They need no database."""

import pytest

from app.sql_guard import SqlRejectedError, check_sql

GOOD_SQL = [
    "SELECT 1",
    "SELECT 1;",
    "select id, name from customers where status = 'A'",
    (
        "SELECT c.name, SUM(i.total_amount) FROM invoices i JOIN accounts a ON a.id = i.account_id "
        "JOIN customers c ON c.id = a.customer_id GROUP BY c.name"
    ),
    "WITH t AS (SELECT 1 AS x) SELECT * FROM t",
    "SELECT 1 UNION SELECT 2",
    "SELECT 1 UNION ALL SELECT 2",
    "(SELECT 1)",
    "SELECT 'delete me' AS note",  # the word DELETE inside a string is fine
    "SELECT 1 -- DROP TABLE customers",  # a comment is fine
    "SELECT name FROM customers WHERE name LIKE '%001%'",
    "SELECT '12:30' AS t, id::text FROM customers",
    "SELECT pg_sleep(1)",  # allowed on purpose: the statement timeout stops long queries
]

BAD_SQL = [
    ("INSERT INTO customers (id) VALUES (1)", "Only SELECT"),
    ("UPDATE customers SET status = 'C'", "Only SELECT"),
    ("DELETE FROM customers", "Only SELECT"),
    ("MERGE INTO a USING b ON a.id = b.id WHEN MATCHED THEN DELETE", "Only SELECT"),
    ("CREATE TABLE x (id INT)", "Only SELECT"),
    ("DROP TABLE customers", "Only SELECT"),
    ("ALTER TABLE customers ADD COLUMN x INT", "Only SELECT"),
    ("TRUNCATE customers", "Only SELECT"),
    ("SELECT id INTO new_table FROM customers", "INTO"),
    ("SELECT 1; DROP TABLE customers", "Only one statement"),
    ("SELECT 1; SELECT 2", "Only one statement"),
    ("SELECT * FROM customers FOR UPDATE", "FOR UPDATE"),
    ("WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x", "DELETE"),
    ("WITH x AS (INSERT INTO customers (id) VALUES (1) RETURNING *) SELECT * FROM x", "INSERT"),
    ("EXPLAIN SELECT 1", "Only SELECT"),
    ("COPY customers TO '/tmp/x'", "Only SELECT"),
    ("VACUUM", "Only SELECT"),
    ("SET statement_timeout = 0", "Only SELECT"),
    ("", "empty"),
    ("   ", "empty"),
    (";", "empty"),
]


@pytest.mark.parametrize("sql", GOOD_SQL)
def test_good_sql_is_accepted(sql: str) -> None:
    check_sql(sql)  # no error means the SQL is accepted


@pytest.mark.parametrize("sql, reason_part", BAD_SQL)
def test_bad_sql_is_rejected_with_a_reason(sql: str, reason_part: str) -> None:
    with pytest.raises(SqlRejectedError) as error:
        check_sql(sql)
    assert reason_part in str(error.value)


def test_postgresql_dialect_name_from_sqlalchemy_works() -> None:
    check_sql("SELECT 1", "postgresql")
