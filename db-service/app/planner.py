"""Gets the query plan from the database without running the query.

Pipeline step: 6 (SQL Validator, action 6A), db-service side. Used by POST /plan.
The dialect-specific EXPLAIN SQL lives in this file only.
"""

from sqlalchemy.exc import DBAPIError

from app.database import engine, error_message, get_dialect, sql_to_text, start_readonly
from app.models import PlanResponse
from app.sql_guard import check_sql


def build_explain_statement(sql: str, dialect: str) -> str:
    """Return the EXPLAIN statement for the dialect.

    We never use ANALYZE. EXPLAIN ANALYZE runs the query. Plain EXPLAIN only plans it.
    To add MySQL or Oracle later, add a new branch here.

    Example: build_explain_statement("SELECT 1;", "postgresql") -> "EXPLAIN (FORMAT JSON) SELECT 1"
    """
    if dialect == "postgresql":
        return "EXPLAIN (FORMAT JSON) " + sql.strip().rstrip(";")
    raise ValueError(f"EXPLAIN is not supported for the dialect: {dialect}")


def get_plan(sql: str) -> PlanResponse:
    """Check the SQL with the guard, run EXPLAIN, and return cost and estimated rows.

    If the database does not accept the SQL (for example, a wrong column name),
    we return valid=False and the database message.
    """
    dialect = get_dialect()
    check_sql(sql, dialect)  # a rejected SQL raises SqlRejectedError (HTTP 400)
    explain_sql = build_explain_statement(sql, dialect)

    try:
        with engine.connect() as conn:
            start_readonly(conn)
            result = conn.execute(sql_to_text(explain_sql)).scalar()
    except DBAPIError as error:
        return PlanResponse(valid=False, error=error_message(error))

    # PostgreSQL returns a list with one item. The item has the key "Plan".
    plan = result[0]["Plan"]
    return PlanResponse(
        valid=True,
        estimated_cost=plan["Total Cost"],
        estimated_rows=plan["Plan Rows"],
        plan=plan,
    )
