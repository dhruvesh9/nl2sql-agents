"""Tests for the client contract: every answer and every error has the same shape."""

import pytest
from fastapi.testclient import TestClient

from app import quick_pipeline
from app.main import app
from app.models import AskResponse, ResultData

client = TestClient(app, raise_server_exceptions=False)


def test_a_stub_endpoint_answers_in_the_error_shape() -> None:
    response = client.post("/ask", json={"question": "How many customers?"})
    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "NOT_IMPLEMENTED"
    assert body["answer"]
    assert body["request_id"]
    assert "detail" not in body


@pytest.mark.parametrize("question", ["", "x" * 5000])
def test_a_bad_question_is_422_in_the_error_shape(question: str) -> None:
    response = client.post("/ask-quick", json={"question": question})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_a_missing_question_field_is_422_in_the_error_shape() -> None:
    response = client.post("/ask-quick", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_an_unexpected_bug_gives_a_generic_500_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bug(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(quick_pipeline, "run_quick", bug)
    response = client.post("/ask-quick", json={"question": "q"})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text


def test_the_http_status_follows_the_response_and_internal_fields_stay_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = AskResponse(answer="busy", code="LLM_BUSY", http_status=503, sql="SELECT 1")
    monkeypatch.setattr(quick_pipeline, "run_quick", lambda question, request_id="": answer)
    response = client.post("/ask-quick", json={"question": "q"})
    assert response.status_code == 503
    assert response.json() == {"answer": "busy", "code": "LLM_BUSY"}


def test_an_answer_with_rows_leaves_out_the_empty_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    data = ResultData(columns=["a"], rows=[[1]])
    answer = AskResponse(answer="Here is the result (1 row).", data=data)
    monkeypatch.setattr(quick_pipeline, "run_quick", lambda question, request_id="": answer)
    response = client.post("/ask-quick", json={"question": "q"})
    assert response.status_code == 200
    assert response.json() == {
        "answer": "Here is the result (1 row).",
        "data": {"columns": ["a"], "rows": [[1]], "truncated": False},
    }


def test_an_unknown_path_has_the_error_shape_and_a_request_id() -> None:
    response = client.get("/nothing-here")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "detail" not in body


def test_a_wrong_method_has_the_error_shape() -> None:
    response = client.get("/ask-quick")
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_a_body_that_is_not_json_is_422_in_the_error_shape() -> None:
    response = client.post(
        "/ask-quick", content=b"this is not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
