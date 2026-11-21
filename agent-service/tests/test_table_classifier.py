"""Tests for agent 2 (Table Classifier). A fake LLM answer replaces the real LLM."""

from typing import Any

import pytest

from app.agents import table_classifier

TABLES_MD = "- customers: buyers\n- accounts: billing accounts\n- invoices: monthly bills\n"


def fake_llm(monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any]) -> dict[str, Any]:
    """Make the LLM return the answer. The result dict keeps what the agent sent."""
    sent: dict[str, Any] = {}

    def fake(system_prompt: str, user_message: str, agent: str = "default") -> dict[str, Any]:
        sent["user_message"] = user_message
        sent["agent"] = agent
        return answer

    monkeypatch.setattr(table_classifier, "call_llm_json", fake)
    return sent


def test_table_names_are_read_from_the_list_lines_only() -> None:
    text = "# Tables\n- customers: buyers\nsome note\n- not a table line\n- invoices: bills\n"
    assert table_classifier.list_table_names(text) == ["customers", "invoices"]


def test_invented_tables_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {"selected_tables": ["customers", "loyalty_points"], "reason": "x"})
    result = table_classifier.run({"intent": "list"}, TABLES_MD)
    assert result["selected_tables"] == ["customers"]


def test_duplicates_are_removed_and_the_order_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = {"selected_tables": ["invoices", "customers", "invoices"], "reason": "x"}
    fake_llm(monkeypatch, answer)
    result = table_classifier.run({}, TABLES_MD)
    assert result["selected_tables"] == ["invoices", "customers"]


def test_a_table_name_must_match_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    # "customer" (singular) is not a table. We do not guess what the LLM meant.
    fake_llm(monkeypatch, {"selected_tables": ["customer", "Invoices"], "reason": "x"})
    assert table_classifier.run({}, TABLES_MD)["selected_tables"] == []


@pytest.mark.parametrize("bad_answer", ["customers", None, {"a": 1}, 5])
def test_an_answer_that_is_not_a_list_gives_no_tables(
    monkeypatch: pytest.MonkeyPatch, bad_answer: Any
) -> None:
    fake_llm(monkeypatch, {"selected_tables": bad_answer, "reason": "x"})
    assert table_classifier.run({}, TABLES_MD)["selected_tables"] == []


def test_missing_keys_in_the_answer_do_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {})
    result = table_classifier.run({}, TABLES_MD)
    assert result == {"selected_tables": [], "reason": "", "runbook_candidates": []}


def test_the_agent_sends_requirements_tables_and_its_own_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = fake_llm(monkeypatch, {"selected_tables": [], "reason": ""})
    table_classifier.run({"intent": "aggregate", "filters": ["year 2025"]}, TABLES_MD)
    assert "year 2025" in sent["user_message"]
    assert "- accounts: billing accounts" in sent["user_message"]
    assert sent["agent"] == "table_classifier"  # this selects the LLM options of the agent


def test_relationships_are_sent_only_when_they_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_llm(monkeypatch, {"selected_tables": [], "reason": ""})

    table_classifier.run({}, TABLES_MD)
    assert "Table relationships" not in sent["user_message"]

    table_classifier.run({}, TABLES_MD, relationships_text="invoices -> accounts")
    assert "Table relationships:\ninvoices -> accounts" in sent["user_message"]


def test_hints_from_the_feedback_step_are_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_llm(monkeypatch, {"selected_tables": [], "reason": ""})
    table_classifier.run({}, TABLES_MD, feedback_hints=["add the accounts table"])
    assert "- add the accounts table" in sent["user_message"]
