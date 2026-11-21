"""Tests for POST /query. The database tests need the sample database (run: make db-load)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import check_connection
from app.executor import choose_row_limit, to_json_safe
from app.main import app

requires_db = pytest.mark.skipif(not check_connection(), reason="PostgreSQL is not running")

client = TestClient(app)


def post_query(sql: str, max_rows: int | None = None):
    return client.post("/query", json={"sql": sql, "max_rows": max_rows})


def test_to_json_safe_converts_special_values() -> None:
    assert to_json_safe(Decimal("1.50")) == 1.5
    assert to_json_safe(date(2025, 1, 31)) == "2025-01-31"
    assert to_json_safe(datetime(2025, 1, 31, 8, 30)) == "2025-01-31T08:30:00"
    assert to_json_safe(b"\x01\xff") == "01ff"
    assert to_json_safe(Decimal("NaN")) == "nan"


def test_to_json_safe_keeps_normal_values() -> None:
    assert to_json_safe("text") == "text"
    assert to_json_safe(5) == 5
    assert to_json_safe(None) is None


def test_row_limit_rules() -> None:
    assert choose_row_limit(None) == settings.default_max_rows
    assert choose_row_limit(0) == settings.default_max_rows
    assert choose_row_limit(-5) == settings.default_max_rows
    assert choose_row_limit(10) == 10
    assert choose_row_limit(10**9) == settings.max_rows_limit


@requires_db
def test_normal_select_returns_rows_and_columns() -> None:
    body = post_query("SELECT id, name FROM customers ORDER BY id", max_rows=3).json()
    assert body["columns"] == ["id", "name"]
    assert body["rows"][0] == [1, "Customer 001"]
    assert body["row_count"] == 3


@requires_db
def test_more_rows_than_max_rows_sets_truncated() -> None:
    body = post_query("SELECT id FROM customers ORDER BY id", max_rows=2).json()
    assert body["row_count"] == 2 and body["truncated"] is True


@requires_db
def test_exactly_max_rows_is_not_truncated() -> None:
    body = post_query("SELECT id FROM customers ORDER BY id LIMIT 5", max_rows=5).json()
    assert body["row_count"] == 5 and body["truncated"] is False


@requires_db
def test_zero_rows_still_returns_column_names() -> None:
    body = post_query("SELECT id, name FROM customers WHERE id < 0").json()
    assert body["columns"] == ["id", "name"]
    assert body["rows"] == [] and body["truncated"] is False


@requires_db
def test_decimal_and_date_values_are_json_safe() -> None:
    body = post_query("SELECT invoice_date, total_amount FROM invoices ORDER BY id", 1).json()
    invoice_date, total_amount = body["rows"][0]
    assert isinstance(invoice_date, str) and isinstance(total_amount, float)


@requires_db
def test_special_characters_in_sql_work() -> None:
    sql = "SELECT '12:30' AS t, ':abc' AS x, name FROM customers WHERE name LIKE '%001%'"
    body = post_query(sql).json()
    assert body["rows"] == [["12:30", ":abc", "Customer 001"]]


@requires_db
def test_wrong_sql_returns_400_with_database_message() -> None:
    response = post_query("SELECT nme FROM customers")
    assert response.status_code == 400
    assert "nme" in response.json()["detail"]


@requires_db
def test_slow_query_stops_at_the_timeout() -> None:
    response = post_query(f"SELECT pg_sleep({settings.statement_timeout_ms / 1000 + 5})")
    assert response.status_code == 400
    assert "timeout" in response.json()["detail"]


@requires_db
def test_delete_is_rejected_with_400() -> None:
    response = post_query("DELETE FROM customers")
    assert response.status_code == 400
    # the data is still there
    assert post_query("SELECT count(*) FROM customers").json()["rows"] == [[100]]


@requires_db
def test_read_only_transaction_blocks_writes_even_if_guard_is_skipped() -> None:
    # A second safety layer: call the executor path with a write that the guard allows by mistake.
    from app.database import engine, start_readonly

    with engine.connect() as conn:
        start_readonly(conn)
        with pytest.raises(Exception, match="read-only"):
            conn.exec_driver_sql("INSERT INTO addresses VALUES (999, 'x', 'x', 'x', 'GB')")
