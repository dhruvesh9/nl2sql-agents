"""knowledge-service FastAPI app: /health, /index, /graph, /generate, /runbooks/{name}.

This service owns the knowledge base (business rules and table descriptions).
Pipeline step: infrastructure (serves steps 1, 2, and 5 of agent-service).
"""

from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import graph_builder, observability, store
from app.config import settings
from app.models import ContentResponse

observability.setup_logging("knowledge-service", settings.log_level, settings.log_format)

# No authentication for now. Later: JWT from Keycloak (user auth and service accounts).
app = FastAPI(title="knowledge-service")
observability.install(app)  # request ID, JSON logs, one log line for each request


@app.exception_handler(FileNotFoundError)
def handle_not_found(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
def handle_bad_name(request: Request, exc: ValueError) -> JSONResponse:
    # store.read_runbook raises ValueError for a name that holds unsafe characters.
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPError)
def handle_db_service_error(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    # POST /generate needs db-service. When db-service fails, the answer is "bad gateway".
    # When it is too slow, the answer is "gateway timeout".
    status = 504 if isinstance(exc, httpx.TimeoutException) else 502
    return JSONResponse(status_code=status, content={"detail": f"db-service failed: {exc}"})


@app.exception_handler(Exception)
def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Any other error (for example a damaged graph.json): a JSON body, like every other error.

    uvicorn logs the stack trace. The client gets no details.
    """
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": observability.current_request_id(),
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Return 200 when the service runs. No API key needed."""
    return {"status": "ok"}


@app.get("/index", response_model=ContentResponse)
def get_index() -> ContentResponse:
    return ContentResponse(content=store.read_index())


@app.get("/graph")
def get_graph() -> dict[str, Any]:
    """Return graph.json as node-link JSON. Not Markdown, so not {"content": ...}."""
    return store.read_graph()


@app.post("/generate")
def generate() -> dict[str, Any]:
    """Build graph.json again from the live database (through db-service). Return a summary."""
    return graph_builder.generate()


@app.get("/runbooks/{name}", response_model=ContentResponse)
def get_runbook(name: str) -> ContentResponse:
    return ContentResponse(content=store.read_runbook(name))
