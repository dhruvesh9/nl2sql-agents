"""Agent 5: SQL Generator. Writes a candidate SELECT query.

Pipeline step: 5 (Loop B). Prompt file: app/prompts/sql_generator.md.
"""

import json
import re
from pathlib import Path
from typing import Any

from app.errors import LlmError
from app.llm import call_llm_json

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "sql_generator.md"


def _clean_sql(sql: str) -> str:
    """Remove a code fence and the trailing semicolon. Some LLMs add them even when told not to."""
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql.strip(), flags=re.IGNORECASE)
    return sql.strip().rstrip(";").strip()


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
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    user_message = (
        f"Requirements:\n{json.dumps(requirements, indent=2)}\n\n"
        f"Dialect: {dialect}\n\nSchema:\n{schema_text}"
    )
    # Irrelevant text costs tokens and confuses the LLM, so add runbooks only when we have them.
    if runbook_texts:
        user_message += "\n\nRunbooks (business rules):\n" + "\n\n".join(runbook_texts)
    if feedback:
        user_message += f"\n\nFeedback from the last attempt:\n{feedback}"

    result = call_llm_json(system_prompt, user_message, agent="sql_generator")

    sql = result.get("sql")
    if not isinstance(sql, str) or not _clean_sql(sql):
        raise LlmError("bad_output", "sql_generator: the LLM did not return a 'sql' text")
    return {"sql": _clean_sql(sql), "explanation": str(result.get("explanation", ""))}
