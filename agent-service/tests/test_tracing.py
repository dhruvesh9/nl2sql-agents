"""Tests for the Langfuse helpers. Langfuse is off in tests, so every helper must do nothing."""

import pytest

from app import tracing, versioning
from app.config import settings


def test_with_tracing_off_the_helpers_do_nothing_and_do_not_fail() -> None:
    assert tracing.trace_id_for("abc") is None
    with tracing.request_trace("ask-quick", "abc", input={"question": "q"}) as trace:
        trace.update(output={"x": 1})
    tracing.score("outcome", "data", "CATEGORICAL")  # no error


def test_observe_passes_the_error_on_when_tracing_is_off() -> None:
    try:
        with tracing.observe("x"):
            raise ValueError("boom")
    except ValueError as error:
        assert str(error) == "boom"
    else:
        raise AssertionError("the error must go on")


def test_prompt_version_changes_when_a_prompt_changes(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.md").write_text("one")
    monkeypatch.setattr(versioning, "PROMPTS_DIR", tmp_path)
    versioning.prompt_version.cache_clear()
    first = versioning.prompt_version()
    versioning.prompt_version.cache_clear()
    (tmp_path / "a.md").write_text("two")
    assert versioning.prompt_version() != first
    versioning.prompt_version.cache_clear()


def test_the_trace_metadata_is_short_text() -> None:
    metadata = versioning.trace_metadata()
    assert set(metadata) == {"prompt_version", "models"}
    assert all(isinstance(value, str) and len(value) <= 200 for value in metadata.values())
    assert "query_analyzer=" in metadata["models"]


def test_tracing_on_starts_the_client_with_the_environment_and_the_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This is the start-up path that only runs when Langfuse is on. A wrong setting name crashed the
    # whole service at start, and no other test noticed because the tests run with Langfuse off.
    created: dict = {}

    class FakeLangfuse:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

    monkeypatch.setattr(tracing, "Langfuse", FakeLangfuse)
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(settings, "langfuse_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk")
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "app_version", "1.2.3")
    tracing.init_tracing()
    assert created["environment"] == "test"
    assert created["release"] == "1.2.3"
    monkeypatch.setattr(tracing, "_client", None)  # leave tracing off for the other tests


@pytest.mark.parametrize("request_id", ["0123456789abcdef0123456789abcdef", "from-a-gateway-123"])
def test_the_trace_id_is_the_request_id_or_a_stable_hash_of_it(
    monkeypatch: pytest.MonkeyPatch, request_id: str
) -> None:
    class FakeClient:
        def create_trace_id(self, seed: str) -> str:
            return "hash-of-" + seed

    monkeypatch.setattr(tracing, "_client", FakeClient())
    expected = request_id if len(request_id) == 32 else "hash-of-" + request_id
    assert tracing.trace_id_for(request_id) == expected
    monkeypatch.setattr(tracing, "_client", None)
