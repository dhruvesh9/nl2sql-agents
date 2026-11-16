"""Agent 5: SQL Generator. Writes a candidate SELECT query.

Pipeline step: 5 (Loop B). Prompt file: app/prompts/sql_generator.md.
"""

from typing import Any


def run(
    requirements: dict[str, Any],
    schema_text: str,
    runbook_texts: list[str],
    dialect: str,
    feedback: str | None = None,
) -> dict[str, Any]:
    """Generate SQL. Return sql and explanation.

    Rules: SELECT only. Use only the given tables and columns. Use only foreign key paths
    or runbook join paths. Write SQL in the given dialect.
    On a retry, feedback holds the feedback from step 6 (action 6B).

    Example:
        -> {"sql": "SELECT c.name, SUM(i.total_amount) FROM ...",
            "explanation": "Join invoices to customers through accounts."}
    """
    raise NotImplementedError(
        "The SQL Generator (step 5) is not implemented yet. See the roadmap in README.md."
    )
