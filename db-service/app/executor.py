"""Runs a checked SELECT query in a read-only transaction.

Pipeline step: 7 (SQL Execution, action 7A), db-service side. Used by POST /query.
"""

import logging
import math
import time
from datetime import date
from datetime import time as time_of_day
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.database import engine, error_message, get_dialect, sql_to_text, start_readonly
from app.models import QueryResponse
from app.sql_guard import SqlRejectedError, check_sql

logger = logging.getLogger(__name__)


def to_json_safe(value: Any) -> Any:
    """Convert a database value to a value that JSON can hold.

    Example:
        to_json_safe(Decimal("1.50")) -> 1.5
        to_json_safe(date(2025, 1, 31)) -> "2025-01-31"
    """
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # JSON has no NaN or Infinity
    if isinstance(value, (date, time_of_day)):  # datetime is a kind of date
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, UUID):
        return str(value)
    return value


def choose_row_limit(max_rows: int | None) -> int:
    """Use the default when max_rows is missing or below 1. Never go above the maximum."""
    if max_rows is None or max_rows < 1:
        return settings.default_max_rows
    return min(max_rows, settings.max_rows_limit)


def run_query(sql: str, max_rows: int | None) -> QueryResponse:
    """Run the SQL and return the rows.

    We ask for max_rows + 1 rows. If we get the extra row, the result was cut: truncated is True.
    """
    check_sql(sql, get_dialect())  # a rejected SQL raises SqlRejectedError (HTTP 400)
    limit = choose_row_limit(max_rows)

    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            start_readonly(conn)
            # stream_results asks the database for rows in small parts.
            # Without it, the driver loads ALL rows into memory first.
            conn = conn.execution_options(stream_results=True)
            result = conn.execute(sql_to_text(sql))
            columns = list(result.keys())
            fetched = result.fetchmany(limit + 1)
    except DBAPIError as error:
        # Wrong SQL and timeouts end here. The agent needs the message to fix its SQL.
        raise SqlRejectedError(error_message(error)) from error
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    truncated = len(fetched) > limit
    rows = [[to_json_safe(value) for value in row] for row in fetched[:limit]]
    # The request log already has the HTTP side. This line has the database side.
    logger.info(
        "query executed",
        extra={
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": elapsed_ms,
            "sql": sql,
        },
    )

    return QueryResponse(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=elapsed_ms,
    )
