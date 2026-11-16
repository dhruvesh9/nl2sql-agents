"""Tests for POST /schema. They need the sample database (run: make db-load)."""

import pytest
from fastapi.testclient import TestClient

from app.database import check_connection
from app.main import app
from app.schema_reader import read_table

requires_db = pytest.mark.skipif(not check_connection(), reason="PostgreSQL is not running")

client = TestClient(app)
HEADERS = {"X-API-Key": "change-me"}


def post_schema(tables: list[str], fk_depth: int = 0) -> dict:
    response = client.post(
        "/schema", json={"tables": tables, "fk_depth": fk_depth}, headers=HEADERS
    )
    assert response.status_code == 200
    return response.json()


@requires_db
def test_read_table_returns_columns_keys_and_comment() -> None:
    table = read_table("invoices")
    assert table is not None
    assert [column.name for column in table.columns][:2] == ["id", "account_id"]
    assert table.primary_key == ["id"]
    assert table.foreign_keys[0].ref_table == "accounts"
    assert table.description == "Monthly bills sent to an account."


@requires_db
def test_read_table_unknown_table_returns_none() -> None:
    assert read_table("nope") is None


@requires_db
def test_usage_records_has_no_foreign_key_on_purpose() -> None:
    assert read_table("usage_records").foreign_keys == []


@requires_db
def test_unknown_and_wrong_case_names_go_to_not_found() -> None:
    body = post_schema(["invoices", "nope", "Customers"])
    assert [table["name"] for table in body["tables"]] == ["invoices"]
    assert body["not_found"] == ["nope", "Customers"]
    assert body["dialect"] == "postgresql"


@requires_db
def test_duplicate_names_return_one_table_in_request_order() -> None:
    body = post_schema(["payments", "invoices", "payments"])
    assert [table["name"] for table in body["tables"]] == ["payments", "invoices"]


@requires_db
def test_empty_request_returns_empty_lists() -> None:
    body = post_schema([], fk_depth=2)
    assert body["tables"] == [] and body["discovered_tables"] == [] and body["not_found"] == []


@requires_db
def test_fk_depth_one_discovers_neighbours_and_reads_them() -> None:
    body = post_schema(["invoices"], fk_depth=1)
    # Tables that point to invoices (invoice_lines, payments, credit_notes, collections_cases)
    # and the table that invoices points to (accounts). The order is alphabetical.
    expected = ["accounts", "collections_cases", "credit_notes", "invoice_lines", "payments"]
    assert body["discovered_tables"] == expected
    names = [table["name"] for table in body["tables"]]
    assert names == ["invoices", *expected]


@requires_db
def test_fk_depth_is_limited_by_max_fk_depth() -> None:
    deep = post_schema(["invoices"], fk_depth=99)
    limited = post_schema(["invoices"], fk_depth=3)  # MAX_FK_DEPTH is 3 in .env.example
    assert deep["discovered_tables"] == limited["discovered_tables"]


@requires_db
def test_table_with_no_links_has_nothing_to_discover() -> None:
    assert post_schema(["usage_records"], fk_depth=3)["discovered_tables"] == []


def test_schema_needs_api_key() -> None:
    response = client.post("/schema", json={"tables": ["invoices"], "fk_depth": 0})
    assert response.status_code == 401
