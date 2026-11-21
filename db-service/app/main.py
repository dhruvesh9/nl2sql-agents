"""db-service FastAPI app: /health, /catalog, /schema, /plan, /query.

This service is the only component that connects to the database.
Pipeline step: infrastructure (serves steps 3, 6, and 7 of agent-service).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app import executor, observability, planner, schema_reader
from app.config import settings
from app.database import (
    DatabaseUnavailableError,
    QueryTimeoutError,
    check_connection,
    classify_error,
)
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


@app.exception_handler(QueryTimeoutError)
def handle_query_timeout(request: Request, exc: QueryTimeoutError) -> JSONResponse:
    # The query was valid but too slow. 504 tells the agent "do not fix the SQL, make it lighter".
    logger.warning("query timeout", extra={"timeout_ms": settings.statement_timeout_ms})
    return JSONResponse(status_code=504, content={"detail": str(exc)})


@app.exception_handler(DatabaseUnavailableError)
def handle_database_unavailable(request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
    logger.error("database unavailable")
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(PoolTimeoutError)
def handle_pool_timeout(request: Request, exc: PoolTimeoutError) -> JSONResponse:
    # All connections of the pool are busy. The caller can try again in a moment.
    logger.error("connection pool is exhausted")
    return JSONResponse(status_code=503, content={"detail": "The database is busy."})


@app.exception_handler(DBAPIError)
def handle_database_error(request: Request, exc: DBAPIError) -> JSONResponse:
    # A database error outside /query and /plan (for example in /schema or /catalog).
    problem = classify_error(exc)
    if isinstance(problem, QueryTimeoutError):
        return handle_query_timeout(request, problem)
    if isinstance(problem, DatabaseUnavailableError):
        return handle_database_unavailable(request, problem)
    return handle_unexpected(request, exc)


@app.exception_handler(Exception)
def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Any other error: a JSON body, like every other error. uvicorn logs the stack trace."""
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": observability.current_request_id(),
        },
    )


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
