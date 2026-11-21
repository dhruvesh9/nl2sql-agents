"""Request IDs and structured logs. The same file is in all three services.

Pipeline step: infrastructure (observability).

- Every request has a request ID. agent-service takes it from the X-Request-ID header or makes one.
  It sends the ID to db-service and knowledge-service in the same header. Each service puts the
  ID in every log line and in the response header. With one ID you follow one question through all
  three services.
- Logs are JSON, one object per line (LOG_FORMAT=json), or short text for a terminal (LOG_FORMAT=text).
  Extra fields come from logger.info("message", extra={"key": value}). Keep the message the same
  every time and put the changing values in fields. Then a log tool can search and count them.
- install() adds the middleware: it sets the request ID and writes ONE "request" log line for each
  request, with method, path, status, and duration_ms. This line is the base for latency
  and error-rate dashboards.

The file is copied into each project, because each service is a separate project with its own venv.
If you change it, change all three copies (the tests in each service check the same rules).
"""

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TextIO

from fastapi import FastAPI, Request, Response

REQUEST_ID_HEADER = "X-Request-ID"
# A request ID from outside must be short and plain, so it cannot break a log line or a header.
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
# These paths are called all the time by health checks. They are logged at DEBUG only.
_QUIET_PATHS = {"/health"}

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# The normal fields of a log record. Every other field of a record came from "extra".
_STANDARD_FIELDS = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "service",
    "request_id",
}

logger = logging.getLogger("request")


def new_request_id() -> str:
    """A new ID: 32 hex characters, the same format as a Langfuse trace ID."""
    return uuid.uuid4().hex


def pick_request_id(incoming: str | None) -> str:
    """Use the ID from the caller when it is safe. Else make a new one."""
    if incoming and _VALID_ID.match(incoming):
        return incoming
    return new_request_id()


def current_request_id() -> str:
    """The ID of the request that this code runs for. Empty outside a request."""
    return request_id_var.get()


class LogFormatter(logging.Formatter):
    """Writes a log record as one JSON line, or as one readable text line."""

    def __init__(self, fmt: str) -> None:
        super().__init__()
        self.as_json = fmt == "json"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        extras = {key: value for key, value in vars(record).items() if key not in _STANDARD_FIELDS}
        request_id = getattr(record, "request_id", "")
        error = self.formatException(record.exc_info) if record.exc_info else None
        if self.as_json:
            data = {
                "ts": timestamp,
                "level": record.levelname,
                "service": getattr(record, "service", ""),
                "request_id": request_id or None,
                "logger": record.name,
                "msg": record.getMessage(),
                **extras,
            }
            if error:
                data["exc"] = error
            return json.dumps(data, default=str, ensure_ascii=False)
        fields = " ".join(f"{key}={value}" for key, value in extras.items())
        line = f"{timestamp} {record.levelname} [{request_id[:8] or '-'}] {record.name}: {record.getMessage()}"
        line = f"{line} {fields}".rstrip()
        return f"{line}\n{error}" if error else line


def make_handler(service: str, fmt: str, stream: TextIO | None = None) -> logging.Handler:
    """A log handler that adds the service name and the request ID to every record."""

    def add_context(record: logging.LogRecord) -> bool:
        record.service = service
        record.request_id = request_id_var.get()
        return True

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(LogFormatter(fmt))
    handler.addFilter(add_context)
    return handler


def setup_logging(service: str, level: str, fmt: str) -> None:
    """Send all logs of the process, also the logs of uvicorn, through one handler."""
    handler = make_handler(service, fmt)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True  # the root handler writes them in our format
    # The middleware writes one better line for each request, so uvicorn's access line is a copy.
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "together", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def install(app: FastAPI) -> None:
    """Add the request ID and the request log line to every request of the app."""

    @app.middleware("http")
    async def request_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = pick_request_id(request.headers.get(REQUEST_ID_HEADER))
        # No reset after the request: each request runs in its own task, so the value cannot leak.
        # The error handlers outside this middleware still need to read it.
        request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            quiet = request.url.path in _QUIET_PATHS and status < 500
            logger.log(
                logging.DEBUG if quiet else (logging.ERROR if status >= 500 else logging.INFO),
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                },
            )
