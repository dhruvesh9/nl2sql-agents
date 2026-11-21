"""One helper for the three records of a pipeline step: log line, trace entry, and Langfuse span.

Pipeline step: infrastructure (observability for all steps).
Before, each step wrote its own log line and its own trace entry. Now a step is a `with` block:

    with step(trace, "2", "table_classifier", "agent", question=question) as out:
        result = table_classifier.run(...)
        out["summary"] = "tables=a, b"          # one short line: goes to the log and the trace
        out["output"] = {"tables": [...]}       # goes to the Langfuse span (keep it small)

The block records the time. If the block raises an error, the step is marked as failed, the
error goes on, and the pipeline catches it in one place (run_quick).
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.models import TraceEntry
from app.tracing import observe

logger = logging.getLogger(__name__)


@contextmanager
def step(
    trace: list[TraceEntry], step_id: str, name: str, kind: str = "span", **input: Any
) -> Iterator[dict[str, Any]]:
    """Run one step. kind is the Langfuse type: "agent" (LLM), "tool" (code or service), "retriever".

    The input keyword arguments are shown on the Langfuse span. Never pass result rows.
    """
    result: dict[str, Any] = {"summary": "", "output": None}
    start = time.perf_counter()
    failed = False
    try:
        with observe(f"{step_id}_{name}", as_type=kind, input=input or None) as observation:
            yield result
            observation.update(output=result["output"], metadata={"summary": result["summary"]})
    except Exception as error:
        failed = True
        # A step can set its own summary before it raises (for example the SQL). Keep it.
        result["summary"] = result["summary"] or f"error: {error}"
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        trace.append(
            TraceEntry(step=step_id, name=name, elapsed_ms=elapsed_ms, summary=result["summary"])
        )
        # The message is the same for every step. The values are fields (see observability.py).
        logger.log(
            logging.WARNING if failed else logging.INFO,
            "step",
            extra={
                "step": step_id,
                "step_name": name,
                "elapsed_ms": elapsed_ms,
                "failed": failed,
                "summary": result["summary"],
            },
        )
