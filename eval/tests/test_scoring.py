"""Tests for the scoring rules of the Table Classifier eval.

The rules are simple, but the accuracy number depends on them, so they must be right.
"""

import pytest

import run_table_classifier as ev


def answer(tables: list[str]) -> dict:
    return {"selected_tables": tables, "reason": "x", "requirements": {}, "trace": []}


def score(expected: list[str], got: list[str]) -> dict:
    return ev.score_question({"expected_tables": ";".join(expected)}, answer(got))


def test_exact_match_is_a_pass_in_any_order() -> None:
    result = score(["invoices", "accounts"], ["accounts", "invoices"])
    assert result["table_status"] == "PASS"


def test_extra_tables_are_a_warning_and_are_listed() -> None:
    result = score(["invoices"], ["invoices", "payments", "accounts"])
    assert result["table_status"] == "WARN"
    assert result["extra_tables"] == "accounts;payments"
    assert result["missing_tables"] == ""


def test_a_missing_table_is_a_failure_even_when_there_are_extra_tables() -> None:
    result = score(["invoices", "accounts"], ["invoices", "payments", "orders"])
    assert result["table_status"] == "FAIL"
    assert result["missing_tables"] == "accounts"
    assert result["extra_tables"] == "orders;payments"


def test_selecting_no_table_when_tables_are_needed_is_a_failure() -> None:
    assert score(["invoices"], [])["table_status"] == "FAIL"


def test_the_same_table_twice_does_not_count_as_an_extra_table() -> None:
    assert score(["invoices"], ["invoices", "invoices"])["table_status"] == "PASS"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("a;b", ["a", "b"]), ("a", ["a"]), ("", []), ("a;;b;", ["a", "b"])],
)
def test_split_list(text: str, expected: list[str]) -> None:
    assert ev.split_list(text) == expected


def result_row(status: str, number: int = 0) -> dict:
    return {
        "id": f"T{number}",
        "category": "x",
        "table_status": status,
        "extra_tables": "a;b" if status == "WARN" else "",
    }


def accuracy_for(passes: int, warns: int, fails: int) -> float:
    rows = (
        [result_row("PASS", n) for n in range(passes)]
        + [result_row("WARN", n) for n in range(warns)]
        + [result_row("FAIL", n) for n in range(fails)]
    )
    return ev.print_summary(rows)


def test_a_warning_counts_as_a_success_in_the_accuracy() -> None:
    assert accuracy_for(passes=1, warns=1, fails=0) == 100.0


def test_a_failure_does_not_count_in_the_accuracy() -> None:
    assert accuracy_for(passes=20, warns=7, fails=3) == 90.0


def test_the_target_is_reached_at_exactly_90_percent_and_not_below() -> None:
    assert accuracy_for(passes=27, warns=0, fails=3) >= ev.TARGET_PERCENT
    assert accuracy_for(passes=26, warns=0, fails=4) < ev.TARGET_PERCENT


def test_an_empty_run_gives_zero_and_does_not_crash() -> None:
    assert ev.print_summary([]) == 0.0
