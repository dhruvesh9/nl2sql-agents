"""db-service FastAPI app: /health, /catalog, /schema, /plan, /query.

This service is the only component that connects to the database.
Pipeline step: infrastructure (serves steps 3, 6, and 7 of agent-service).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import executor, observability, planner, schema_reader
from app.config import settings
from app.database import check_connection
from app.models import (
    CatalogResponse,
    PlanRequest,
    PlanResponse,
    QueryRequest,
    QueryResponse,
    SchemaRequest,
    SchemaResponse,
)
from app.sql_guard import SqlRejectedError

logger = logging.getLogger(__name__)
observability.setup_logging("db-service", settings.log_level, settings.log_format)

# No authentication for now. Later: JWT from Keycloak (user auth and service accounts).
app = FastAPI(title="db-service")
observability.install(app)  # request ID, JSON logs, one log line for each request


@app.exception_handler(NotImplementedError)
def handle_not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
    # A stub raises this error. The message names the task file to read.
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.exception_handler(SqlRejectedError)
def handle_sql_rejected(request: Request, exc: SqlRejectedError) -> JSONResponse:
    # A rejected SQL is normal here (the agent sent a bad query). The reason helps to find the cause.
    logger.warning("sql rejected", extra={"reason": str(exc)})
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
def health() -> JSONResponse:
    """Return 200 when the database answers, 503 when it does not. No API key needed."""
    database_ok = check_connection()
    status_code = 200 if database_ok else 503
    body = {"status": "ok" if database_ok else "error", "database": database_ok}
    return JSONResponse(status_code=status_code, content=body)


@app.get("/catalog", response_model=CatalogResponse)
def catalog() -> CatalogResponse:
    """Return every table with its comments and foreign keys. knowledge-service calls it."""
    return schema_reader.get_catalog()


@app.post("/schema", response_model=SchemaResponse)
def schema(request: SchemaRequest) -> SchemaResponse:
    return schema_reader.get_schema(request.tables, request.fk_depth)


@app.post("/plan", response_model=PlanResponse)
def plan(request: PlanRequest) -> PlanResponse:
    return planner.get_plan(request.sql)


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    return executor.run_query(request.sql, request.max_rows)
