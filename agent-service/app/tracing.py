"""Langfuse tracing helpers. Tracing is optional and off by default.

Pipeline step: infrastructure (observability for all steps).
When LANGFUSE_ENABLED is false, every helper does nothing, so the app works without Langfuse.
Tracing must never break a request: if Langfuse fails, we only log a warning.

What a trace shows (see request_trace, observe, and app/step_trace.py):
- One trace for each request. Its ID is the request ID, so you paste the ID from a log line or from
  a client error into Langfuse and find the trace. It has the tags, the environment, the app version,
  the prompt version, and the models.
- One child observation for each pipeline step (agent, tool or retriever) with a small input and
  output, and under it the LLM calls (generations) with prompt, answer, tokens, and time.
- A step that fails is marked ERROR with the message.
- Scores on the trace (outcome, rows_returned), so you can filter and count in Langfuse.
Result rows are never sent. They can hold personal data.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from typing import Any

from langfuse import Langfuse, propagate_attributes

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
        environment=settings.environment,
        release=settings.app_version,
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
        # Mark the observation as an error, so it is easy to find in Langfuse.
        # Then pass the real error on to the caller. Langfuse only records it.
        try:
            observation.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
        except Exception:
            logger.warning("Langfuse could not mark %s as an error", name, exc_info=True)
        manager.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        manager.__exit__(None, None, None)


def trace_id_for(request_id: str) -> str | None:
    """The Langfuse trace ID for a request ID. None when tracing is off.

    A request ID of 32 hex characters is used as it is, so it is the same in the logs and in Langfuse.
    Any other ID (for example from a gateway) is turned into a trace ID, and the request ID
    stays in the trace metadata.
    """
    if _client is None:
        return None
    if len(request_id) == 32 and all(c in "0123456789abcdef" for c in request_id):
        return request_id
    return _client.create_trace_id(seed=request_id)


@contextmanager
def request_trace(
    name: str, request_id: str, input: Any, metadata: dict[str, str] | None = None
) -> Iterator[Any]:
    """Open the trace of one request. Use it once, at the start of an endpoint.

    name is the trace name (the endpoint). metadata holds short text values
    (Langfuse keeps text up to 200 characters), for example the prompt version.
    """
    if _client is None:
        yield SimpleNamespace(update=_noop_update)
        return
    attributes = {"request_id": request_id, **(metadata or {})}
    try:
        context = propagate_attributes(
            trace_name=name,
            tags=[name, settings.environment],
            version=settings.app_version,
            metadata=attributes,
        )
    except Exception:
        logger.warning("Langfuse could not set the trace attributes", exc_info=True)
        context = nullcontext()
    with (
        context,
        observe(
            name, input=input, trace_context={"trace_id": trace_id_for(request_id)}
        ) as observation,
    ):
        yield observation


def score(name: str, value: float | str, data_type: str, comment: str | None = None) -> None:
    """Add a score to the current trace. data_type is NUMERIC, CATEGORICAL, or BOOLEAN.

    Scores let you filter and count traces in Langfuse (for example all traces with outcome=LLM_BUSY).
    """
    if _client is None:
        return
    try:
        _client.score_current_trace(name=name, value=value, data_type=data_type, comment=comment)
    except Exception:
        logger.warning("Langfuse could not add the score %s", name, exc_info=True)
