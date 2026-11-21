"""Client for knowledge-service, with a small cache. It gives the agents the knowledge base.

Pipeline step: 1A (index), 2A (table graph), and 5A (runbooks).

The knowledge base belongs to knowledge-service. Its files can change at any time.
We cache each answer for KNOWLEDGE_CACHE_TTL_SECONDS, so we do not call the service for every LLM call.
If a refresh fails, we use the old copy ("stale if error"), so a short outage does not stop the agent.
"""

import logging
import re
import time
from typing import Any

import httpx

from app.config import settings
from app.observability import REQUEST_ID_HEADER, current_request_id

logger = logging.getLogger(__name__)

# path -> (time when we saved the answer, JSON answer). time.monotonic() does not jump when the clock changes.
_cache: dict[str, tuple[float, Any]] = {}


class KnowledgeServiceError(Exception):
    """knowledge-service answered with an error, or we could not reach it."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"knowledge-service error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _fetch(path: str) -> Any:
    """Send one GET request. Return the parsed JSON answer. Raise KnowledgeServiceError on a problem."""
    start = time.perf_counter()
    try:
        response = httpx.get(
            f"{settings.knowledge_service_url}{path}",
            timeout=settings.knowledge_service_timeout_seconds,
            headers={REQUEST_ID_HEADER: current_request_id()},
        )
    except httpx.HTTPError as error:
        raise KnowledgeServiceError(503, f"cannot reach knowledge-service: {error}") from error
    logger.info(
        "knowledge_service call",
        extra={
            "path": path,
            "status": response.status_code,
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        },
    )

    if response.status_code >= 400:
        # FastAPI sends the reason as {"detail": "..."}. Keep it.
        try:
            detail = str(response.json()["detail"])
        except (ValueError, KeyError, TypeError):
            detail = response.text
        raise KnowledgeServiceError(response.status_code, detail)
    return response.json()


def _get(path: str) -> Any:
    """Return the JSON answer for one path. Use the cache while it is fresh."""
    now = time.monotonic()
    cached = _cache.get(path)
    if cached and now - cached[0] < settings.knowledge_cache_ttl_seconds:
        logger.debug("knowledge cache hit", extra={"path": path})
        return cached[1]

    try:
        answer = _fetch(path)
    except KnowledgeServiceError as error:
        # A 4xx answer is a real answer (for example 404: the runbook was deleted). Do not hide it.
        # A 5xx answer or no answer is a service problem. An old copy is better than a failure.
        if cached and error.status_code >= 500:
            logger.warning("%s. Use the old copy of %s", error, path)
            _cache[path] = (now, cached[1])  # try again after the next TTL, not on every call
            return cached[1]
        raise

    _cache[path] = (now, answer)
    return answer


def preload() -> None:
    """Fill the cache at startup. A failure only logs a warning. The agent still starts."""
    for path in ("/index", "/graph"):
        try:
            _get(path)
        except KnowledgeServiceError as error:
            logger.warning(
                "Preload of %s failed: %s. We will try again on the first request.", path, error
            )


def read_index() -> str:
    """Return the text of index.md."""
    return _get("/index")["content"]


def read_graph() -> dict[str, Any]:
    """Return the table graph (graph.json) as node-link JSON: {"nodes": [...], "edges": [...]}.

    knowledge-service builds it from the live database with POST /generate.
    app/table_graph.py turns it into prompt text.
    """
    return _get("/graph")


def read_runbook(name: str) -> str:
    """Return the text of one runbook, for example read_runbook("active_customer").

    The name has no ".md" at the end. It may hold only letters, digits, and underscores.
    We check it here too, so a bad name never leaves this service.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Invalid runbook name: {name!r}")
    return _get(f"/runbooks/{name}")["content"]
