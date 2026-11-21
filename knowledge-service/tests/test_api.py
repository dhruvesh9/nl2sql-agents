"""Tests for the knowledge-service API: the content and the safety of the paths."""

import pytest
from fastapi.testclient import TestClient

from app import store

DOCUMENT_PATHS = ["/index", "/runbooks/invoice_status"]


def test_health_answers(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", DOCUMENT_PATHS)
def test_a_document_answers_without_authentication(client: TestClient, kb, path: str) -> None:
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("/index", "INDEX TEXT"),
        ("/runbooks/invoice_status", "INVOICE RULES"),
    ],
)
def test_a_document_returns_the_text_of_its_file(
    client: TestClient, kb, path: str, text: str
) -> None:
    assert client.get(path).json() == {"content": text}


def test_a_missing_index_returns_404(client: TestClient, kb) -> None:
    (kb / "index.md").unlink()
    assert client.get("/index").status_code == 404


def test_an_unknown_runbook_returns_404_without_the_server_path(client: TestClient, kb) -> None:
    response = client.get("/runbooks/no_such_runbook")
    assert response.status_code == 404
    assert "no_such_runbook" in response.json()["detail"]
    assert str(kb) not in response.json()["detail"]  # never show a path of the server


@pytest.mark.parametrize("name", ["bad.name", "a-b", "x%20y", "invoice_status.md"])
def test_a_runbook_name_with_other_characters_returns_400(
    client: TestClient, kb, name: str
) -> None:
    assert client.get(f"/runbooks/{name}").status_code == 400


def test_a_runbook_name_cannot_leave_the_runbooks_folder(client: TestClient, kb) -> None:
    response = client.get("/runbooks/..%2Fsecret")
    assert response.status_code in (400, 404)
    assert "TOP-SECRET" not in response.text


def test_the_store_only_reads_inside_the_runbooks_folder(kb) -> None:
    with pytest.raises(ValueError, match="Invalid runbook name"):
        store.read_runbook("../secret")
    with pytest.raises(FileNotFoundError):
        store.read_runbook("secret")  # secret.md exists, but not in runbooks/
