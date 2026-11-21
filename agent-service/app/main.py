"""agent-service FastAPI app: /health, /ask, and /ask-quick.

Pipeline step: infrastructure. Each request opens one Langfuse trace.
/ask is the full pipeline with the feedback loops. /ask-quick is the same flow without them.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import knowledge, observability, pipeline, quick_pipeline, tracing, versioning
from app.agents import response_agent
from app.config import settings
from app.models import AskRequest, AskResponse
from app.tracing import init_tracing, shutdown_tracing

observability.setup_logging("agent-service", settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_tracing()
    knowledge.preload()  # warm the cache. A failure only logs a warning.
    yield
    shutdown_tracing()


app = FastAPI(title="agent-service", lifespan=lifespan)
observability.install(app)  # request ID, JSON logs, one log line for each request


def _error_json(response: AskResponse) -> JSONResponse:
    # An error that the middleware did not see (a crash) has no header yet, so we add it here.
    return JSONResponse(
        status_code=response.http_status,
        content=response.model_dump(exclude_none=True),
        headers={observability.REQUEST_ID_HEADER: response.request_id or ""},
    )


# Every error leaves the service in the same shape: {"type": "error", "data": ..., "code": ...}.
# The client never gets FastAPI's default {"detail": ...} and never gets a stack trace.
@app.exception_handler(RequestValidationError)
def handle_invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_json(response_agent.for_invalid_request(observability.current_request_id()))


@app.exception_handler(StarletteHTTPException)
def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # An unknown path (404) or a wrong method (405). Without this the client gets FastAPI's own shape.
    return _error_json(
        response_agent.for_http_error(exc.status_code, observability.current_request_id())
    )


@app.exception_handler(NotImplementedError)
@app.exception_handler(Exception)
def handle_any_error(request: Request, exc: Exception) -> JSONResponse:
    # A stub raises NotImplementedError. Any other error that no pipeline caught ends up here too.
    return _error_json(response_agent.for_error(exc, observability.current_request_id()))


def _trace_output(response: AskResponse) -> dict[str, Any]:
    """The debug data for Langfuse: the outcome AND the steps. The client gets no steps.

    Only the number of rows is sent, not the rows: they can hold personal data.
    """
    return {
        "answer": response.answer,
        "code": response.code,
        "rows": len(response.data.rows) if response.data else 0,
        "sql": response.sql,
        "request_id": response.request_id,
        "steps": [entry.model_dump() for entry in response.trace],
    }


def _record_outcome(trace: Any, response: AskResponse) -> None:
    """Put the result on the Langfuse trace: the output and two scores to filter and count by.

    outcome: "data" (rows), "text" (an answer without rows), or the error code.
    """
    trace.update(output=_trace_output(response))
    outcome = response.code or ("data" if response.data else "text")
    tracing.score("outcome", outcome, "CATEGORICAL")
    tracing.score("rows_returned", len(response.data.rows) if response.data else 0, "NUMERIC")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, response_model_exclude_none=True)
def ask(request: AskRequest) -> AskResponse:
    """The full pipeline with Loop A and Loop B. See app/pipeline.py. Not implemented yet (501)."""
    request_id = observability.current_request_id()
    # One trace per request. LLM calls inside the pipeline become children of this trace.
    with tracing.request_trace(
        "ask", request_id, {"question": request.question}, versioning.trace_metadata()
    ) as trace:
        response = pipeline.run_pipeline(request.question)
        _record_outcome(trace, response)
    return response


@app.post("/ask-quick", response_model=AskResponse, response_model_exclude_none=True)
def ask_quick(request: AskRequest, http_response: Response) -> AskResponse:
    """Steps 1, 2, 3, 5, 7, 8 with no feedback loops. See app/quick_pipeline.py.

    run_quick never raises: a failure becomes a response with a code.
    """
    request_id = observability.current_request_id()
    with tracing.request_trace(
        "ask-quick", request_id, {"question": request.question}, versioning.trace_metadata()
    ) as trace:
        response = quick_pipeline.run_quick(request.question, request_id)
        _record_outcome(trace, response)
    http_response.status_code = response.http_status
    return response
