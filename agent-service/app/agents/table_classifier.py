"""Agent 2: Table Classifier. Picks the tables that the question needs.

Pipeline step: 2. Prompt file: app/prompts/table_classifier.md.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.llm import call_llm_json

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "table_classifier.md"


def list_table_names(tables_md: str) -> list[str]:
    """Read the table names from tables.md. Each table is one line: "- name: description".

    Example:
        list_table_names("- orders: x\\n- invoices: y") -> ["orders", "invoices"]
    """
    return re.findall(r"^- (\w+):", tables_md, flags=re.MULTILINE)


def run(
    requirements: dict[str, Any],
    tables_md: str,
    feedback_hints: list[str] | None = None,
    relationships_md: str = "",
) -> dict[str, Any]:
    """Select tables. Return selected_tables, reason, and runbook_candidates.

    Rule: when unsure, include the table.
    On a retry, feedback_hints holds the hints from step 4 (action 4A).
    relationships_md is the text of table_relationship.md. It is optional.
    Missing tables are costly (a retry loop later), so extra tables are better than missing ones.

    This agent sees only tables.md and the relationships, not the runbook index. So it cannot name runbooks,
    and runbook_candidates is always empty. Step R keeps the candidates from step 1.

    Example:
        run(requirements, tables_md)
        -> {"selected_tables": ["invoices", "accounts", "customers"],
            "reason": "Invoices have the amount. Accounts link to customers.",
            "runbook_candidates": []}
    """
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    user_message = f"Requirements:\n{json.dumps(requirements, indent=2)}\n\nTables:\n{tables_md}"
    if relationships_md:
        user_message += f"\n\nTable relationships:\n{relationships_md}"
    if feedback_hints:
        hints = "\n".join(f"- {hint}" for hint in feedback_hints)
        user_message += f"\n\nHints from the last attempt:\n{hints}"

    result = call_llm_json(system_prompt, user_message, agent="table_classifier")

    # The LLM can invent a table name. Keep only the tables that tables.md lists.
    # dict.fromkeys removes duplicates and keeps the order.
    known_tables = set(list_table_names(tables_md))
    answer = result.get("selected_tables", [])
    if not isinstance(answer, list):  # for example the LLM wrote one string, not a list
        answer = []
    selected = [
        name for name in dict.fromkeys(answer) if isinstance(name, str) and name in known_tables
    ]
    dropped = [name for name in answer if name not in selected]
    if dropped:
        # An invented name shows that the prompt or the model needs work.
        logger.warning("table_classifier: the LLM named unknown tables, dropped: %s", dropped)

    return {
        "selected_tables": selected,
        "reason": str(result.get("reason", "")),
        "runbook_candidates": [],
    }
