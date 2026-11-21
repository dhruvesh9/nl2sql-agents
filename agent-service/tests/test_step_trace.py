"""Tests for step(): the trace entry, the Langfuse span, and the failure rules."""

import pytest

from app import step_trace
from app.models import TraceEntry


class FakeObservation:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **fields: object) -> None:
        self.updates.append(fields)


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Replaces observe(). It keeps the name, the type, the input, and the updates of each span."""
    from contextlib import contextmanager

    seen: list[dict] = []

    @contextmanager
    def fake_observe(name: str, as_type: str = "span", **kwargs: object):
        observation = FakeObservation()
        seen.append(
            {"name": name, "as_type": as_type, "input": kwargs.get("input"), "obs": observation}
        )
        yield observation

    monkeypatch.setattr(step_trace, "observe", fake_observe)
    return seen


def test_a_step_adds_a_trace_entry_with_the_summary(spans: list[dict]) -> None:
    trace: list[TraceEntry] = []
    with step_trace.step(trace, "2", "table_classifier", "agent", question="q") as out:
        out["summary"] = "tables=a"
        out["output"] = {"tables": ["a"]}
    assert [(e.step, e.name, e.summary) for e in trace] == [("2", "table_classifier", "tables=a")]


def test_the_span_has_a_clear_name_a_type_the_input_and_the_output(spans: list[dict]) -> None:
    with step_trace.step([], "3", "schema_discovery", "tool", tables=["a"]) as out:
        out["summary"] = "tables=1"
        out["output"] = {"tables": ["a"]}
    span = spans[0]
    assert (span["name"], span["as_type"], span["input"]) == (
        "3_schema_discovery",
        "tool",
        {"tables": ["a"]},
    )
    assert span["obs"].updates == [
        {"output": {"tables": ["a"]}, "metadata": {"summary": "tables=1"}}
    ]


def test_a_failed_step_is_recorded_and_the_error_goes_on(spans: list[dict]) -> None:
    trace: list[TraceEntry] = []
    with pytest.raises(RuntimeError), step_trace.step(trace, "5", "sql_generator", "agent"):
        raise RuntimeError("model down")
    assert trace[0].summary == "error: model down"


def test_a_summary_that_the_step_set_before_the_error_is_kept(spans: list[dict]) -> None:
    trace: list[TraceEntry] = []
    with pytest.raises(RuntimeError), step_trace.step(trace, "7", "sql_execution", "tool") as out:
        out["summary"] = "error: bad column; sql=SELECT 1"
        raise RuntimeError("x")
    assert trace[0].summary == "error: bad column; sql=SELECT 1"


def test_a_step_without_input_sends_no_empty_input(spans: list[dict]) -> None:
    with step_trace.step([], "8", "response_agent", "agent"):
        pass
    assert spans[0]["input"] is None
