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
from collections.abc import Callable
from typing import Any

from app import db_client, knowledge, pipeline, table_graph
from app.agents import query_analyzer, response_agent, sql_generator, table_classifier
from app.config import settings
from app.models import AskResponse, TraceEntry
from app.step_trace import step

logger = logging.getLogger(__name__)


def _select_tables(
    question: str, requirements: dict[str, Any], trace: list[TraceEntry]
) -> list[str]:
    """Step 2: give the requirements and the table graph to the Table Classifier."""
    with step(trace, "2", "table_classifier", "agent", question=question) as out:
        graph = knowledge.read_graph()
        result = table_classifier.run(
            requirements,
            table_graph.tables_text(graph),
            relationships_text=table_graph.relationships_text(graph),
        )
        tables = result["selected_tables"]
        out["summary"] = f"tables={', '.join(tables)}"
        out["output"] = {
            "tables": tables,
            "reason": result["reason"],
            "graph_tables": len(graph["nodes"]),
            "graph_foreign_keys": len(graph["edges"]),
        }
    return tables


def _write_sql(
    question: str, requirements: dict[str, Any], tables: list[str], trace: list[TraceEntry]
) -> str:
    """Step 3 (live schema from db-service) and step 5 (SQL Generator). Return the SQL."""
    with step(
        trace, "3", "schema_discovery", "tool", tables=tables, fk_depth=settings.fk_depth
    ) as out:
        schema = db_client.get_schema(tables, settings.fk_depth)
        found = [table["name"] for table in schema["tables"]]
        out["summary"] = f"tables={len(found)}"
        out["output"] = {"tables": found, "not_found": schema.get("not_found", [])}

    names = requirements.get("runbook_candidates") or []
    with step(trace, "5", "sql_generator", "agent", question=question, runbooks=names) as out:
        # Load the runbook text only now and only for the names step 1 found: fewer tokens.
        runbook_texts = [knowledge.read_runbook(name) for name in names]
        schema_text = pipeline.schema_to_text(schema)
        generated = sql_generator.run(requirements, schema_text, runbook_texts, schema["dialect"])
        out["summary"] = f"runbooks={names}; {generated['explanation']}"
        out["output"] = {
            "sql": generated["sql"],
            "explanation": generated["explanation"],
            "schema_chars": len(schema_text),
        }
    return generated["sql"]


def _run_query(sql: str, trace: list[TraceEntry]) -> dict[str, Any]:
    """Step 7: run the SQL. The step shows the SQL, the row count, and the time of the query."""
    with step(trace, "7", "sql_execution", "tool", sql=sql) as out:
        try:
            result = db_client.run_query(sql)
        except db_client.DbServiceError as error:
            # With no validator yet, a bad query shows up here. Keep the SQL with the error.
            out["summary"] = f"error: {error.detail}; sql={sql}"
            out["output"] = {"error": error.detail}
            raise
        out["summary"] = f"rows={result['row_count']}"
        out["output"] = {
            "row_count": result["row_count"],
            "truncated": result.get("truncated"),
            "db_elapsed_ms": result.get("elapsed_ms"),
        }
    return result


def _run(question: str, trace: list[TraceEntry], request_id: str) -> AskResponse:
    """The steps in order. Any failure is raised, and run_quick turns it into a response."""
    with step(trace, "1", "query_analyzer", "agent", question=question) as out:
        requirements = query_analyzer.run(question, knowledge.read_index())
        out["summary"] = f"intent={requirements['intent']}"
        out["output"] = requirements

    # A greeting ("hello") needs no tables, so we stop before any more LLM calls.
    if requirements["intent"] == "chitchat":
        return _respond(
            trace, lambda: response_agent.for_message("chitchat", question, request_id, trace)
        )

    tables = _select_tables(question, requirements, trace)
    if not tables:
        return _respond(
            trace,
            lambda: response_agent.for_message("no_matching_data", question, request_id, trace),
        )

    sql = _write_sql(question, requirements, tables, trace)
    result = _run_query(sql, trace)
    return _respond(
        trace, lambda: response_agent.for_rows(result, sql, question, request_id, trace)
    )


def _respond(trace: list[TraceEntry], build: Callable[[], AskResponse]) -> AskResponse:
    """Step 8: the Response Agent builds the client response. It is a step like the others."""
    with step(trace, "8", "response_agent", "agent") as out:
        response = build()
        out["summary"] = _describe(response)
        out["output"] = {"has_data": response.data is not None, "code": response.code}
    # The response holds a copy of the list (pydantic copies it). Give it the full trace, with step 8.
    response.trace = trace
    return response


def _describe(response: AskResponse) -> str:
    """A short line for the trace. It names the kind of answer, never the data."""
    if response.code:
        return f"error {response.code}"
    return f"answer with {len(response.data.rows)} row(s)" if response.data else "answer text"


def _fail(error: Exception, trace: list[TraceEntry], request_id: str) -> AskResponse:
    """Give an error to the Response Agent (step 8). The error was already logged by its step."""
    return _respond(trace, lambda: response_agent.for_error(error, request_id, trace))


def run_quick(question: str, request_id: str = "") -> AskResponse:
    """Analyze the question, pick the tables, write the SQL, run it once, and build the response."""
    trace: list[TraceEntry] = []
    logger.info("ask-quick start", extra={"question": question})
    try:
        return _run(question, trace, request_id)
    except Exception as error:  # noqa: BLE001 - the one place that turns any failure into a response
        return _fail(error, trace, request_id)
