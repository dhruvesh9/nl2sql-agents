"""The three eval levels. Each function grades one question and returns a result dict.

Level 1  classifier  Query Analyzer + Table Classifier, called as Python functions.
Level 2  sql         SQL Generator with the GOLD tables and GOLD runbooks as input, so a wrong
                     table from level 1 cannot hide or cause an SQL error.
Level 3  system      The real HTTP endpoint (/ask-quick or /ask). The question goes in, the answer
                     comes out. Errors from all agents add up here. The client answer has no SQL,
                     so the level 3 details have no SQL. Level 2 keeps the SQL for debugging.

Levels 1 and 2 import the agent code, so run the eval with the agent-service venv
(make eval does this). A missing "status" key never happens: every function sets it.
"""

import os
from typing import Any

import httpx

import compare
import scoring
from dataset import expects_refusal

AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8000")
HTTP_TIMEOUT_SECONDS = 180
MAX_ROWS = 1000  # the db-service limit. A bigger answer is cut, and we say so in the detail.


def skip(reason: str) -> dict[str, Any]:
    return {"status": "SKIP", "detail": reason}


def _analyze(row: dict, cache: dict[str, dict]) -> dict[str, Any]:
    """Run the Query Analyzer one time for each question and attempt. Levels 1 and 2 share it."""
    from app import knowledge
    from app.agents import query_analyzer

    if row["id"] not in cache:
        cache[row["id"]] = query_analyzer.run(row["question"], knowledge.read_index())
    return cache[row["id"]]


def _gold_result(row: dict, gold_cache: dict[str, dict]) -> dict[str, Any]:
    """Run the gold SQL one time and keep the rows."""
    from app import db_client

    if row["id"] not in gold_cache:
        gold_cache[row["id"]] = db_client.run_query(row["gold_sql"], MAX_ROWS)
    return gold_cache[row["id"]]


def _grade_rows(row: dict, got: dict, gold_cache: dict) -> tuple[str, str]:
    """Compare the rows of an answer with the rows of the gold SQL. Return (status, detail)."""
    gold = _gold_result(row, gold_cache)
    same, reason = compare.compare_results(gold["rows"], got["rows"], row["ordered"])
    if not same:
        reason += f" | expected {gold['rows'][:3]} got {got['rows'][:3]}"
    if gold["truncated"] or got.get("truncated"):
        reason += " (result cut at the row limit)"
    return ("MATCH" if same else "MISMATCH"), reason


def run_classifier(row: dict, cache: dict, gold_cache: dict) -> dict[str, Any]:
    """Level 1: did the Table Classifier select the gold tables? Also: did step 1 find the runbooks?"""
    if expects_refusal(row):
        return skip("refusal question")
    from app import knowledge, table_graph
    from app.agents import table_classifier

    requirements = _analyze(row, cache)
    graph = knowledge.read_graph()
    selected = table_classifier.run(
        requirements,
        table_graph.tables_text(graph),
        relationships_text=table_graph.relationships_text(graph),
    )["selected_tables"]
    result = scoring.score_tables(row["gold_tables"], selected)
    result["runbook_recall"] = scoring.runbook_recall(
        row["gold_runbooks"], requirements["runbook_candidates"]
    )
    result["detail"] = f"missing={result['missing']} extra={result['extra']}"
    return result


def run_sql_generator(row: dict, cache: dict, gold_cache: dict) -> dict[str, Any]:
    """Level 2: with perfect tables and runbooks, does the generated SQL give the gold rows?"""
    if expects_refusal(row) or not row["gold_sql"]:
        return skip("no gold SQL" if not expects_refusal(row) else "refusal question")
    from app import db_client, knowledge, pipeline
    from app.agents import sql_generator
    from app.config import settings

    requirements = _analyze(row, cache)
    schema = db_client.get_schema(row["gold_tables"], settings.fk_depth)
    runbook_texts = [knowledge.read_runbook(name) for name in row["gold_runbooks"]]
    sql = sql_generator.run(
        requirements, pipeline.schema_to_text(schema), runbook_texts, schema["dialect"]
    )["sql"]
    try:
        got = db_client.run_query(sql, MAX_ROWS)
    except db_client.DbServiceError as error:
        return {"status": "ERROR", "sql": sql, "detail": error.detail}
    status, detail = _grade_rows(row, got, gold_cache)
    return {"status": status, "sql": sql, "detail": detail}


def run_system(row: dict, endpoint: str, gold_cache: dict) -> dict[str, Any]:
    """Level 3: send the question to the endpoint and grade the client answer."""
    refusal = expects_refusal(row)
    if not refusal and not row["gold_sql"]:
        return skip("no gold SQL")
    response = httpx.post(
        f"{AGENT_URL}/{endpoint}", json={"question": row["question"]}, timeout=HTTP_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    body = response.json()
    # The client answer has no SQL and no reason. "data" is there only when the query gave rows,
    # so "data present" means the system answered with data. "answer" is the text for the user.
    answered = body.get("data") is not None
    if refusal:
        # A refusal question must not return data. A text or an error is a correct refusal.
        return {"kind": "refuse", "status": "ANSWERED" if answered else "REFUSED", "detail": ""}
    if not answered:
        return {"kind": "answer", "status": "FAILED", "detail": body["answer"]}
    status, detail = _grade_rows(
        row, body["data"], gold_cache
    )  # data has columns, rows and truncated
    return {"kind": "answer", "status": status, "detail": detail}
