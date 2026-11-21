"""What version of the prompts and models runs. Sent to Langfuse with every trace.

Pipeline step: infrastructure (observability).
When an answer gets worse, the first question is "what changed?". A hash of the prompt files and the
model names answer it, because the trace then shows exactly which prompts and models made the answer.
"""

import hashlib
from functools import cache
from pathlib import Path

from app.llm import options_for

PROMPTS_DIR = Path(__file__).parent / "prompts"
AGENTS = ["query_analyzer", "table_classifier", "sql_generator", "response_agent"]


@cache
def prompt_version() -> str:
    """A short hash of all prompt files. A change in one prompt gives a new value."""
    digest = hashlib.sha256()
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def models_text() -> str:
    """The model of each agent as one short text, for example "query_analyzer=Qwen/Qwen3.8-Flash, ..."."""
    return ", ".join(f"{agent}={options_for(agent)['model']}" for agent in AGENTS)[:200]


def trace_metadata() -> dict[str, str]:
    """The metadata for a trace: prompt version and models."""
    return {"prompt_version": prompt_version(), "models": models_text()}
