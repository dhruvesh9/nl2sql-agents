"""SQL guard: accepts only one safe SELECT statement.

Pipeline step: 6 and 7 (db-service side). /plan and /query call it before any SQL runs.

Why not search for words like DELETE? A word search blocks valid SQL such as
SELECT 'delete me', and it misses tricks. A parser understands the real structure.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

# sqlglot uses the name "postgres". SQLAlchemy uses "postgresql".
SQLGLOT_DIALECTS = {"postgresql": "postgres"}

# The top-level statement must be one of these.
ALLOWED_TOP_LEVEL = (exp.Select, exp.SetOperation, exp.Subquery)

# These must not appear anywhere in the statement.
# Example: WITH x AS (DELETE FROM a RETURNING *) SELECT * FROM x
FORBIDDEN_NODES = {
    exp.Insert: "INSERT is not allowed",
    exp.Update: "UPDATE is not allowed",
    exp.Delete: "DELETE is not allowed",
    exp.Merge: "MERGE is not allowed",
    exp.Create: "CREATE is not allowed",
    exp.Drop: "DROP is not allowed",
    exp.Alter: "ALTER is not allowed",
    exp.Command: "Commands are not allowed",
    exp.Into: "SELECT ... INTO is not allowed because it creates a table",
    exp.Lock: "SELECT ... FOR UPDATE is not allowed because it locks rows",
}


class SqlRejectedError(ValueError):
    """Raised when the SQL is not allowed. The message is the reason. The API returns HTTP 400."""


def check_sql(sql: str, dialect: str = "postgres") -> None:
    """Parse the SQL with sqlglot. Raise SqlRejectedError if the SQL is not allowed.

    Allowed: exactly one SELECT, a WITH ... SELECT, or a UNION of SELECTs.

    Example:
        check_sql("SELECT 1")                -> None
        check_sql("DELETE FROM customers")   -> raises SqlRejectedError("Only SELECT is allowed")
    """
    dialect = SQLGLOT_DIALECTS.get(dialect, dialect)

    try:
        parsed = sqlglot.parse(sql, read=dialect)
    except SqlglotError as error:
        raise SqlRejectedError(f"The SQL cannot be parsed: {error}") from error

    # A trailing semicolon, or an empty text, gives None entries. Remove them.
    statements = [statement for statement in parsed if statement is not None]

    if len(statements) == 0:
        raise SqlRejectedError("The SQL is empty")
    if len(statements) > 1:
        raise SqlRejectedError("Only one statement is allowed")

    statement = statements[0]
    if not isinstance(statement, ALLOWED_TOP_LEVEL):
        raise SqlRejectedError("Only SELECT is allowed")

    # walk() visits every part of the statement, including the parts inside a WITH.
    for node in statement.walk():
        for forbidden_type, reason in FORBIDDEN_NODES.items():
            if isinstance(node, forbidden_type):
                raise SqlRejectedError(reason)
