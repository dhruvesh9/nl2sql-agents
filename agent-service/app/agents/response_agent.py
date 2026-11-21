"""Response Agent: turns every outcome into the one response that the client gets.

Pipeline step: 8 (Response Builder). Every pipeline ends here, for success and for failure.

Two paths:
- Deterministic, no LLM: errors and data. An error needs no LLM, and it must also work when the
  LLM is down. Rows go straight into the response. The LLM never sees result rows.
- LLM, no reasoning: a short friendly text for non-error cases: a greeting, a question that no
  table can answer, and a result of ONE value ("There are 20 customers in London."). The
  value-sentence must contain the exact value, or we use a fixed text. If a call fails, a fixed
  text is used. So this agent never raises an error.
- Result rows: they go into `data` as an array, and the LLM never sees them. The only exception is
  a result of one row and one column: its value goes to the LLM so it can write a sentence, and
  settings.response_llm_sees_values turns that off. With 2 or more values, `answer` is a fixed text.

The response always has an `answer` text. `data` is there only when the query returned rows.

Other agents do not write messages. They raise errors (app/errors.py, DbServiceError, ...).
error_code() maps each error to a code. ERRORS holds the text and the HTTP status of each code.
"""

import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.db_client import DbServiceError
from app.errors import LlmError
from app.knowledge import KnowledgeServiceError
from app.llm import call_llm
from app.models import AskResponse, ResultData, TraceEntry

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "response_agent.md"

# code -> (HTTP status, text for the user). The text never holds details of the real error.
ERRORS: dict[str, tuple[int, str]] = {
    "LLM_BUSY": (503, "The AI service is busy right now. Please try again in a minute."),
    "LLM_UNAVAILABLE": (503, "The AI service is not available. Please try again later."),
    "LLM_BAD_OUTPUT": (502, "I could not work out an answer. Please ask in another way."),
    "QUERY_FAILED": (
        200,
        "I could not build a valid query for that question. Please ask in another way.",
    ),
    "SERVICE_UNAVAILABLE": (503, "A service that I need is not available. Please try again later."),
    "INVALID_REQUEST": (422, "Please send a question that is not empty and not too long."),
    "NOT_IMPLEMENTED": (501, "This feature is not available yet."),
    "INTERNAL_ERROR": (500, "Something went wrong on our side. Please try again."),
}

# Used when the LLM cannot write the text. These must be good enough on their own.
FALLBACK_TEXT = {
    "chitchat": "Hello! I can answer questions about the company data. What would you like to know?",
    "no_matching_data": "I could not find data for that question. Please ask in another way.",
}
NO_ROWS_TEXT = "No data matches your question."


def error_code(error: Exception) -> str:
    """Return the code for an error. An unknown error gives INTERNAL_ERROR."""
    if isinstance(error, LlmError):
        return {"rate_limited": "LLM_BUSY", "unavailable": "LLM_UNAVAILABLE"}.get(
            error.kind, "LLM_BAD_OUTPUT"
        )
    if isinstance(error, DbServiceError):
        # 400 means db-service rejected the SQL. Any other status means db-service has a problem.
        return "QUERY_FAILED" if error.status_code == 400 else "SERVICE_UNAVAILABLE"
    if isinstance(error, KnowledgeServiceError | httpx.HTTPError):
        return "SERVICE_UNAVAILABLE"
    if isinstance(error, NotImplementedError):
        return "NOT_IMPLEMENTED"
    return "INTERNAL_ERROR"


def for_error(
    error: Exception, request_id: str = "", trace: list[TraceEntry] | None = None
) -> AskResponse:
    """Build the error response. The real error goes to the log, not to the client."""
    code = error_code(error)
    http_status, text = ERRORS[code]
    # Only an unknown error needs the stack trace. The other errors are known cases.
    logger.error(
        "request %s failed with %s: %s",
        request_id,
        code,
        error,
        exc_info=error if code == "INTERNAL_ERROR" else None,
    )
    return AskResponse(
        answer=text,
        code=code,
        request_id=request_id or None,
        http_status=http_status,
        trace=trace or [],
    )


def _value_text(value: Any) -> str:
    """Show a value as text. 20.0 becomes 20, so the text is the same as a person would write it."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _single_value_answer(question: str, column: str, value: Any) -> str:
    """Return a sentence for a result of one value. Fall back to "Column name: value"."""
    shown = _value_text(value)
    fallback = f"{column.replace('_', ' ').capitalize()}: {shown}"
    if not settings.response_llm_sees_values:
        return fallback
    try:
        system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
        user_message = (
            f"Situation: answer\n\nQuestion of the user:\n{question}\n\nResult:\n{column} = {shown}"
        )
        reply = call_llm(system_prompt, user_message, agent="response_agent").strip()
    except Exception:
        logger.warning("response_agent: the LLM reply failed, using the fixed text", exc_info=True)
        return fallback
    # The LLM must not change the value. A reply without the exact value is not safe to show.
    if reply and shown.lower() in reply.replace(",", "").lower():
        return reply
    logger.warning(
        "response_agent: the reply does not hold the value %r, using the fixed text", shown
    )
    return fallback


def _rows_text(count: int, truncated: bool) -> str:
    """A fixed text for a result with 2 or more values. The LLM does not see these rows."""
    if truncated:
        return f"Here are the first {count} rows. There are more rows than the limit."
    return "Here is the result (1 row)." if count == 1 else f"Here are the results ({count} rows)."


def for_rows(
    result: dict[str, Any],
    sql: str,
    question: str = "",
    request_id: str = "",
    trace: list[TraceEntry] | None = None,
) -> AskResponse:
    """Build the response for a query result. The answer text is always there.

    No rows, or one NULL value (for example SUM of nothing): the "no data" text, and no data.
    One row with one column: a sentence, and the value in data.
    More: a fixed text, and the rows in data.
    """
    columns, rows = result["columns"], result["rows"]
    common = {"request_id": request_id or None, "sql": sql, "trace": trace or []}
    if not rows or (len(rows) == 1 and len(columns) == 1 and rows[0][0] is None):
        return AskResponse(answer=NO_ROWS_TEXT, **common)
    truncated = bool(result.get("truncated"))
    data = ResultData(columns=columns, rows=rows, truncated=truncated)
    if len(rows) == 1 and len(columns) == 1:
        text = _single_value_answer(question, columns[0], rows[0][0])
    else:
        text = _rows_text(len(rows), truncated)
    return AskResponse(answer=text, data=data, **common)


def for_message(
    kind: str, question: str, request_id: str = "", trace: list[TraceEntry] | None = None
) -> AskResponse:
    """Build a short friendly text with the LLM. kind is "chitchat" or "no_matching_data".

    The LLM gets the kind and the question of the user, and nothing else.
    On any failure we use the fixed text, because this step must always give an answer.
    """
    text = ""
    try:
        system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
        user_message = f"Situation: {kind}\n\nMessage of the user:\n{question}"
        text = call_llm(system_prompt, user_message, agent="response_agent").strip()
    except Exception:
        # Not only LlmError: a missing prompt file must not stop a greeting either.
        logger.warning("response_agent: the LLM reply failed, using the fixed text", exc_info=True)
    return AskResponse(
        answer=text or FALLBACK_TEXT[kind],
        request_id=request_id or None,
        trace=trace or [],
    )


def for_invalid_request(request_id: str = "") -> AskResponse:
    """Build the response for a request that failed validation (empty or too long question)."""
    http_status, text = ERRORS["INVALID_REQUEST"]
    return AskResponse(
        answer=text,
        code="INVALID_REQUEST",
        request_id=request_id or None,
        http_status=http_status,
    )
