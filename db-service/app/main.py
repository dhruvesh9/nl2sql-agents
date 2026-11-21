"""db-service FastAPI app: /health, /catalog, /schema, /plan, /query.

This service is the only component that connects to the database.
Pipeline step: infrastructure (serves steps 3, 6, and 7 of agent-service).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import executor, planner, schema_reader
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

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# No authentication for now. Later: JWT from Keycloak (user auth and service accounts).
app = FastAPI(title="db-service")


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
