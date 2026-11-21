"""Tests for request IDs and structured logs. The same file is in all three services."""

import io
import json
import logging
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import observability


@pytest.fixture
def logs() -> Iterator[Callable[[], list[dict]]]:
    """Collect everything that is logged as parsed JSON lines."""
    stream = io.StringIO()
    handler = observability.make_handler("test-service", "json", stream)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    root.removeHandler(handler)
    root.setLevel(old_level)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    observability.install(app)

    @app.get("/ping")
    def ping() -> dict:
        # A sync endpoint runs in a thread. The request ID must still be there.
        logging.getLogger("test").info("inside", extra={"thing": 5})
        return {"ok": True}

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("bug")

    return TestClient(app, raise_server_exceptions=False)


def test_a_new_id_has_32_hex_characters_and_is_set_in_the_response(client: TestClient) -> None:
    request_id = client.get("/ping").headers["X-Request-ID"]
    assert len(request_id) == 32
    int(request_id, 16)  # all hex


def test_a_safe_id_from_the_caller_is_kept_everywhere(
    client: TestClient, logs: Callable[[], list[dict]]
) -> None:
    response = client.get("/ping", headers={"X-Request-ID": "gateway-id-12345"})
    assert response.headers["X-Request-ID"] == "gateway-id-12345"
    lines = [line for line in logs() if line["logger"] in {"test", "request"}]
    assert {line["request_id"] for line in lines} == {"gateway-id-12345"}
    assert [line["msg"] for line in lines] == ["inside", "request"]


@pytest.mark.parametrize("bad", ["short", "has space in it 123", "x" * 200, "semi;colon-12345"])
def test_an_unsafe_id_is_replaced(client: TestClient, bad: str) -> None:
    assert client.get("/ping", headers={"X-Request-ID": bad}).headers["X-Request-ID"] != bad


def test_each_request_gets_one_request_line_with_the_numbers(
    client: TestClient, logs: Callable[[], list[dict]]
) -> None:
    client.get("/ping")
    line = next(entry for entry in logs() if entry["msg"] == "request")
    assert (line["method"], line["path"], line["status"]) == ("GET", "/ping", 200)
    assert line["duration_ms"] >= 0
    assert line["service"] == "test-service"
    assert line["level"] == "INFO"


def test_extra_fields_become_json_fields_and_the_message_stays_the_same(
    client: TestClient, logs: Callable[[], list[dict]]
) -> None:
    client.get("/ping")
    inside = next(entry for entry in logs() if entry["msg"] == "inside")
    assert inside["thing"] == 5


def test_health_checks_are_logged_at_debug_only(
    client: TestClient, logs: Callable[[], list[dict]]
) -> None:
    client.get("/health")
    assert [entry["level"] for entry in logs() if entry["msg"] == "request"] == ["DEBUG"]


def test_a_crash_is_logged_as_an_error_request(
    client: TestClient, logs: Callable[[], list[dict]]
) -> None:
    assert client.get("/boom").status_code == 500
    line = next(entry for entry in logs() if entry["msg"] == "request")
    assert (line["status"], line["level"]) == (500, "ERROR")


def test_an_error_with_a_stack_trace_is_one_json_line() -> None:
    stream = io.StringIO()
    handler = observability.make_handler("s", "json", stream)
    logger = logging.getLogger("trace-test")
    logger.addHandler(handler)
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")
    finally:
        logger.removeHandler(handler)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert "ValueError: boom" in json.loads(lines[0])["exc"]


def test_the_text_format_is_readable_and_has_the_fields() -> None:
    stream = io.StringIO()
    handler = observability.make_handler("s", "text", stream)
    logger = logging.getLogger("text-test")
    logger.addHandler(handler)
    logger.propagate = False
    observability.request_id_var.set("abcdef1234567890")
    logger.warning("slow", extra={"elapsed_ms": 900})
    logger.removeHandler(handler)
    line = stream.getvalue()
    assert "WARNING [abcdef12] text-test: slow elapsed_ms=900" in line


def test_pick_request_id_uses_a_valid_id_and_makes_one_otherwise() -> None:
    assert observability.pick_request_id("abcd-1234.xyz") == "abcd-1234.xyz"
    assert len(observability.pick_request_id(None)) == 32
    assert len(observability.pick_request_id("")) == 32
