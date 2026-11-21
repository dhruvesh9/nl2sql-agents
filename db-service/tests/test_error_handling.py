"""Tests for the edge errors: timeout, lost connection, wrong SQL, and a crash.

These tests need no database: they build the database errors by hand.
"""

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import errors as pg
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app import executor, schema_reader
from app.database import DatabaseUnavailableError, QueryTimeoutError, classify_error
from app.main import app
from app.sql_guard import SqlRejectedError

client = TestClient(app, raise_server_exceptions=False)


def wrapped(orig: Exception, kind: type[DBAPIError] = OperationalError) -> DBAPIError:
    return kind("SELECT 1", {}, orig)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            wrapped(pg.QueryCanceled("canceling statement due to statement timeout")),
            QueryTimeoutError,
        ),
        (wrapped(psycopg.OperationalError("connection failed")), DatabaseUnavailableError),
        (wrapped(pg.AdminShutdown("terminating connection")), DatabaseUnavailableError),
        (wrapped(pg.TooManyConnections("too many clients")), DatabaseUnavailableError),
        (
            wrapped(pg.UndefinedColumn("column nme does not exist"), ProgrammingError),
            SqlRejectedError,
        ),
        (wrapped(pg.SyntaxError("syntax error at or near"), ProgrammingError), SqlRejectedError),
    ],
)
def test_each_database_error_gets_the_right_kind(error: DBAPIError, expected: type) -> None:
    assert isinstance(classify_error(error), expected)


def test_a_wrong_sql_keeps_the_database_message_for_the_agent() -> None:
    error = wrapped(
        pg.UndefinedColumn("column nme does not exist\nLINE 1: SELECT nme"), ProgrammingError
    )
    assert str(classify_error(error)) == "column nme does not exist"


def fail_with(monkeypatch: pytest.MonkeyPatch, module: object, name: str, error: Exception) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(module, name, broken)


def test_a_timeout_is_504_with_a_clear_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_with(monkeypatch, executor, "run_query", QueryTimeoutError("The query took too long."))
    response = client.post("/query", json={"sql": "SELECT 1"})
    assert response.status_code == 504
    assert response.json() == {"detail": "The query took too long."}


def test_a_lost_database_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_with(
        monkeypatch,
        executor,
        "run_query",
        DatabaseUnavailableError("The database is not available."),
    )
    assert client.post("/query", json={"sql": "SELECT 1"}).status_code == 503


def test_a_database_error_outside_query_is_classified_too(monkeypatch: pytest.MonkeyPatch) -> None:
    # /schema and /catalog do not use classify_error themselves. The app handler does it for them.
    down = wrapped(psycopg.OperationalError("connection failed"))
    fail_with(monkeypatch, schema_reader, "get_catalog", down)
    assert client.get("/catalog").status_code == 503


def test_an_exhausted_connection_pool_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    fail_with(
        monkeypatch, schema_reader, "get_catalog", PoolTimeoutError("QueuePool limit reached")
    )
    response = client.get("/catalog")
    assert response.status_code == 503
    assert response.json() == {"detail": "The database is busy."}


def test_a_bug_gives_json_with_the_request_id_and_no_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fail_with(monkeypatch, schema_reader, "get_catalog", RuntimeError("secret internal detail"))
    response = client.get("/catalog", headers={"X-Request-ID": "request-id-12345"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "request-id-12345"}
    assert "secret" not in response.text
