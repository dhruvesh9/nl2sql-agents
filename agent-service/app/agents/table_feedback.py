"""Agent 4: Table Feedback. Checks if the live schema is enough to answer the question.

Pipeline step: 4 (Loop A). Prompt file: app/prompts/table_feedback.md.
"""

from typing import Any


def run(requirements: dict[str, Any], schema_text: str) -> dict[str, Any]:
    """Judge the schema. Return sufficient, score, missing, hints, and mandatory_failure.

    score is 0 to 100. mandatory_failure explains a problem that retries cannot fix
    (for example, the data does not exist in the database). Use null when there is none.

    Example:
        -> {"sufficient": false, "score": 55, "missing": ["customers"],
            "hints": ["Add customers to get the customer name"], "mandatory_failure": null}
    """
    raise NotImplementedError(
        "The Table Feedback agent (step 4) is not implemented yet. See the roadmap in README.md."
    )
