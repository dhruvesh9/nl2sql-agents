"""Tests for the quick pipeline (POST /ask-quick). Every agent and every service call is faked."""

from typing import Any

import pytest

from app import db_client, knowledge, quick_pipeline
from app.agents import query_analyzer, sql_generator, table_classifier

GRAPH = {
    "nodes": [{"id": "orders", "description": "Purchase orders."}],
    "edges": [
        {"source": "orders", "target": "accounts", "columns": ["account_id"], "ref_columns": ["id"]}
    ],
}

SCHEMA = {
    "dialect": "postgresql",
    "tables": [
        {
            "name": "orders",
            "description": None,
            "columns": [{"name": "id", "type": "INTEGER", "nullable": False}],
            "primary_key": ["id"],
            "foreign_keys": [],
        }
    ],
}


class Fakes:
    """Replaces the agents and the services. It keeps what each step received."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.intent = "list"
        self.tables = ["orders"]
        self.query_error: str | None = None
        self.received: dict[str, Any] = {}
        monkeypatch.setattr(knowledge, "read_index", lambda: "INDEX")
        monkeypatch.setattr(knowledge, "read_graph", lambda: GRAPH)
        monkeypatch.setattr(query_analyzer, "run", self.analyzer)
        monkeypatch.setattr(table_classifier, "run", self.classifier)
        monkeypatch.setattr(db_client, "get_schema", lambda tables, fk_depth: SCHEMA)
        monkeypatch.setattr(sql_generator, "run", self.generator)
        monkeypatch.setattr(db_client, "run_query", self.run_query)

    def analyzer(self, question: str, index_md: str) -> dict[str, Any]:
        self.received["index_md"] = index_md
        return {"intent": self.intent, "filters": ["year 2025"]}

    def classifier(
        self, requirements: dict[str, Any], tables_text: str, **kwargs: Any
    ) -> dict[str, Any]:
        self.received["requirements"] = requirements
        self.received["tables_text"] = tables_text
        self.received["relationships_text"] = kwargs["relationships_text"]
        return {"selected_tables": self.tables, "reason": "x", "runbook_candidates": []}

    def generator(
        self, requirements: dict[str, Any], schema_text: str, *args: Any
    ) -> dict[str, str]:
        self.received["schema_text"] = schema_text
        return {"sql": "SELECT id FROM orders", "explanation": "x"}

    def run_query(self, sql: str) -> dict[str, Any]:
        if self.query_error:
            raise db_client.DbServiceError(400, self.query_error)
        return {"columns": ["id"], "rows": [[1]], "row_count": 1}


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    return Fakes(monkeypatch)


def test_happy_path_runs_every_step_and_returns_the_rows(fakes: Fakes) -> None:
    response = quick_pipeline.run_quick("List orders")
    assert response.status == "success"
    assert response.sql == "SELECT id FROM orders"
    assert response.rows == [[1]]
    assert [entry.step for entry in response.trace] == ["1", "2", "3", "5", "7"]


def test_each_step_gets_the_output_of_the_step_before(fakes: Fakes) -> None:
    quick_pipeline.run_quick("List orders")
    assert fakes.received["index_md"] == "INDEX"
    assert fakes.received["requirements"]["filters"] == ["year 2025"]
    assert fakes.received["tables_text"] == "- orders: Purchase orders."  # from the graph
    assert "orders.account_id -> accounts.id" in fakes.received["relationships_text"]
    assert "TABLE orders" in fakes.received["schema_text"]  # the live schema, as text


def test_chitchat_stops_after_step_1(fakes: Fakes) -> None:
    fakes.intent = "chitchat"
    response = quick_pipeline.run_quick("hello")
    assert response.status == "failed"
    assert "requirements" not in fakes.received  # no classifier call, no cost, for a greeting
    assert [entry.name for entry in response.trace] == ["query_analyzer"]


def test_no_tables_fails_before_the_database_is_called(fakes: Fakes) -> None:
    fakes.tables = []
    response = quick_pipeline.run_quick("q")
    assert response.status == "failed"
    assert "schema_text" not in fakes.received


def test_rejected_sql_is_returned_as_a_failure_with_the_sql(fakes: Fakes) -> None:
    fakes.query_error = "column bad does not exist"
    response = quick_pipeline.run_quick("q")
    assert response.status == "failed"
    assert response.sql == "SELECT id FROM orders"
    assert response.failure_reason == "column bad does not exist"


def test_the_client_gets_no_trace(fakes: Fakes) -> None:
    # The trace is debug data. It goes to the logs and Langfuse, not to the client.
    response = quick_pipeline.run_quick("List orders")
    assert response.trace  # the pipeline still records the steps
    body = response.model_dump()
    assert set(body) == {"status", "sql", "columns", "rows", "failure_reason"}
