"""Tests for the Response Agent: error codes, rows, and the LLM text with its fallback."""

from typing import Any

import httpx
import pytest

from app.agents import response_agent
from app.config import settings
from app.db_client import DbServiceError
from app.errors import LlmError
from app.knowledge import KnowledgeServiceError


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (LlmError("rate_limited", "x"), "LLM_BUSY"),
        (LlmError("unavailable", "x"), "LLM_UNAVAILABLE"),
        (LlmError("bad_output", "x"), "LLM_BAD_OUTPUT"),
        (LlmError("timeout", "x"), "TIMEOUT"),
        (httpx.ReadTimeout("slow"), "TIMEOUT"),
        (httpx.ConnectTimeout("slow"), "TIMEOUT"),
        (TimeoutError("budget used"), "TIMEOUT"),
        (DbServiceError(504, "query too long"), "TIMEOUT"),
        (DbServiceError(408, "x"), "TIMEOUT"),
        (DbServiceError(500, "boom"), "SERVICE_UNAVAILABLE"),
        (DbServiceError(502, "x"), "SERVICE_UNAVAILABLE"),
        (DbServiceError(429, "x"), "SERVICE_UNAVAILABLE"),
        (DbServiceError(404, "x"), "INTERNAL_ERROR"),
        (DbServiceError(422, "x"), "INTERNAL_ERROR"),
        (DbServiceError(401, "x"), "INTERNAL_ERROR"),
        (KnowledgeServiceError(504, "slow"), "TIMEOUT"),
        (KnowledgeServiceError(404, "run POST /generate first"), "SERVICE_UNAVAILABLE"),
        (KnowledgeServiceError(400, "bad name"), "INTERNAL_ERROR"),
        (KnowledgeServiceError(500, "boom"), "SERVICE_UNAVAILABLE"),
        (DbServiceError(400, "bad column"), "QUERY_FAILED"),
        (DbServiceError(503, "down"), "SERVICE_UNAVAILABLE"),
        (KnowledgeServiceError(503, "down"), "SERVICE_UNAVAILABLE"),
        (httpx.ConnectError("refused"), "SERVICE_UNAVAILABLE"),
        (NotImplementedError("later"), "NOT_IMPLEMENTED"),
        (RuntimeError("a bug"), "INTERNAL_ERROR"),
    ],
)
def test_each_error_has_a_code(error: Exception, code: str) -> None:
    assert response_agent.error_code(error) == code


def test_every_code_has_a_text_and_a_status() -> None:
    for code, (status, text) in response_agent.ERRORS.items():
        assert status >= 200
        assert text, code


def test_an_error_response_never_shows_the_real_error() -> None:
    error = DbServiceError(503, "password authentication failed for user nl2sql_reader")
    response = response_agent.for_error(error, request_id="r1")
    assert response.code == "SERVICE_UNAVAILABLE"
    assert response.http_status == 503
    assert response.request_id == "r1"
    assert "password" not in response.answer
    assert response.data is None
    assert "password" not in response.model_dump_json()


def rows_result(columns: list[str], rows: list[list[Any]], truncated: bool = False) -> dict:
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}


@pytest.fixture
def llm_says(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replaces the LLM. Set seen["reply"] to change the reply. It keeps the last request."""
    seen: dict[str, Any] = {"reply": "unset", "calls": 0}

    def fake_call(system: str, user: str, agent: str = "default") -> str:
        seen.update(system=system, user=user, agent=agent, calls=seen["calls"] + 1)
        return seen["reply"]

    monkeypatch.setattr(response_agent, "call_llm", fake_call)
    return seen


def test_several_rows_give_a_fixed_text_and_the_rows_and_the_llm_sees_nothing(
    llm_says: dict[str, Any],
) -> None:
    result = rows_result(["name", "total"], [["Ann", 12.5], ["Bo", 7]])
    response = response_agent.for_rows(result, "SELECT 1", "Totals?")
    assert response.answer == "Here are the results (2 rows)."
    assert response.data.model_dump() == {
        "columns": ["name", "total"],
        "rows": [["Ann", 12.5], ["Bo", 7]],
        "truncated": False,
    }
    assert response.sql == "SELECT 1"  # internal only
    assert llm_says["calls"] == 0  # the rows never go to the LLM


def test_one_row_with_several_columns_does_not_go_to_the_llm(llm_says: dict[str, Any]) -> None:
    response = response_agent.for_rows(rows_result(["a", "b"], [[1, 2]]), "q", "question")
    assert response.answer == "Here is the result (1 row)."
    assert response.data.rows == [[1, 2]]
    assert llm_says["calls"] == 0


def test_two_columns_with_the_same_name_keep_both_values() -> None:
    # Rows are lists, so SELECT COUNT(*), COUNT(x) loses nothing.
    result = rows_result(["count", "count"], [[5, 3]])
    data = response_agent.for_rows(result, "q").data
    assert data.columns == ["count", "count"]
    assert data.rows == [[5, 3]]


def test_cut_rows_are_marked_and_the_text_says_so() -> None:
    response = response_agent.for_rows(rows_result(["a"], [[1], [2]], truncated=True), "q")
    assert response.data.truncated is True
    assert "first 2 rows" in response.answer


def test_no_rows_gives_the_no_data_text_and_no_data() -> None:
    response = response_agent.for_rows(rows_result(["a"], []), "q")
    assert response.answer == response_agent.NO_ROWS_TEXT
    assert response.data is None


def test_one_null_value_means_no_data() -> None:
    # SUM() of no rows is NULL. "None" would be a strange answer.
    response = response_agent.for_rows(rows_result(["total"], [[None]]), "q")
    assert response.answer == response_agent.NO_ROWS_TEXT
    assert response.data is None


def test_a_single_value_becomes_a_sentence_and_keeps_the_row(llm_says: dict[str, Any]) -> None:
    llm_says["reply"] = "There are 20 customers living in London."
    response = response_agent.for_rows(
        rows_result(["customer_count"], [[20]]), "SELECT COUNT(*)", "How many in London?"
    )
    assert response.answer == "There are 20 customers living in London."
    assert response.data.model_dump() == {
        "columns": ["customer_count"],
        "rows": [[20]],
        "truncated": False,
    }
    assert "How many in London?" in llm_says["user"]
    assert "customer_count = 20" in llm_says["user"]


def test_a_sentence_with_a_changed_value_is_not_used(llm_says: dict[str, Any]) -> None:
    llm_says["reply"] = "There are about 25 customers in London."  # the value is 20
    response = response_agent.for_rows(rows_result(["customer_count"], [[20]]), "q", "question")
    assert response.answer == "Customer count: 20"


def test_a_number_with_a_thousands_comma_and_a_float_are_accepted(llm_says: dict[str, Any]) -> None:
    llm_says["reply"] = "The total is 1,234 pounds."
    assert "1,234" in response_agent.for_rows(rows_result(["t"], [[1234.0]]), "q", "x").answer


def test_a_failed_llm_gives_the_fixed_value_text_and_the_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: Any, **kwargs: Any) -> str:
        raise LlmError("unavailable", "x")

    monkeypatch.setattr(response_agent, "call_llm", broken)
    response = response_agent.for_rows(rows_result(["customer_count"], [[20]]), "q", "question")
    assert response.answer == "Customer count: 20"
    assert response.data.rows == [[20]]


def test_the_switch_keeps_the_value_away_from_the_llm(
    llm_says: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "response_llm_sees_values", False)
    response = response_agent.for_rows(rows_result(["customer_count"], [[20]]), "q", "question")
    assert response.answer == "Customer count: 20"
    assert llm_says["calls"] == 0


def test_the_llm_text_is_used_and_it_sees_only_the_kind_and_the_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def fake_call(system: str, user: str, agent: str = "default") -> str:
        seen.update(system=system, user=user, agent=agent)
        return "  Hi! Ask me about the data.  "

    monkeypatch.setattr(response_agent, "call_llm", fake_call)
    response = response_agent.for_message("chitchat", "hello there")
    assert response.answer == "Hi! Ask me about the data."
    assert response.data is None
    assert seen["agent"] == "response_agent"
    assert "chitchat" in seen["user"]
    assert "hello there" in seen["user"]


@pytest.mark.parametrize("failure", [LlmError("unavailable", "x"), RuntimeError("anything")])
def test_a_failed_llm_call_gives_the_fixed_text_and_never_raises(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def broken(*args: Any, **kwargs: Any) -> str:
        raise failure

    monkeypatch.setattr(response_agent, "call_llm", broken)
    for kind in ("chitchat", "no_matching_data"):
        response = response_agent.for_message(kind, "hello")
        assert response.answer == response_agent.FALLBACK_TEXT[kind]


def test_an_empty_llm_text_gives_the_fixed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(response_agent, "call_llm", lambda *args, **kwargs: "   ")
    response = response_agent.for_message("chitchat", "hello")
    assert response.answer == response_agent.FALLBACK_TEXT["chitchat"]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (404, "NOT_FOUND"),
        (405, "METHOD_NOT_ALLOWED"),
        (413, "INVALID_REQUEST"),
        (400, "INVALID_REQUEST"),
        (500, "INTERNAL_ERROR"),
    ],
)
def test_an_http_error_of_the_framework_gets_the_same_shape(status: int, code: str) -> None:
    response = response_agent.for_http_error(status, "r1")
    assert (response.code, response.http_status, response.request_id) == (code, status, "r1")
    assert response.answer == response_agent.ERRORS[code][1]


@pytest.mark.parametrize(
    ("guardrail", "code"),
    [("data_change", "DATA_CHANGE_NOT_ALLOWED"), ("prompt_injection", "REQUEST_BLOCKED")],
)
def test_a_blocked_request_gets_a_fixed_refusal_and_no_llm_call(
    monkeypatch: pytest.MonkeyPatch, guardrail: str, code: str
) -> None:
    def must_not_run(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("the refusal must not be written by an LLM")

    monkeypatch.setattr(response_agent, "call_llm", must_not_run)
    response = response_agent.for_blocked(guardrail, "r1")
    assert (response.code, response.http_status, response.data) == (code, 200, None)
    assert response.answer == response_agent.ERRORS[code][1]
    assert response.request_id == "r1"


def test_the_data_change_refusal_says_what_the_assistant_can_do() -> None:
    text = response_agent.ERRORS["DATA_CHANGE_NOT_ALLOWED"][1]
    assert "only read data" in text
