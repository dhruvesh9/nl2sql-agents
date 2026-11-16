"""HTTP client for db-service. Each function sends one request and returns the parsed JSON.

Pipeline step: 3 (get_schema), 6 (get_plan), 7 (run_query).
"""

from typing import Any

import httpx

from app.config import settings


class DbServiceError(Exception):
    """db-service answered with an error. status_code and detail tell what went wrong.

    Status 400 means db-service rejected the SQL. The detail is the reason.
    Give the detail to the SQL generator as feedback.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"db-service error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Send one POST request to db-service with the API key and a timeout."""
    response = httpx.post(
        f"{settings.db_service_url}{path}",
        json=body,
        headers={"X-API-Key": settings.db_service_api_key},
        timeout=settings.db_service_timeout_seconds,
    )
    if response.status_code >= 400:
        # FastAPI sends the reason as {"detail": "..."}. Keep it, because the agent needs it.
        try:
            detail = str(response.json()["detail"])
        except (ValueError, KeyError, TypeError):
            detail = response.text
        raise DbServiceError(response.status_code, detail)
    return response.json()


def get_schema(tables: list[str], fk_depth: int) -> dict[str, Any]:
    """POST /schema. Return the tables, discovered_tables, and not_found."""
    return _post("/schema", {"tables": tables, "fk_depth": fk_depth})


def get_plan(sql: str) -> dict[str, Any]:
    """POST /plan. Return valid, error, estimated_cost, and estimated_rows."""
    return _post("/plan", {"sql": sql})


def run_query(sql: str, max_rows: int | None = None) -> dict[str, Any]:
    """POST /query. Return columns, rows, row_count, truncated, and elapsed_ms."""
    return _post("/query", {"sql": sql, "max_rows": max_rows})
