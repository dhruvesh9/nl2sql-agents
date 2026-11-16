"""Langfuse tracing helpers. Tracing is optional and off by default.

Pipeline step: infrastructure (observability for all steps).
When LANGFUSE_ENABLED is false, every helper does nothing, so the app works without Langfuse.
Tracing must never break a request: if Langfuse fails, we only log a warning.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from langfuse import Langfuse

from app.config import settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None


def init_tracing() -> None:
    """Create the Langfuse client when tracing is on. Call it once at app start."""
    global _client
    if not settings.langfuse_enabled:
        logger.info("Langfuse tracing is off")
        return
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("LANGFUSE_ENABLED is true, but the Langfuse keys are empty. Tracing is off.")
        return
    _client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    logger.info("Langfuse tracing is on (%s)", settings.langfuse_host)


def shutdown_tracing() -> None:
    """Send the traces that are still waiting. Call it once at app stop."""
    if _client is not None:
        _client.shutdown()


def _noop_update(**kwargs: Any) -> None:
    """Stand-in for observation.update() when tracing is off."""


@contextmanager
def observe(name: str, as_type: str = "span", **kwargs: Any) -> Iterator[Any]:
    """Open a Langfuse observation. The result has an update(**fields) method.

    Use as_type="generation" for an LLM call. Pass model=..., input=..., and so on.
    Calls inside the with block become children of this observation.

    Example:
        with observe("ask", input={"question": q}) as obs:
            ...
            obs.update(output={"status": "success"})
    """
    if _client is None:
        yield SimpleNamespace(update=_noop_update)
        return
    try:
        manager = _client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
        observation = manager.__enter__()
    except Exception:
        logger.warning("Langfuse could not start observation %s", name, exc_info=True)
        yield SimpleNamespace(update=_noop_update)
        return
    try:
        yield observation
    except BaseException as exc:
        # Pass the real error on to the caller. Langfuse only records it.
        manager.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        manager.__exit__(None, None, None)
