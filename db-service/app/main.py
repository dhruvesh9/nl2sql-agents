"""db-service FastAPI app: /health, /schema, /plan, /query.

This service is the only component that connects to the database.
Pipeline step: infrastructure (serves steps 3, 6, and 7 of agent-service).
"""

import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app import executor, planner, schema_reader
from app.config import settings
from app.database import check_connection
from app.models import (
    PlanRequest,
    PlanResponse,
    QueryRequest,
    QueryResponse,
    SchemaRequest,
    SchemaResponse,
)
from app.sql_guard import SqlRejectedError

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="db-service")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Reject the request when the X-API-Key header is missing or wrong."""
    expected = settings.service_api_key.encode()
    # compare_digest takes the same time for any input. This stops timing attacks.
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.exception_handler(NotImplementedError)
def handle_not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
    # A stub raises this error. The message names the task file to read.
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.exception_handler(SqlRejectedError)
def handle_sql_rejected(request: Request, exc: SqlRejectedError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
def health() -> JSONResponse:
    """Return 200 when the database answers, 503 when it does not. No API key needed."""
    database_ok = check_connection()
    status_code = 200 if database_ok else 503
    body = {"status": "ok" if database_ok else "error", "database": database_ok}
    return JSONResponse(status_code=status_code, content=body)


@app.post("/schema", response_model=SchemaResponse, dependencies=[Depends(require_api_key)])
def schema(request: SchemaRequest) -> SchemaResponse:
    return schema_reader.get_schema(request.tables, request.fk_depth)


@app.post("/plan", response_model=PlanResponse, dependencies=[Depends(require_api_key)])
def plan(request: PlanRequest) -> PlanResponse:
    return planner.get_plan(request.sql)


@app.post("/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)])
def query(request: QueryRequest) -> QueryResponse:
    return executor.run_query(request.sql, request.max_rows)
