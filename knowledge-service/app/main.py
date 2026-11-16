"""knowledge-service FastAPI app: /health, /index, /tables, /relationships, /runbooks/{name}.

This service owns the knowledge base (business rules and table descriptions).
Pipeline step: infrastructure (serves steps 1, 2, and 5 of agent-service).
"""

import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app import store
from app.config import settings
from app.models import ContentResponse

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="knowledge-service")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject the request when the X-API-Key header is missing or wrong."""
    expected = settings.service_api_key.encode()
    # compare_digest takes the same time for any input. This stops timing attacks.
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.exception_handler(FileNotFoundError)
def handle_not_found(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
def handle_bad_name(request: Request, exc: ValueError) -> JSONResponse:
    # store.read_runbook raises ValueError for a name that holds unsafe characters.
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    """Return 200 when the service runs. No API key needed."""
    return {"status": "ok"}


@app.get("/index", response_model=ContentResponse, dependencies=[Depends(require_api_key)])
def get_index() -> ContentResponse:
    return ContentResponse(content=store.read_index())


@app.get("/tables", response_model=ContentResponse, dependencies=[Depends(require_api_key)])
def get_tables() -> ContentResponse:
    return ContentResponse(content=store.read_tables())


@app.get("/relationships", response_model=ContentResponse, dependencies=[Depends(require_api_key)])
def get_relationships() -> ContentResponse:
    return ContentResponse(content=store.read_relationships())


@app.get(
    "/runbooks/{name}", response_model=ContentResponse, dependencies=[Depends(require_api_key)]
)
def get_runbook(name: str) -> ContentResponse:
    return ContentResponse(content=store.read_runbook(name))
