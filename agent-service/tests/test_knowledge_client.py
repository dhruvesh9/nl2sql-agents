"""Tests for the knowledge-service client: the cache and the failure rules.

A fake HTTP function replaces httpx.get, so knowledge-service does not need to run.
"""

import httpx
import pytest

from app import knowledge
from app.config import settings


class FakeService:
    """Replaces httpx.get. It counts the calls, and you can switch it to an error."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        self.status = 200
        self.content = "text v1"
        self.down = False
        monkeypatch.setattr(httpx, "get", self.get)

    def get(self, url: str, **kwargs) -> httpx.Response:
        self.calls += 1
        assert kwargs["headers"]["X-API-Key"]  # every call must send the API key
        assert kwargs["timeout"] > 0  # every call must have a timeout
        if self.down:
            raise httpx.ConnectError("service is down")
        body = {"content": self.content} if self.status == 200 else {"detail": "reason text"}
        return httpx.Response(self.status, json=body, request=httpx.Request("GET", url))


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch: pytest.MonkeyPatch):
    knowledge._cache.clear()
    monkeypatch.setattr(settings, "knowledge_cache_ttl_seconds", 300)
    yield
    knowledge._cache.clear()


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> FakeService:
    return FakeService(monkeypatch)


def expire_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """A TTL of 0 means every cached text is already too old."""
    monkeypatch.setattr(settings, "knowledge_cache_ttl_seconds", 0)


def test_second_read_inside_the_ttl_does_not_call_the_service(service: FakeService) -> None:
    assert knowledge.read_index() == "text v1"
    assert knowledge.read_index() == "text v1"
    assert service.calls == 1


def test_each_document_has_its_own_cache_entry(service: FakeService) -> None:
    knowledge.read_index()
    knowledge.read_tables()
    assert service.calls == 2


def test_after_the_ttl_the_new_text_is_loaded(
    service: FakeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    knowledge.read_tables()
    expire_cache(monkeypatch)
    service.content = "text v2"
    assert knowledge.read_tables() == "text v2"


def test_service_down_after_the_ttl_returns_the_old_copy(
    service: FakeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    knowledge.read_tables()
    expire_cache(monkeypatch)
    service.down = True
    assert knowledge.read_tables() == "text v1"


def test_server_error_after_the_ttl_returns_the_old_copy(
    service: FakeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    knowledge.read_tables()
    expire_cache(monkeypatch)
    service.status = 500
    assert knowledge.read_tables() == "text v1"


def test_after_a_failed_refresh_we_do_not_call_the_service_on_every_read(
    service: FakeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If we retried on every read, a down service would slow down every question.
    knowledge.read_tables()
    expire_cache(monkeypatch)
    service.down = True
    knowledge.read_tables()  # the refresh fails, we keep the old copy
    calls_before = service.calls
    monkeypatch.setattr(settings, "knowledge_cache_ttl_seconds", 300)
    knowledge.read_tables()
    assert service.calls == calls_before


def test_service_down_and_no_copy_raises_a_clear_error(service: FakeService) -> None:
    service.down = True
    with pytest.raises(knowledge.KnowledgeServiceError) as error:
        knowledge.read_index()
    assert error.value.status_code == 503


def test_not_found_is_not_hidden_by_an_old_copy(
    service: FakeService, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A deleted runbook must fail. An old copy would hide the change for a long time.
    knowledge.read_runbook("invoice_status")
    expire_cache(monkeypatch)
    service.status = 404
    with pytest.raises(knowledge.KnowledgeServiceError) as error:
        knowledge.read_runbook("invoice_status")
    assert error.value.status_code == 404
    assert error.value.detail == "reason text"


@pytest.mark.parametrize("name", ["../../.env", "a/b", "invoice status", "x.md", ""])
def test_unsafe_runbook_name_never_reaches_the_service(service: FakeService, name: str) -> None:
    with pytest.raises(ValueError, match="Invalid runbook name"):
        knowledge.read_runbook(name)
    assert service.calls == 0


def test_preload_does_not_stop_the_app_when_the_service_is_down(service: FakeService) -> None:
    service.down = True
    knowledge.preload()  # must not raise
    assert knowledge._cache == {}
