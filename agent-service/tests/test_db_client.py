"""Tests for db_client. They use a fake HTTP answer, so db-service does not need to run."""

import httpx
import pytest

from app import db_client, observability


def fake_post(status_code: int, json_body: dict):
    def post(url: str, **kwargs) -> httpx.Response:
        assert kwargs["timeout"] > 0  # every call must have a timeout
        return httpx.Response(status_code, json=json_body, request=httpx.Request("POST", url))

    return post


def test_run_query_returns_parsed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"columns": ["n"], "rows": [[1]], "row_count": 1, "truncated": False, "elapsed_ms": 2}
    monkeypatch.setattr(httpx, "post", fake_post(200, body))
    assert db_client.run_query("SELECT 1") == body


def test_rejected_sql_raises_error_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(400, {"detail": "Only SELECT is allowed"}))
    with pytest.raises(db_client.DbServiceError) as error:
        db_client.get_plan("DELETE FROM customers")
    assert error.value.status_code == 400
    assert error.value.detail == "Only SELECT is allowed"


def test_the_request_id_goes_to_db_service_in_the_header(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake(url: str, **kwargs):
        seen.update(kwargs["headers"])
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake)
    observability.request_id_var.set("abc12345def")
    db_client.get_plan("SELECT 1")
    assert seen == {"X-Request-ID": "abc12345def"}
