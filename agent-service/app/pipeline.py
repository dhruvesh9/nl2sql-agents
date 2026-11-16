"""Pipeline orchestrator: runs steps 1 to 8 and the two feedback loops.

Pipeline step: all. POST /ask calls run_pipeline.
"""

from typing import Any

from app.models import AskResponse


def schema_to_text(schema: dict[str, Any]) -> str:
    """Convert the /schema response to a compact text for the prompts. One line per column.

    Example output:
        TABLE orders (Orders placed by an account)
          id INTEGER PK
          account_id INTEGER FK->accounts.id
    """
    raise NotImplementedError(
        "Live schema discovery (step 3) is not implemented yet. See the roadmap in README.md."
    )


def run_pipeline(question: str) -> AskResponse:
    """Run the full pipeline for one question and return the response with the trace.

    Step order:
        1.  Query Analyzer       -> requirements, runbook candidates
        R.  Runbook Selector     -> update after step 1
        Loop A, up to MAX_TABLE_ATTEMPTS times:
          2.  Table Classifier   -> selected tables
          3.  Live schema        -> POST /schema, schema_to_text
          4.  Table Feedback     -> score, hints. Stop at PASS_SCORE.
        Loop B, up to MAX_SQL_ATTEMPTS times:
          5.  SQL Generator      -> candidate SELECT
          6.  SQL Validator      -> hard checks + judge, POST /plan
        7.  Execute              -> POST /query, only after a pass
        8.  Response Builder     -> success or failure with a reason

    Rules:
        Never execute SQL that did not pass step 6.
        Add one trace entry per step and per attempt.
        When a loop uses all attempts, go to step 8 with a failure reason.

    Tracing: wrap each step in app.tracing.observe(...).
    """
    raise NotImplementedError(
        "The full pipeline (POST /ask) is not implemented yet. See the roadmap in README.md."
    )
