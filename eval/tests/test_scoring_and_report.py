"""Tests for the table scores, the percentile, the summary, and the regression gate."""

import pytest

import report
import scoring


def test_score_tables_pass_warn_fail() -> None:
    assert scoring.score_tables(["a", "b"], ["b", "a"])["status"] == "PASS"
    warn = scoring.score_tables(["a"], ["a", "x"])
    assert warn["status"] == "WARN"
    assert warn["extra"] == ["x"]
    assert warn["recall"] == 100
    assert warn["precision"] == 50
    fail = scoring.score_tables(["a", "b"], ["a"])
    assert fail["status"] == "FAIL"
    assert fail["missing"] == ["b"]
    assert fail["recall"] == 50


def test_runbook_recall_is_none_when_no_runbook_is_needed() -> None:
    assert scoring.runbook_recall([], ["x"]) is None
    assert scoring.runbook_recall(["a", "b"], ["a"]) == 50


@pytest.mark.parametrize(("percent", "expected"), [(50, 3), (95, 5), (100, 5)])
def test_percentile_uses_the_nearest_rank(percent: float, expected: float) -> None:
    assert scoring.percentile([5, 1, 3, 2, 4], percent) == expected
    assert scoring.percentile([], 50) == 0


def result(id_: str, attempt: int, status: str, **extra) -> dict:
    return {"id": id_, "attempt": attempt, "status": status, "elapsed_ms": 100, **extra}


def test_sql_summary_skips_skipped_questions_and_shows_the_spread() -> None:
    results = [
        result("q1", 1, "MATCH"),
        result("q2", 1, "ERROR"),
        result("q3", 1, "SKIP"),
        result("q1", 2, "MATCH"),
        result("q2", 2, "MATCH"),
        result("q3", 2, "SKIP"),
    ]
    summary = report.summarize_level("sql", results)
    accuracy = summary["metrics"]["execution_accuracy"]
    assert (accuracy["min"], accuracy["max"], accuracy["mean"]) == (50, 100, 75)
    assert summary["questions"] == 2
    assert summary["skipped"] == 1
    assert summary["unstable_questions"] == ["q2"]  # ERROR in attempt 1, MATCH in attempt 2


def test_system_summary_scores_answers_and_refusals_apart() -> None:
    results = [
        result("a", 1, "MATCH", kind="answer"),
        result("b", 1, "FAILED", kind="answer"),
        result("r1", 1, "REFUSED", kind="refuse"),
        result("r2", 1, "ANSWERED", kind="refuse"),
    ]
    metrics = report.summarize_level("system", results)["metrics"]
    assert metrics["execution_accuracy"]["mean"] == 50
    assert metrics["refusal_accuracy"]["mean"] == 50


def level_summary(accuracy: float) -> dict:
    return {"levels": {"sql": {"metrics": {"execution_accuracy": {"mean": accuracy}}}}}


def test_the_gate_reports_only_a_fall_bigger_than_the_limit() -> None:
    assert report.regressions(level_summary(80), level_summary(83), max_drop=5) == []
    problems = report.regressions(level_summary(70), level_summary(83), max_drop=5)
    assert problems == ["sql.execution_accuracy: 83.0 -> 70.0"]
    assert report.regressions(level_summary(90), level_summary(83), max_drop=5) == []
