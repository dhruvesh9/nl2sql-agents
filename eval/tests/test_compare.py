"""Tests for execution accuracy. The rules decide if an answer counts as correct."""

from compare import compare_results


def test_same_rows_in_another_order_match() -> None:
    assert compare_results([[1, "a"], [2, "b"]], [[2, "b"], [1, "a"]])[0]


def test_row_order_counts_when_the_question_asks_for_an_order() -> None:
    assert not compare_results([[1], [2]], [[2], [1]], ordered=True)[0]
    assert compare_results([[1], [2]], [[1], [2]], ordered=True)[0]


def test_int_float_and_text_numbers_are_equal() -> None:
    assert compare_results([[5, "20.00"]], [[5.0, 20]])[0]


def test_numbers_are_rounded_to_two_decimals() -> None:
    assert compare_results([[1.0]], [[1.004]])[0]
    assert not compare_results([[1.0]], [[1.02]])[0]


def test_another_column_order_is_accepted() -> None:
    same, reason = compare_results([["Pixel", 3]], [[3, "Pixel"]])
    assert same
    assert "column order" in reason


def test_different_values_row_count_and_column_count_fail() -> None:
    assert compare_results([[1]], [[2]]) == (False, "the values differ")
    assert "row count" in compare_results([[1]], [[1], [2]])[1]
    assert "column count" in compare_results([[1, 2]], [[1]])[1]


def test_none_and_empty_results() -> None:
    assert compare_results([[None]], [[None]])[0]
    assert compare_results([], [])[0]
    assert not compare_results([[None]], [["None"]])[0]
