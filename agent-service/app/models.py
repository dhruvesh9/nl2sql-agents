"""API models and the PipelineState for agent-service.

Pipeline step: infrastructure. /ask uses the API models. The pipeline uses PipelineState.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.config import settings


class AskRequest(BaseModel):
    # An empty or huge question costs LLM tokens and cannot be answered, so we stop it early.
    question: str = Field(min_length=1, max_length=settings.max_question_chars)


class TraceEntry(BaseModel):
    step: str
    name: str
    attempt: int = 1
    elapsed_ms: int
    summary: str


class ResultData(BaseModel):
    """The rows of a query result. The field names are always the same, so a client can read them.

    columns: the column names, in order. rows: one list of values per row, in the same order.
    truncated: True when the rows were cut at the row limit.
    """

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


class AskResponse(BaseModel):
    """The one response that the client gets. The client only renders it.

    answer: a text. ALWAYS there: the sentence for the user, a "no data" text, or an error text.
    data: {columns, rows, truncated}. Only there when the query returned rows.
    code: a short stable value for the client. Only there when something went wrong.
    The endpoints leave out the fields that are None.
    """

    answer: str
    data: ResultData | None = None
    code: str | None = None  # only for an error
    request_id: str | None = None  # the client can quote it, and we find the request in the logs
    # Internal fields. exclude=True keeps them out of the JSON that the client gets.
    # The app sends them to the logs and to the Langfuse trace instead.
    http_status: int = Field(default=200, exclude=True)
    sql: str | None = Field(default=None, exclude=True)
    trace: list[TraceEntry] = Field(default_factory=list, exclude=True)


class PipelineState(BaseModel):
    """Data that moves between the steps of one /ask request. The pipeline steps fill it."""

    question: str
    requirements: dict[str, Any] = Field(default_factory=dict)  # step 1
    selected_tables: list[str] = Field(default_factory=list)  # step 2
    schema_text: str = ""  # step 3
    feedback_hints: list[str] = Field(default_factory=list)  # step 4
    needs_runbook: bool = False  # step R
    relevant_runbooks: list[str] = Field(default_factory=list)  # step R
    sql: str | None = None  # step 5
    sql_feedback: str | None = None  # step 6
    trace: list[TraceEntry] = Field(default_factory=list)
