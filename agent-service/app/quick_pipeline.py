"""Quick end-to-end pipeline: steps 1, 2, 3, 5, 7 and 8, with no feedback loops.

Pipeline step: 1, 2, 3, 5, 7, 8. Used by POST /ask-quick.
The steps raise errors when they fail. run_quick catches every error in ONE place and gives it
to the Response Agent (step 8), which builds the client response. The steps write no messages.
It is a shortcut to see the whole flow work. It skips steps 4 and 6.
It sends the runbooks from step 1 to the SQL generator, so business rules (for example
"unpaid" means status 'O') reach the SQL.
It runs SQL that no validator checked. Only the SELECT-only guard in db-service protects us.
POST /ask (pipeline.run_pipeline) is the full flow with Loop A and Loop B.
"""

import logging
import time
from typing import Any

from app import db_client, knowledge, pipeline, table_graph
from app.agents import query_analyzer, response_agent, sql_generator, table_classifier
from app.config import settings
from app.models import AskResponse, TraceEntry

logger = logging.getLogger(__name__)


def _trace(step: str, name: str, start: float, summary: str) -> TraceEntry:
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return TraceEntry(step=step, name=name, elapsed_ms=elapsed_ms, summary=summary)


def _select_tables(requirements: dict[str, Any], trace: list[TraceEntry]) -> list[str]:
    """Step 2: give the requirements and the table graph to the Table Classifier."""
    start = time.perf_counter()
    graph = knowledge.read_graph()
    logger.info("table graph: %d tables, %d foreign keys", len(graph["nodes"]), len(graph["edges"]))
    result = table_classifier.run(
        requirements,
        table_graph.tables_text(graph),
        relationships_text=table_graph.relationships_text(graph),
    )
    logger.info("step 2 table_classifier output: %s", result)
    trace.append(
        _trace("2", "table_classifier", start, f"tables={', '.join(result['selected_tables'])}")
    )
    return result["selected_tables"]


def _write_sql(requirements: dict[str, Any], tables: list[str], trace: list[TraceEntry]) -> str:
    """Step 3 (live schema from db-service) and step 5 (SQL Generator). Return the SQL."""
    start = time.perf_counter()
    schema = db_client.get_schema(tables, settings.fk_depth)
    trace.append(_trace("3", "schema_discovery", start, f"tables={len(schema['tables'])}"))

    start = time.perf_counter()
    schema_text = pipeline.schema_to_text(schema)
    # Load the runbook text only now and only for the names step 1 found: less text, fewer tokens.
    names = requirements.get("runbook_candidates") or []
    runbook_texts = [knowledge.read_runbook(name) for name in names]
    generated = sql_generator.run(requirements, schema_text, runbook_texts, schema["dialect"])
    logger.info("step 5 sql_generator output: %s", generated)
    trace.append(
        _trace("5", "sql_generator", start, f"runbooks={names}; {generated['explanation']}")
    )
    return generated["sql"]


def _run(question: str, trace: list[TraceEntry], request_id: str) -> AskResponse:
    """The steps in order. Any failure is raised, and run_quick turns it into a response."""
    logger.info("ask-quick start: request_id=%s question=%r", request_id, question)

    start = time.perf_counter()
    requirements = query_analyzer.run(question, knowledge.read_index())
    logger.info("step 1 query_analyzer output: %s", requirements)
    trace.append(_trace("1", "query_analyzer", start, f"intent={requirements['intent']}"))

    # A greeting ("hello") needs no tables, so we stop before any more LLM calls.
    if requirements["intent"] == "chitchat":
        return response_agent.for_message("chitchat", question, request_id, trace)

    tables = _select_tables(requirements, trace)
    if not tables:
        return response_agent.for_message("no_matching_data", question, request_id, trace)

    sql = _write_sql(requirements, tables, trace)

    start = time.perf_counter()
    try:
        result = db_client.run_query(sql)
    except db_client.DbServiceError as error:
        # With no validator yet, a bad query shows up here. Keep the SQL in the trace for debugging.
        trace.append(_trace("7", "sql_execution", start, f"error: {error.detail}; sql={sql}"))
        raise
    trace.append(_trace("7", "sql_execution", start, f"rows={result['row_count']}"))
    return response_agent.for_rows(result, sql, question, request_id, trace)


def run_quick(question: str, request_id: str = "") -> AskResponse:
    """Analyze the question, pick the tables, write the SQL, run it once, and build the response."""
    trace: list[TraceEntry] = []
    try:
        return _run(question, trace, request_id)
    except Exception as error:  # noqa: BLE001 - the one place that turns any failure into a response
        return response_agent.for_error(error, request_id, trace)
