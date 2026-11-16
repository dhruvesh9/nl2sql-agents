"""Tests for the mini pipeline (step 1 and step 2). Fake agents and a fake knowledge base are used."""

from typing import Any

import pytest

from app import analysis_pipeline, knowledge
from app.agents import query_analyzer, table_classifier


@pytest.fixture(autouse=True)
def fake_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge, "read_index", lambda: "INDEX")
    monkeypatch.setattr(knowledge, "read_tables", lambda: "TABLES")
    monkeypatch.setattr(knowledge, "read_relationships", lambda: "RELATIONSHIPS")


def fake_agents(monkeypatch: pytest.MonkeyPatch, intent: str) -> dict[str, Any]:
    """Replace both agents. The result dict keeps what step 2 received."""
    received: dict[str, Any] = {"classifier_calls": 0}

    def analyzer(question: str, index_md: str) -> dict[str, Any]:
        received["index_md"] = index_md
        return {"intent": intent, "filters": ["year 2025"], "runbook_candidates": []}

    def classifier(requirements: dict[str, Any], tables_md: str, **kwargs: Any) -> dict[str, Any]:
        received["classifier_calls"] += 1
        received["requirements"] = requirements
        received["tables_md"] = tables_md
        received["relationships_md"] = kwargs.get("relationships_md")
        return {
            "selected_tables": ["invoices", "accounts"],
            "reason": "because",
            "runbook_candidates": [],
        }

    monkeypatch.setattr(query_analyzer, "run", analyzer)
    monkeypatch.setattr(table_classifier, "run", classifier)
    return received


def test_step_2_gets_the_output_of_step_1_and_the_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = fake_agents(monkeypatch, intent="aggregate")
    response = analysis_pipeline.run_analysis("Total unpaid invoices")

    assert received["index_md"] == "INDEX"
    assert received["requirements"]["filters"] == ["year 2025"]
    assert received["tables_md"] == "TABLES"
    assert received["relationships_md"] == "RELATIONSHIPS"
    assert response.selected_tables == ["invoices", "accounts"]
    assert response.reason == "because"


def test_the_trace_has_one_entry_for_each_step_that_ran(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_agents(monkeypatch, intent="aggregate")
    response = analysis_pipeline.run_analysis("Total unpaid invoices")
    assert [(entry.step, entry.name) for entry in response.trace] == [
        ("1", "query_analyzer"),
        ("2", "table_classifier"),
    ]
    assert all(entry.elapsed_ms >= 0 for entry in response.trace)


def test_chitchat_stops_after_step_1_and_never_calls_the_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = fake_agents(monkeypatch, intent="chitchat")
    response = analysis_pipeline.run_analysis("hello")

    assert received["classifier_calls"] == 0  # no LLM call, no cost, for a greeting
    assert response.selected_tables == []
    assert response.requirements["intent"] == "chitchat"
    assert [entry.name for entry in response.trace] == ["query_analyzer"]
