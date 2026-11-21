"""Loads the eval dataset (dataset/questions.toml). One file feeds all three eval levels.

Eval step: input of every level. See README.md for the field list.
"""

import tomllib
from pathlib import Path
from typing import Any

DATASET_FILE = Path(__file__).parent / "dataset" / "questions.toml"

# These questions have no answer in the data. A good system refuses them.
REFUSE_CATEGORIES = {"chitchat", "unanswerable", "adversarial"}
SPLITS = {"dev", "test"}


def expects_refusal(row: dict[str, Any]) -> bool:
    """True when the system must not return data for this question."""
    return row["category"] in REFUSE_CATEGORIES


def load_questions(
    split: str = "all", limit: int | None = None, ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Return the questions of one split ("dev", "test", or "all"). Fill the optional fields.

    ids keeps only those questions (for a quick run of a few questions, for example after a prompt change).
    """
    with DATASET_FILE.open("rb") as file:
        rows = tomllib.load(file)["question"]
    for row in rows:
        row.setdefault("gold_tables", [])
        row.setdefault("gold_runbooks", [])
        row.setdefault("gold_sql", "")
        row.setdefault("ordered", False)
    if split != "all":
        rows = [row for row in rows if row["split"] == split]
    if ids:
        rows = [row for row in rows if row["id"] in ids]
    return rows[:limit] if limit else rows
