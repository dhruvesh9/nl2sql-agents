"""Tests for the knowledge-service API: access control, the content, and the safety of the paths."""

import pytest
from fastapi.testclient import TestClient

from app import store

DOCUMENT_PATHS = ["/index", "/tables", "/relationships", "/runbooks/invoice_status"]


def test_health_needs_no_api_key(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", DOCUMENT_PATHS)
def test_a_document_needs_the_right_api_key(
    client: TestClient, kb, headers: dict[str, str], path: str
) -> None:
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get(path, headers=headers).status_code == 200


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("/index", "INDEX TEXT"),
        ("/tables", "- customers: buyers\n"),
        ("/relationships", "accounts -> customers"),  # the service removes the end of the file
        ("/runbooks/invoice_status", "INVOICE RULES"),
    ],
)
def test_a_document_returns_the_text_of_its_file(
    client: TestClient, kb, headers: dict[str, str], path: str, text: str
) -> None:
    assert client.get(path, headers=headers).json() == {"content": text}


@pytest.mark.parametrize("content", ["", "   \n\n"])
def test_an_empty_relationships_file_returns_an_empty_text(
    client: TestClient, kb, headers: dict[str, str], content: str
) -> None:
    (kb / "table_relationship.md").write_text(content, encoding="utf-8")
    assert client.get("/relationships", headers=headers).json() == {"content": ""}


def test_a_missing_relationships_file_is_not_an_error(
    client: TestClient, kb, headers: dict[str, str]
) -> None:
    # The file is optional. The agent must work without it.
    (kb / "table_relationship.md").unlink()
    assert client.get("/relationships", headers=headers).json() == {"content": ""}


@pytest.mark.parametrize("path", ["/index", "/tables"])
def test_a_missing_required_file_returns_404(
    client: TestClient, kb, headers: dict[str, str], path: str
) -> None:
    (kb / "index.md").unlink()
    (kb / "tables.md").unlink()
    assert client.get(path, headers=headers).status_code == 404


def test_an_unknown_runbook_returns_404_without_the_server_path(
    client: TestClient, kb, headers: dict[str, str]
) -> None:
    response = client.get("/runbooks/no_such_runbook", headers=headers)
    assert response.status_code == 404
    assert "no_such_runbook" in response.json()["detail"]
    assert str(kb) not in response.json()["detail"]  # never show a path of the server


@pytest.mark.parametrize("name", ["bad.name", "a-b", "x%20y", "invoice_status.md"])
def test_a_runbook_name_with_other_characters_returns_400(
    client: TestClient, kb, headers: dict[str, str], name: str
) -> None:
    assert client.get(f"/runbooks/{name}", headers=headers).status_code == 400


def test_a_runbook_name_cannot_leave_the_runbooks_folder(
    client: TestClient, kb, headers: dict[str, str]
) -> None:
    response = client.get("/runbooks/..%2Fsecret", headers=headers)
    assert response.status_code in (400, 404)
    assert "TOP-SECRET" not in response.text


def test_the_store_only_reads_inside_the_runbooks_folder(kb) -> None:
    with pytest.raises(ValueError, match="Invalid runbook name"):
        store.read_runbook("../secret")
    with pytest.raises(FileNotFoundError):
        store.read_runbook("secret")  # secret.md exists, but not in runbooks/
