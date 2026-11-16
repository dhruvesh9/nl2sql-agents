"""Tests for POST /plan. The database tests need the sample database (run: make db-load)."""

import pytest
from fastapi.testclient import TestClient

from app.database import check_connection
from app.main import app
from app.planner import build_explain_statement

requires_db = pytest.mark.skipif(not check_connection(), reason="PostgreSQL is not running")

client = TestClient(app)
HEADERS = {"X-API-Key": "change-me"}


def post_plan(sql: str):
    return client.post("/plan", json={"sql": sql}, headers=HEADERS)


def test_explain_statement_for_postgresql() -> None:
    assert build_explain_statement("SELECT 1;", "postgresql") == "EXPLAIN (FORMAT JSON) SELECT 1"


def test_explain_statement_never_uses_analyze() -> None:
    assert "ANALYZE" not in build_explain_statement("SELECT 1", "postgresql").upper()


def test_explain_statement_for_unknown_dialect_fails() -> None:
    with pytest.raises(ValueError):
        build_explain_statement("SELECT 1", "oracle")


@requires_db
def test_good_select_returns_cost_and_rows() -> None:
    body = post_plan("SELECT name FROM customers WHERE status = 'A'").json()
    assert body["valid"] is True
    assert body["error"] is None
    assert body["estimated_cost"] > 0
    assert body["estimated_rows"] > 0
    assert body["plan"]["Node Type"]


@requires_db
def test_wrong_column_returns_valid_false_with_database_message() -> None:
    body = post_plan("SELECT nme FROM customers").json()
    assert body["valid"] is False
    assert "nme" in body["error"]
    assert body["estimated_cost"] is None


@requires_db
def test_wrong_table_returns_valid_false() -> None:
    body = post_plan("SELECT * FROM nope").json()
    assert body["valid"] is False
    assert "nope" in body["error"]


@requires_db
def test_trailing_semicolon_and_special_characters_work() -> None:
    sql = "SELECT '12:30' AS t, name FROM customers WHERE name LIKE '%001%';"
    assert post_plan(sql).json()["valid"] is True


@requires_db
def test_delete_is_rejected_with_400() -> None:
    response = post_plan("DELETE FROM customers")
    assert response.status_code == 400
    assert "Only SELECT" in response.json()["detail"]


@requires_db
def test_plan_does_not_run_the_query() -> None:
    # pg_sleep(30) would take 30 seconds if the query ran. EXPLAIN only plans it.
    response = post_plan("SELECT pg_sleep(30)")
    assert response.status_code == 200
    assert response.json()["valid"] is True
