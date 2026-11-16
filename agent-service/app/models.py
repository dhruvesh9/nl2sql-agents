"""API models and the PipelineState for agent-service.

Pipeline step: infrastructure. /ask uses the API models. The pipeline uses PipelineState.
"""

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str


class TraceEntry(BaseModel):
    step: str
    name: str
    attempt: int = 1
    elapsed_ms: int
    summary: str


class AskResponse(BaseModel):
    status: str  # "success" or "failed"
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    failure_reason: str | None = None
    trace: list[TraceEntry] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """Answer of POST /analyze: the mini pipeline with step 1 and step 2 only."""

    question: str
    requirements: dict[str, Any] = Field(default_factory=dict)  # output of step 1
    selected_tables: list[str] = Field(default_factory=list)  # output of step 2
    reason: str = ""  # why step 2 chose these tables
    trace: list[TraceEntry] = Field(default_factory=list)


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
