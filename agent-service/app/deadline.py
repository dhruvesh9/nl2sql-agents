"""The time budget of one request. Every step checks it before it starts.

Pipeline step: infrastructure (error handling).
A request must not hang for minutes: the UI user would wait for nothing. Each call to an LLM or a
service has its own timeout, but several slow steps can still add up. So run_quick starts a budget
(REQUEST_TIMEOUT_SECONDS) and step() checks it before each step. Python code that waits for an HTTP
answer cannot be stopped from outside, so we stop between the steps. The step that is running still
ends by its own timeout, so the total time is the budget plus at most one call.
"""

import contextvars
import time

from app.config import settings

_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar("deadline", default=None)


def start(seconds: float | None = None) -> None:
    """Start the budget for the current request. Call it once at the start of a pipeline."""
    _deadline.set(
        time.monotonic() + (settings.request_timeout_seconds if seconds is None else seconds)
    )


def check(next_step: str) -> None:
    """Raise TimeoutError when the budget is used. Do nothing when no budget was started."""
    limit = _deadline.get()
    if limit is not None and time.monotonic() > limit:
        raise TimeoutError(f"the time budget of the request is used, before step {next_step}")
