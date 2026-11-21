"""Tests for agent 5 (SQL Generator). A fake LLM answer replaces the real LLM."""

from typing import Any

import pytest

from app.agents import sql_generator
from app.errors import LlmError


def test_sql_generator_cleans_fence_and_semicolon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sql_generator,
        "call_llm_json",
        lambda *args, **kwargs: {"sql": "```sql\nSELECT 1;\n```", "explanation": "e"},
    )
    assert sql_generator.run({}, "schema", [], "postgresql")["sql"] == "SELECT 1"


def test_sql_generator_sends_runbooks_and_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_llm(system: str, user: str, **kwargs: Any) -> dict[str, str]:
        seen["user"] = user
        return {"sql": "SELECT 1"}

    monkeypatch.setattr(sql_generator, "call_llm_json", fake_llm)
    sql_generator.run({}, "schema", ["RUNBOOK TEXT"], "postgresql", feedback="fix the join")
    assert "RUNBOOK TEXT" in seen["user"]
    assert "fix the join" in seen["user"]


def test_sql_generator_rejects_missing_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sql_generator, "call_llm_json", lambda *a, **k: {"explanation": "e"})
    with pytest.raises(LlmError):
        sql_generator.run({}, "schema", [], "postgresql")
