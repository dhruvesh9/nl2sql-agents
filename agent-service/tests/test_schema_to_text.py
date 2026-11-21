"""Tests for schema_to_text: the schema text that the SQL generator reads."""

from app import pipeline

SCHEMA = {
    "tables": [
        {
            "name": "orders",
            "description": "Orders placed by an account.",
            "columns": [
                {"name": "id", "type": "INTEGER", "description": None},
                {
                    "name": "status",
                    "type": "VARCHAR(10)",
                    "description": "Order status:\nNEW,  SHIPPED.",
                },
                {"name": "account_id", "type": "INTEGER"},
            ],
            "primary_key": ["id"],
            "foreign_keys": [
                {"columns": ["account_id"], "ref_table": "accounts", "ref_columns": ["id"]}
            ],
        }
    ]
}


def test_a_column_comment_follows_the_column_on_one_line() -> None:
    text = pipeline.schema_to_text(SCHEMA)
    assert "  status VARCHAR(10) -- Order status: NEW, SHIPPED." in text


def test_columns_without_a_comment_have_no_dashes() -> None:
    lines = pipeline.schema_to_text(SCHEMA).splitlines()
    assert "  id INTEGER PK" in lines
    assert "  account_id INTEGER FK->accounts.id" in lines


def test_the_table_line_keeps_the_table_comment() -> None:
    assert pipeline.schema_to_text(SCHEMA).startswith("TABLE orders (Orders placed by an account.)")
