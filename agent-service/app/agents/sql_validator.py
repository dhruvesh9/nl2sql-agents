"""Step 6: SQL Validator. Hard checks in code, then an LLM judge, then a Python score.

Pipeline step: 6 (Loop B). Prompt file: app/prompts/sql_validator.md.
"""

from typing import Any

# Weights for the final score. The score is computed in Python, not in the LLM.
WEIGHTS = {"tables": 25, "joins": 30, "selection_and_filters": 30, "performance": 15}


def run(
    sql: str, requirements: dict[str, Any], schema_text: str, schema_tables: list[str]
) -> dict[str, Any]:
    """Validate the SQL. Return passed, score, hard_checks, category_scores, and feedback.

    Part A: hard checks in code (SQL guard with sqlglot, tables in the schema, /plan is valid).
    Part B: LLM judge scores tables, joins, selection_and_filters, and performance (0 to 100).
    Part C: weighted score in Python with WEIGHTS.
    passed is True only if all hard checks pass AND the score is at least PASS_SCORE.

    Example:
        -> {"passed": false, "score": 62,
            "hard_checks": {"guard": true, "tables_in_schema": true, "plan_valid": true},
            "category_scores": {"tables": 90, "joins": 30, "selection_and_filters": 70,
                                "performance": 80},
            "feedback": "Join invoices to accounts with account_id, not customer_id."}
    """
    raise NotImplementedError(
        "The SQL Validator (step 6) is not implemented yet. See the roadmap in README.md."
    )
