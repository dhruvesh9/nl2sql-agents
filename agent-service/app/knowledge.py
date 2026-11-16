"""Client for knowledge-service, with a small cache. It gives the agents the knowledge base text.

Pipeline step: 1A (index), 2A (tables and relationships), and 5A (runbooks).

The knowledge base belongs to knowledge-service. Its files can change at any time.
We cache each answer for KNOWLEDGE_CACHE_TTL_SECONDS, so we do not call the service for every LLM call.
If a refresh fails, we use the old copy ("stale if error"), so a short outage does not stop the agent.
"""

import logging
import re
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# path -> (time when we saved the text, text). time.monotonic() does not jump when the clock changes.
_cache: dict[str, tuple[float, str]] = {}


class KnowledgeServiceError(Exception):
    """knowledge-service answered with an error, or we could not reach it."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"knowledge-service error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _fetch(path: str) -> str:
    """Send one GET request. Return the "content" text. Raise KnowledgeServiceError on a problem."""
    try:
        response = httpx.get(
            f"{settings.knowledge_service_url}{path}",
            headers={"X-API-Key": settings.knowledge_service_api_key},
            timeout=settings.knowledge_service_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise KnowledgeServiceError(503, f"cannot reach knowledge-service: {error}") from error

    if response.status_code >= 400:
        # FastAPI sends the reason as {"detail": "..."}. Keep it.
        try:
            detail = str(response.json()["detail"])
        except (ValueError, KeyError, TypeError):
            detail = response.text
        raise KnowledgeServiceError(response.status_code, detail)
    return response.json()["content"]


def _get(path: str) -> str:
    """Return the text for one path. Use the cache while it is fresh."""
    now = time.monotonic()
    cached = _cache.get(path)
    if cached and now - cached[0] < settings.knowledge_cache_ttl_seconds:
        return cached[1]

    try:
        text = _fetch(path)
    except KnowledgeServiceError as error:
        # A 4xx answer is a real answer (for example 404: the runbook was deleted). Do not hide it.
        # A 5xx answer or no answer is a service problem. An old copy is better than a failure.
        if cached and error.status_code >= 500:
            logger.warning("%s. Use the old copy of %s", error, path)
            _cache[path] = (now, cached[1])  # try again after the next TTL, not on every call
            return cached[1]
        raise

    _cache[path] = (now, text)
    return text


def preload() -> None:
    """Fill the cache at startup. A failure only logs a warning. The agent still starts."""
    for path in ("/index", "/tables", "/relationships"):
        try:
            _get(path)
        except KnowledgeServiceError as error:
            logger.warning(
                "Preload of %s failed: %s. We will try again on the first request.", path, error
            )


def read_index() -> str:
    """Return the text of index.md."""
    return _get("/index")


def read_tables() -> str:
    """Return the text of tables.md (one line per table)."""
    return _get("/tables")


def read_relationships() -> str:
    """Return the text of table_relationship.md. It is "" if the file is empty or missing.

    The file shows how the tables link to each other. The Table Classifier uses it to find
    the tables between two tables, for example customers -> accounts -> subscriptions -> devices.
    """
    return _get("/relationships")


def read_runbook(name: str) -> str:
    """Return the text of one runbook, for example read_runbook("active_customer").

    The name has no ".md" at the end. It may hold only letters, digits, and underscores.
    We check it here too, so a bad name never leaves this service.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Invalid runbook name: {name!r}")
    return _get(f"/runbooks/{name}")
