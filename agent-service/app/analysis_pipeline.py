"""Mini pipeline: step 1 (Query Analyzer) and step 2 (Table Classifier) only.

Pipeline step: 1 and 2. Used by POST /analyze.
We use it to test the two agents alone, before we build the next agents.
The eval project (eval/) calls this pipeline and measures the accuracy.
"""

import logging
import time
from typing import Any

from app import knowledge
from app.agents import query_analyzer, table_classifier
from app.models import AnalyzeResponse, TraceEntry

logger = logging.getLogger(__name__)


def _trace(step: str, name: str, start: float, summary: str) -> TraceEntry:
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return TraceEntry(step=step, name=name, elapsed_ms=elapsed_ms, summary=summary)


def run_analysis(question: str) -> AnalyzeResponse:
    """Run step 1, then step 2. Return the requirements and the selected tables.

    A chit-chat question ("hello") stops after step 1, because it needs no tables.
    """
    trace: list[TraceEntry] = []
    logger.info("analysis start: question=%r", question)

    start = time.perf_counter()
    requirements: dict[str, Any] = query_analyzer.run(question, knowledge.read_index())
    trace.append(_trace("1", "query_analyzer", start, f"intent={requirements['intent']}"))
    logger.info("step 1 query_analyzer output: %s", requirements)

    if requirements["intent"] == "chitchat":
        logger.info("intent is chitchat: skip step 2")
        return AnalyzeResponse(question=question, requirements=requirements, trace=trace)

    start = time.perf_counter()
    # The file is read on each request, so your edits work at once, without a restart.
    relationships = knowledge.read_relationships()
    logger.info("table_relationship.md: %d lines", len(relationships.splitlines()))
    result = table_classifier.run(
        requirements, knowledge.read_tables(), relationships_md=relationships
    )
    summary = ", ".join(result["selected_tables"])
    trace.append(_trace("2", "table_classifier", start, f"tables={summary}"))
    logger.info("step 2 table_classifier output: %s", result)

    return AnalyzeResponse(
        question=question,
        requirements=requirements,
        selected_tables=result["selected_tables"],
        reason=result["reason"],
        trace=trace,
    )
