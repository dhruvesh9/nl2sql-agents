"""Test setup. The tests use a small knowledge base in a temporary folder, never the real files."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def kb(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """A small knowledge base. secret.md sits OUTSIDE the runbooks folder, so it must never leak."""
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "index.md").write_text("INDEX TEXT", encoding="utf-8")
    (tmp_path / "runbooks" / "invoice_status.md").write_text("INVOICE RULES", encoding="utf-8")
    (tmp_path / "secret.md").write_text("TOP-SECRET", encoding="utf-8")
    monkeypatch.setattr(settings, "knowledge_base_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
