"""Tests for call_llm_json. A fake call_llm replaces the real LLM, so no network is used."""

import pytest

from app import llm


def fake_llm(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> list[str]:
    """Make call_llm return the given answers in order. Return the list of user messages it got."""
    user_messages: list[str] = []

    def fake_call_llm(system_prompt: str, user_message: str, agent: str = "default") -> str:
        user_messages.append(user_message)
        return answers.pop(0)

    monkeypatch.setattr(llm, "call_llm", fake_call_llm)
    return user_messages


def test_clean_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ['{"a": 1}'])
    assert llm.call_llm_json("system", "user") == {"a": 1}


def test_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ['```json\n{"a": 1}\n```'])
    assert llm.call_llm_json("system", "user") == {"a": 1}


def test_fence_without_the_word_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ['```\n{"a": 1}\n```'])
    assert llm.call_llm_json("system", "user") == {"a": 1}


def test_spaces_inside_values_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ['{"name": "Customer 001"}'])
    assert llm.call_llm_json("system", "user") == {"name": "Customer 001"}


def test_text_around_the_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ['Here is the JSON: {"a": 1} Hope this helps!'])
    assert llm.call_llm_json("system", "user") == {"a": 1}


def test_bad_json_then_good_json_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = fake_llm(monkeypatch, ['{"a": 1,}', '{"a": 1}'])
    assert llm.call_llm_json("system", "user") == {"a": 1}
    assert len(messages) == 2
    # the retry message must hold the bad answer and the parse error
    assert '{"a": 1,}' in messages[1]
    assert "Parse error" in messages[1]


def test_retry_answer_with_fences_is_cleaned(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ["not json", '```json\n{"a": 1}\n```'])
    assert llm.call_llm_json("system", "user") == {"a": 1}


def test_bad_json_twice_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    messages = fake_llm(monkeypatch, ["bad one", "bad two"])
    with pytest.raises(ValueError, match="bad two"):
        llm.call_llm_json("system", "user")
    assert len(messages) == 2  # one try and one retry, never more


def test_empty_answer_fails_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ["", ""])
    with pytest.raises(ValueError):
        llm.call_llm_json("system", "user")


def test_list_is_not_accepted_as_an_object(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, ['[{"a": 1}]', '{"a": 1}'])
    assert llm.call_llm_json("system", "user") == {"a": 1}


def test_system_prompt_asks_for_json_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_call_llm(system_prompt: str, user_message: str, agent: str = "default") -> str:
        seen.append(system_prompt)
        return '{"a": 1}'

    monkeypatch.setattr(llm, "call_llm", fake_call_llm)
    llm.call_llm_json("Return JSON.", "user")
    assert seen[0].startswith("Return JSON.") and "JSON only" in seen[0]
