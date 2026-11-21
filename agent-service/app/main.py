"""agent-service FastAPI app: /health, /ask, and /ask-quick.

Pipeline step: infrastructure. Each request opens one Langfuse trace.
/ask is the full pipeline with the feedback loops. /ask-quick is the same flow without them.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import knowledge, pipeline, quick_pipeline
from app.agents import response_agent
from app.config import settings
from app.models import AskRequest, AskResponse
from app.tracing import init_tracing, observe, shutdown_tracing

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_tracing()
    knowledge.preload()  # warm the cache. A failure only logs a warning.
    yield
    shutdown_tracing()


app = FastAPI(title="agent-service", lifespan=lifespan)


def new_request_id() -> str:
    """A short id for one request. The client gets it back, and the logs show it."""
    return uuid.uuid4().hex[:12]


def _error_json(response: AskResponse) -> JSONResponse:
    return JSONResponse(
        status_code=response.http_status, content=response.model_dump(exclude_none=True)
    )


# Every error leaves the service in the same shape: {"type": "error", "data": ..., "code": ...}.
# The client never gets FastAPI's default {"detail": ...} and never gets a stack trace.
@app.exception_handler(RequestValidationError)
def handle_invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_json(response_agent.for_invalid_request(new_request_id()))


@app.exception_handler(NotImplementedError)
@app.exception_handler(Exception)
def handle_any_error(request: Request, exc: Exception) -> JSONResponse:
    # A stub raises NotImplementedError. Any other error that no pipeline caught ends up here too.
    return _error_json(response_agent.for_error(exc, new_request_id()))


def _trace_output(response: AskResponse) -> dict[str, Any]:
    """The debug data for Langfuse: the outcome AND the steps. The client gets no steps.

    Only the number of rows is sent, not the rows: they can hold personal data.
    """
    steps = [entry.model_dump() for entry in response.trace]
    for step in steps:
        logger.info(
            "step %(step)s %(name)s attempt=%(attempt)d %(elapsed_ms)d ms: %(summary)s", step
        )
    return {
        "code": response.code,
        "rows": len(response.data.rows) if response.data else 0,
        "sql": response.sql,
        "request_id": response.request_id,
        "steps": steps,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, response_model_exclude_none=True)
def ask(request: AskRequest) -> AskResponse:
    """The full pipeline with Loop A and Loop B. See app/pipeline.py. Not implemented yet (501)."""
    # One trace per request. LLM calls inside the pipeline become children of this trace.
    with observe("ask", input={"question": request.question}) as trace:
        response = pipeline.run_pipeline(request.question)
        trace.update(output=_trace_output(response))
    return response


@app.post("/ask-quick", response_model=AskResponse, response_model_exclude_none=True)
def ask_quick(request: AskRequest, http_response: Response) -> AskResponse:
    """Steps 1, 2, 3, 5, 7, 8 with no feedback loops. See app/quick_pipeline.py.

    run_quick never raises: a failure becomes a response of type "error".
    """
    request_id = new_request_id()
    with observe("ask-quick", input={"question": request.question}) as trace:
        response = quick_pipeline.run_quick(request.question, request_id)
        trace.update(output=_trace_output(response))
    http_response.status_code = response.http_status
    return response
