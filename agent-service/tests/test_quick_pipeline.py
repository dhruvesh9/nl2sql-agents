"""Tests for the quick pipeline (POST /ask-quick). Every agent and every service call is faked."""

from typing import Any

import pytest

from app import db_client, knowledge, quick_pipeline
from app.agents import query_analyzer, response_agent, sql_generator, table_classifier
from app.errors import LlmError

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
        monkeypatch.setattr(knowledge, "read_runbook", lambda name: f"RUNBOOK {name}")
        monkeypatch.setattr(query_analyzer, "run", self.analyzer)
        monkeypatch.setattr(table_classifier, "run", self.classifier)
        monkeypatch.setattr(db_client, "get_schema", lambda tables, fk_depth: SCHEMA)
        monkeypatch.setattr(sql_generator, "run", self.generator)
        monkeypatch.setattr(db_client, "run_query", self.run_query)
        monkeypatch.setattr(response_agent, "call_llm", lambda *args, **kwargs: "A friendly reply.")

    def analyzer(self, question: str, index_md: str) -> dict[str, Any]:
        self.received["index_md"] = index_md
        return {"intent": self.intent, "filters": ["year 2025"], "runbook_candidates": ["rb"]}

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
        self.received["runbook_texts"] = args[0]
        return {"sql": "SELECT id FROM orders", "explanation": "x"}

    def run_query(self, sql: str) -> dict[str, Any]:
        if self.query_error:
            raise db_client.DbServiceError(400, self.query_error)
        return {"columns": ["id"], "rows": [[1], [2]], "row_count": 2}


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    return Fakes(monkeypatch)


def test_happy_path_runs_every_step_and_returns_a_text_and_the_rows(fakes: Fakes) -> None:
    response = quick_pipeline.run_quick("List orders")
    assert response.answer == "Here are the results (2 rows)."
    assert response.data.columns == ["id"]
    assert response.data.rows == [[1], [2]]
    assert response.sql == "SELECT id FROM orders"  # internal: for the logs, not for the client
    assert [entry.step for entry in response.trace] == ["1", "2", "3", "5", "7"]


def test_each_step_gets_the_output_of_the_step_before(fakes: Fakes) -> None:
    quick_pipeline.run_quick("List orders")
    assert fakes.received["index_md"] == "INDEX"
    assert fakes.received["requirements"]["filters"] == ["year 2025"]
    assert fakes.received["tables_text"] == "- orders: Purchase orders."  # from the graph
    assert "orders.account_id -> accounts.id" in fakes.received["relationships_text"]
    assert "TABLE orders" in fakes.received["schema_text"]  # the live schema, as text


def test_the_sql_generator_gets_the_runbooks_from_step_1(fakes: Fakes) -> None:
    quick_pipeline.run_quick("List orders")
    assert fakes.received["runbook_texts"] == ["RUNBOOK rb"]


def test_chitchat_gets_a_friendly_text_and_stops_after_step_1(fakes: Fakes) -> None:
    fakes.intent = "chitchat"
    response = quick_pipeline.run_quick("hello")
    assert response.answer == "A friendly reply."
    assert response.data is None
    assert "requirements" not in fakes.received  # no classifier call, no cost, for a greeting
    assert [entry.name for entry in response.trace] == ["query_analyzer"]


def test_no_tables_gets_a_text_before_the_database_is_called(fakes: Fakes) -> None:
    fakes.tables = []
    response = quick_pipeline.run_quick("q")
    assert response.answer == "A friendly reply."
    assert response.data is None
    assert "schema_text" not in fakes.received


def test_rejected_sql_becomes_an_error_and_the_sql_stays_in_the_trace(fakes: Fakes) -> None:
    fakes.query_error = "column bad does not exist"
    response = quick_pipeline.run_quick("q", request_id="abc")
    assert (response.code, response.request_id, response.data) == ("QUERY_FAILED", "abc", None)
    assert "column bad" not in response.answer  # the detail is for the log, not for the user
    assert "SELECT id FROM orders" in response.trace[-1].summary


def test_an_error_in_any_agent_becomes_an_error_response(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*args: Any, **kwargs: Any) -> None:
        raise LlmError("unavailable", "timeout")

    monkeypatch.setattr(table_classifier, "run", down)
    response = quick_pipeline.run_quick("q")
    assert (response.code, response.http_status) == ("LLM_UNAVAILABLE", 503)
    assert [entry.step for entry in response.trace] == [
        "1"
    ]  # the steps before the failure are kept


def test_the_client_gets_only_the_answer_the_rows_and_the_ids(fakes: Fakes) -> None:
    # The trace, the SQL and the status are debug data. They go to the logs and Langfuse.
    response = quick_pipeline.run_quick("List orders", request_id="abc")
    assert response.trace
    body = response.model_dump(exclude_none=True)
    assert set(body) == {"answer", "data", "request_id"}
    assert set(body["data"]) == {"columns", "rows", "truncated"}
