"""Smoke tests for db-service."""

import pytest
from fastapi.testclient import TestClient

from app.database import check_connection
from app.main import app

client = TestClient(app)


def test_health_answers_and_reports_database_state() -> None:
    # The app must start and answer even when the database is down.
    response = client.get("/health")
    assert response.status_code in (200, 503)
    assert "database" in response.json()


@pytest.mark.skipif(not check_connection(), reason="PostgreSQL is not running (run: make db-up)")
def test_health_ok_when_database_is_up() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}
