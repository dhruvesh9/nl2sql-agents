"""Tests for agent 1 (Query Analyzer). A fake LLM answer replaces the real LLM."""

from typing import Any

import pytest

from app.agents import query_analyzer

INDEX_MD = (
    "| Runbook | Keywords | Description |\n"
    "|---|---|---|\n"
    "| `invoice_status` | invoice, unpaid | Status codes of invoices. |\n"
    "| `active_customer` | active customer | The rule for an active customer. |\n"
)
SEVEN_KEYS = {
    "guardrail",
    "intent",
    "requested_fields",
    "filters",
    "aggregations",
    "business_concepts",
    "runbook_candidates",
}


def fake_llm(monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any]) -> dict[str, Any]:
    """Make the LLM return the answer. The result dict keeps what the agent sent."""
    sent: dict[str, Any] = {}

    def fake(system_prompt: str, user_message: str, agent: str = "default") -> dict[str, Any]:
        sent["user_message"] = user_message
        sent["agent"] = agent
        return dict(answer)

    monkeypatch.setattr(query_analyzer, "call_llm_json", fake)
    return sent


def test_missing_keys_are_filled_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {"intent": "list"})
    result = query_analyzer.run("List all products", INDEX_MD)
    assert set(result) == SEVEN_KEYS
    assert result["intent"] == "list"
    assert result["filters"] == []


def test_default_lists_are_not_shared_between_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    # If two answers shared one default list, a change in one request would leak into the next.
    fake_llm(monkeypatch, {})
    first = query_analyzer.run("q1", INDEX_MD)
    first["filters"].append("year 2025")
    second = query_analyzer.run("q2", INDEX_MD)
    assert second["filters"] == []


def test_invented_runbook_names_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = {"runbook_candidates": ["invoice_status", "loyalty_rules"]}
    fake_llm(monkeypatch, answer)
    result = query_analyzer.run("Unpaid invoices", INDEX_MD)
    assert result["runbook_candidates"] == ["invoice_status"]


def test_a_part_of_a_runbook_name_is_not_a_runbook(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {"runbook_candidates": ["invoice", "status", "active"]})
    assert query_analyzer.run("q", INDEX_MD)["runbook_candidates"] == []


def test_runbook_candidates_that_are_not_text_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {"runbook_candidates": [None, 5, ["invoice_status"], "active_customer"]})
    assert query_analyzer.run("q", INDEX_MD)["runbook_candidates"] == ["active_customer"]


@pytest.mark.parametrize("bad_value", [None, "invoice_status", 5, {"a": 1}])
def test_runbook_candidates_that_are_not_a_list_give_an_empty_list(
    monkeypatch: pytest.MonkeyPatch, bad_value: Any
) -> None:
    fake_llm(monkeypatch, {"runbook_candidates": bad_value})
    assert query_analyzer.run("q", INDEX_MD)["runbook_candidates"] == []


def test_the_agent_sends_the_question_the_index_and_its_own_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = fake_llm(monkeypatch, {})
    query_analyzer.run("How many active customers?", INDEX_MD)
    assert "How many active customers?" in sent["user_message"]
    assert "`invoice_status`" in sent["user_message"]
    assert sent["agent"] == "query_analyzer"


@pytest.mark.parametrize("value", ["data_change", "prompt_injection"])
def test_a_guardrail_from_the_llm_is_kept(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    fake_llm(monkeypatch, {"intent": "blocked", "guardrail": value})
    assert query_analyzer.run("delete all customers", INDEX_MD)["guardrail"] == value


def test_a_missing_guardrail_means_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {"intent": "list"})
    assert query_analyzer.run("List all products", INDEX_MD)["guardrail"] == "none"


@pytest.mark.parametrize("value", ["unsafe", "DATA_CHANGE", None, 5, ["data_change"]])
def test_a_guardrail_value_that_is_not_one_of_the_three_words_is_not_used(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    # The SQL guard and the read-only transaction in db-service still stop a real write.
    fake_llm(monkeypatch, {"intent": "list", "guardrail": value})
    assert query_analyzer.run("q", INDEX_MD)["guardrail"] == "none"


def test_the_prompt_tells_the_llm_about_the_guardrail_and_the_normal_past_tense_question() -> None:
    prompt = query_analyzer.PROMPT_FILE.read_text(encoding="utf-8")
    assert "`data_change`" in prompt
    assert "`prompt_injection`" in prompt
    assert "How many mandates were cancelled?" in prompt  # a question ABOUT a change is normal
