"""Smoke tests for agent-service."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_returns_501_until_the_pipeline_is_built() -> None:
    response = client.post("/ask", json={"question": "How many customers?"})
    assert response.status_code == 501
    assert "not implemented yet" in response.json()["detail"]
