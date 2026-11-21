"""Compares two SQL result sets. This is "execution accuracy".

Eval step: level 2 (SQL generator) and level 3 (whole system).
We do not compare the SQL text. Many different queries are correct. We compare the rows.
Rules: column names are ignored, numbers are rounded to 2 decimals, and the row order is
ignored unless the question asks for an order. A different column order is accepted.
"""

from typing import Any


def _cell(value: Any) -> str:
    """Turn one value into text that is equal for 5, 5.0 and "5.00"."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return f"{round(float(value), 2):.2f}"
    text = str(value).strip()
    try:
        return f"{round(float(text), 2):.2f}"
    except ValueError:
        return text


def _rows(rows: list[list[Any]], ordered: bool) -> list[tuple[str, ...]]:
    cells = [tuple(_cell(value) for value in row) for row in rows]
    return cells if ordered else sorted(cells)


def compare_results(
    gold_rows: list[list[Any]], got_rows: list[list[Any]], ordered: bool = False
) -> tuple[bool, str]:
    """Return (same, reason). The reason is short and says why the rows differ."""
    if len(gold_rows) != len(got_rows):
        return False, f"row count: expected {len(gold_rows)}, got {len(got_rows)}"
    if gold_rows and len(gold_rows[0]) != len(got_rows[0]):
        return False, f"column count: expected {len(gold_rows[0])}, got {len(got_rows[0])}"
    if _rows(gold_rows, ordered) == _rows(got_rows, ordered):
        return True, "same rows"
    # The same values in another column order is still a correct answer.
    gold_sorted = sorted(tuple(sorted(row)) for row in _rows(gold_rows, False))
    got_sorted = sorted(tuple(sorted(row)) for row in _rows(got_rows, False))
    if not ordered and gold_sorted == got_sorted:
        return True, "same rows, other column order"
    return False, "the values differ"
