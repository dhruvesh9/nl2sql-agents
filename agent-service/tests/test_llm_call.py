"""Tests for call_llm and the per-agent LLM options. A fake Together client is used, so no network."""

from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from app import llm
from app.config import LlmParams, Settings, settings

AGENTS = ("query_analyzer", "table_classifier", "table_feedback", "sql_generator", "sql_validator")


@pytest.fixture(autouse=True)
def default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Known defaults, so a local .env file cannot change the result of a test."""
    monkeypatch.setattr(settings, "llm_model", "default-model")
    monkeypatch.setattr(settings, "llm_temperature", 0.0)
    monkeypatch.setattr(settings, "llm_reasoning_enabled", None)
    for agent in AGENTS:
        monkeypatch.setattr(settings, agent, LlmParams())


def delta(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))], usage=None
    )


class FakeTogether:
    """Replaces the Together client. It keeps the last request, and streams fixed chunks."""

    last_request: ClassVar[dict[str, Any]] = {}
    chunks: ClassVar[list[SimpleNamespace]] = []

    def __init__(self, api_key: str) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs: Any):
        FakeTogether.last_request = kwargs
        return iter(FakeTogether.chunks)


@pytest.fixture
def together(monkeypatch: pytest.MonkeyPatch) -> type[FakeTogether]:
    FakeTogether.last_request = {}
    FakeTogether.chunks = [delta('{"a"'), delta(": 1}")]
    monkeypatch.setattr(llm, "Together", FakeTogether)
    return FakeTogether


def test_the_answer_is_the_joined_parts_of_the_stream(together: type[FakeTogether]) -> None:
    # Thinking tokens have no content. A usage-only chunk has no choices. Both must be skipped.
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    together.chunks = [
        delta(None),
        delta('{"a"'),
        delta(None),
        delta(": 1}"),
        SimpleNamespace(choices=[], usage=usage),
    ]
    assert llm.call_llm("system", "user") == '{"a": 1}'


def test_the_request_always_streams_and_sends_both_messages(together: type[FakeTogether]) -> None:
    # Some models (for example Qwen3.8-Flash) refuse a request that does not stream.
    llm.call_llm("the system text", "the user text")
    request = together.last_request
    assert request["stream"] is True
    assert request["messages"] == [
        {"role": "system", "content": "the system text"},
        {"role": "user", "content": "the user text"},
    ]


def test_without_any_setting_only_the_basic_options_are_sent(together: type[FakeTogether]) -> None:
    # A model can reject an option it does not know, so we send an option only when it is set.
    llm.call_llm("s", "u", agent="table_classifier")
    request = together.last_request
    assert request["model"] == "default-model"
    assert request["temperature"] == 0.0
    for option in ("top_p", "top_k", "reasoning"):
        assert option not in request


def test_reasoning_false_is_sent_and_is_not_the_same_as_not_set(
    together: type[FakeTogether], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "query_analyzer", LlmParams(reasoning_enabled=False))
    llm.call_llm("s", "u", agent="query_analyzer")
    assert together.last_request["reasoning"] == {"enabled": False}


def test_the_settings_of_an_agent_win_over_the_defaults(
    together: type[FakeTogether], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "llm_reasoning_enabled", False)
    monkeypatch.setattr(
        settings,
        "table_classifier",
        LlmParams(model="big-model", temperature=0.3, top_p=0.9, top_k=40, reasoning_enabled=True),
    )
    llm.call_llm("s", "u", agent="table_classifier")
    request = together.last_request
    assert request["model"] == "big-model"
    assert request["temperature"] == 0.3
    assert request["top_p"] == 0.9
    assert request["top_k"] == 40
    assert request["reasoning"] == {"enabled": True}


def test_the_settings_of_one_agent_do_not_change_another_agent(
    together: type[FakeTogether], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "table_classifier", LlmParams(reasoning_enabled=True))
    llm.call_llm("s", "u", agent="query_analyzer")
    assert "reasoning" not in together.last_request


def test_an_option_that_an_agent_leaves_empty_uses_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "query_analyzer", LlmParams(top_k=20))
    options = llm.options_for("query_analyzer")
    assert options["model"] == "default-model"
    assert options["temperature"] == 0.0
    assert options["top_k"] == 20


def test_an_unknown_agent_name_uses_the_defaults() -> None:
    options = llm.options_for("not_an_agent")
    assert options["model"] == "default-model"
    assert options["top_p"] is None


def test_json_call_passes_the_agent_name_to_both_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names: list[str] = []
    answers = ["not json", '{"ok": true}']

    def fake_call_llm(system_prompt: str, user_message: str, agent: str = "default") -> str:
        names.append(agent)
        return answers.pop(0)

    monkeypatch.setattr(llm, "call_llm", fake_call_llm)
    assert llm.call_llm_json("s", "u", agent="table_classifier") == {"ok": True}
    assert names == ["table_classifier", "table_classifier"]


def test_agent_options_can_be_set_with_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TABLE_CLASSIFIER__REASONING_ENABLED", "true")
    monkeypatch.setenv("TABLE_CLASSIFIER__TOP_K", "40")
    monkeypatch.setenv("QUERY_ANALYZER__REASONING_ENABLED", "false")

    fresh = Settings(_env_file=None)
    assert fresh.table_classifier.reasoning_enabled is True
    assert fresh.table_classifier.top_k == 40
    assert fresh.query_analyzer.reasoning_enabled is False
    assert fresh.sql_generator.reasoning_enabled is None  # not set: the default is used
