"""Tests for the time budget of a request."""

import pytest

from app import deadline, step_trace


def test_without_a_started_budget_nothing_is_checked() -> None:
    deadline._deadline.set(None)
    deadline.check("1 query_analyzer")  # no error


def test_inside_the_budget_the_check_passes() -> None:
    deadline.start(60)
    deadline.check("1 query_analyzer")


def test_after_the_budget_the_check_raises_a_timeout_that_names_the_step() -> None:
    deadline.start(-1)
    with pytest.raises(TimeoutError, match="before step 5 sql_generator"):
        deadline.check("5 sql_generator")


def test_a_step_does_not_start_when_the_budget_is_used() -> None:
    deadline.start(-1)
    ran = []
    trace: list = []
    with pytest.raises(TimeoutError), step_trace.step(trace, "5", "sql_generator", "agent"):
        ran.append("body")
    assert ran == []  # the LLM call inside the step never happened
    assert "time budget" in trace[0].summary


def test_the_answer_step_runs_even_when_the_budget_is_used() -> None:
    deadline.start(-1)
    ran = []
    with step_trace.step([], "8", "response_agent", "agent", check_deadline=False):
        ran.append("body")
    assert ran == ["body"]
