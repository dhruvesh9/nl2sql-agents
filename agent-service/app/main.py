"""agent-service FastAPI app: /health, /ask, and /ask-quick.

Pipeline step: infrastructure. Each request opens one Langfuse trace.
/ask is the full pipeline with the feedback loops. /ask-quick is the same flow without them.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app import knowledge, pipeline, quick_pipeline
from app.config import settings
from app.db_client import DbServiceError
from app.knowledge import KnowledgeServiceError
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


@app.exception_handler(NotImplementedError)
def handle_not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
    # A stub raises this error. The message names the task file to read.
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.exception_handler(KnowledgeServiceError)
def handle_knowledge_error(request: Request, exc: KnowledgeServiceError) -> JSONResponse:
    # knowledge-service is another service. When it fails, the answer is "bad gateway".
    return JSONResponse(status_code=502, content={"detail": str(exc)})


def _trace_output(response: AskResponse) -> dict[str, Any]:
    """The debug data for Langfuse: the result AND the steps. The client gets no steps."""
    steps = [entry.model_dump() for entry in response.trace]
    for step in steps:
        logger.info(
            "step %(step)s %(name)s attempt=%(attempt)d %(elapsed_ms)d ms: %(summary)s", step
        )
    return {
        "status": response.status,
        "sql": response.sql,
        "failure_reason": response.failure_reason,
        "steps": steps,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """The full pipeline with Loop A and Loop B. See app/pipeline.py. Not implemented yet (501)."""
    # One trace per request. LLM calls inside the pipeline become children of this trace.
    with observe("ask", input={"question": request.question}) as trace:
        response = pipeline.run_pipeline(request.question)
        trace.update(output=_trace_output(response))
    return response


@app.post("/ask-quick", response_model=AskResponse)
def ask_quick(request: AskRequest) -> AskResponse:
    """Steps 1, 2, 3, 5, 7 with no feedback loops (no steps 4 and 6). See app/quick_pipeline.py."""
    try:
        with observe("ask-quick", input={"question": request.question}) as trace:
            response = quick_pipeline.run_quick(request.question)
            trace.update(output=_trace_output(response))
    except ValueError as error:  # the LLM did not return valid JSON, even after one retry
        raise HTTPException(status_code=502, detail=str(error)) from error
    except DbServiceError as error:  # db-service failed on /schema
        raise HTTPException(status_code=502, detail=str(error)) from error
    return response
