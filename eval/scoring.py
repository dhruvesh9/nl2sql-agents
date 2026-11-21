"""Scores for the table classifier and the query analyzer, and small statistics helpers.

Eval step: level 1 (table classifier), plus the runbook recall of the Query Analyzer.
A missing table is fatal, because the SQL generator cannot use a table that it never sees.
An extra table only costs tokens. So recall is the main number and precision is the second.
"""

import math


def score_tables(gold: list[str], got: list[str]) -> dict:
    """Compare the selected tables with the gold tables.

    status: PASS (same set), WARN (all gold tables found, with extras), FAIL (a table is missing).
    """
    gold_set, got_set = set(gold), set(got)
    missing = sorted(gold_set - got_set)
    extra = sorted(got_set - gold_set)
    status = "FAIL" if missing else ("WARN" if extra else "PASS")
    return {
        "status": status,
        "recall": 100 * len(gold_set & got_set) / len(gold_set) if gold_set else 100.0,
        "precision": 100 * len(gold_set & got_set) / len(got_set) if got_set else 0.0,
        "missing": missing,
        "extra": extra,
    }


def runbook_recall(gold: list[str], got: list[str]) -> float | None:
    """Percent of the gold runbooks that the Query Analyzer found. None if no runbook is needed."""
    if not gold:
        return None
    return 100 * len(set(gold) & set(got)) / len(set(gold))


def percentile(values: list[float], percent: float) -> float:
    """Nearest-rank percentile. An empty list gives 0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(ordered)) - 1)
    return ordered[index]
