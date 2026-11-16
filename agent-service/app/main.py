"""agent-service FastAPI app: /health and /ask.

Pipeline step: infrastructure. /ask starts the pipeline and opens one Langfuse trace per request.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app import analysis_pipeline, knowledge, pipeline
from app.agents import query_analyzer
from app.config import settings
from app.knowledge import KnowledgeServiceError
from app.models import AnalyzeResponse, AskRequest, AskResponse
from app.tracing import init_tracing, observe, shutdown_tracing

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    # One trace per request. LLM calls inside the pipeline become children of this trace.
    with observe("ask", input={"question": request.question}) as trace:
        response = pipeline.run_pipeline(request.question)
        trace.update(output={"status": response.status, "failure_reason": response.failure_reason})
    return response


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AskRequest) -> AnalyzeResponse:
    """Run only step 1 and step 2. Use it to test the two agents and to run the evals."""
    try:
        with observe("analyze", input={"question": request.question}) as trace:
            response = analysis_pipeline.run_analysis(request.question)
            trace.update(output={"tables": response.selected_tables})
    except ValueError as error:  # the LLM did not return valid JSON, even after one retry
        raise HTTPException(status_code=502, detail=str(error)) from error
    return response


# TEMPORARY. Use it to try agent 1 alone, for example in Postman. Remove it when the full pipeline (POST /ask) works.
@app.post("/debug/query-analyzer")
def debug_query_analyzer(request: AskRequest) -> dict:
    try:
        return query_analyzer.run(request.question, knowledge.read_index())
    except ValueError as error:  # the LLM did not return valid JSON, even after one retry
        raise HTTPException(status_code=502, detail=str(error)) from error
