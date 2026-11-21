"""Agent 1: User Query Analyzer. Turns the question into structured requirements.

Pipeline step: 1. Prompt file: app/prompts/query_analyzer.md.
"""

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.llm import call_llm_json

logger = logging.getLogger(__name__)

GUARDRAILS = {"none", "data_change", "prompt_injection"}

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "query_analyzer.md"

# Every answer must have these keys. A missing key gets this default value.
DEFAULTS: dict[str, Any] = {
    "guardrail": "none",
    "intent": "",
    "requested_fields": [],
    "filters": [],
    "aggregations": [],
    "business_concepts": [],
    "runbook_candidates": [],
}


def run(question: str, index_md: str) -> dict[str, Any]:
    """Analyze the question. Return the requirements as a dict.

    Output keys: guardrail, intent, requested_fields, filters, aggregations, business_concepts,
    runbook_candidates.

    Example:
        run("Total unpaid invoice amount per customer in 2025", index_md)
        -> {"intent": "aggregate", "requested_fields": ["customer", "total amount"],
            "filters": ["status unpaid", "year 2025"], "aggregations": ["sum"],
            "business_concepts": ["unpaid invoice"], "runbook_candidates": ["invoice_status"]}
    """
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")

    user_message = f"Question:\n{question}\n\nIndex (knowledge base):\n{index_md}"
    result = call_llm_json(system_prompt, user_message, agent="query_analyzer")

    # Fill the missing keys, so the next steps can always read all six.
    # deepcopy gives each answer its own lists. A shared list would keep changes from other requests.
    for key, default in DEFAULTS.items():
        result.setdefault(key, deepcopy(default))

    # A guardrail that is not one of the three words is not trusted as a block, and not used.
    # The SQL guard and the read-only transaction in db-service still protect the data.
    # isinstance first: a list or a dict is not hashable, and "in a set" would raise TypeError.
    if not isinstance(result["guardrail"], str) or result["guardrail"] not in GUARDRAILS:
        logger.warning(
            "query_analyzer: unknown guardrail value", extra={"value": str(result["guardrail"])}
        )
        result["guardrail"] = "none"

    # The LLM can invent a runbook name, or send something that is not a list (for example null).
    # Keep only the names that the index lists. In index.md, each name is between backticks.
    candidates = result["runbook_candidates"]
    if not isinstance(candidates, list):
        candidates = []
    result["runbook_candidates"] = [
        name for name in candidates if isinstance(name, str) and f"`{name}`" in index_md
    ]
    return result
