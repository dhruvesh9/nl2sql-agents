"""Counts the LLM tokens that agent-service code uses while the eval runs it in this process.

Eval step: cost measurement for levels 1 and 2. (Level 3 calls agent-service over HTTP, so the
tokens are in Langfuse and the logs of that process, not here.)
app/llm.py logs every call ("llm_call") with the token counts in the field total_tokens.
We read that field, so agent-service does not need any change.
"""

import logging

_TOTALS = {"tokens": 0, "calls": 0}


def _count(record: logging.LogRecord) -> bool:
    """A logging filter. It reads the llm_call records and never blocks a record."""
    if record.getMessage() == "llm_call":
        _TOTALS["tokens"] += getattr(record, "total_tokens", 0)
        _TOTALS["calls"] += 1
    return True


def start_counting() -> None:
    """Start to count. Call this one time at the start of a run."""
    llm_logger = logging.getLogger("app.llm")
    llm_logger.setLevel(logging.INFO)  # the call log is INFO. A higher level would drop it.
    llm_logger.propagate = False  # count the calls, but keep one line per call off the report
    llm_logger.addFilter(_count)


def reset() -> None:
    _TOTALS.update(tokens=0, calls=0)


def read() -> dict[str, int]:
    """Return the tokens and the LLM calls since the last reset."""
    return dict(_TOTALS)
