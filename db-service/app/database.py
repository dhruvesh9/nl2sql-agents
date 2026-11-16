"""Database engine for db-service. This is the only module that creates a connection.

Pipeline step: infrastructure.
"""

import logging

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql.elements import TextClause

from app.config import settings

logger = logging.getLogger(__name__)

# Local PostgreSQL and hosted providers (for example Supabase) both use this engine.
# Only DATABASE_URL changes.
# prepare_threshold=None turns off server-side prepared statements.
# Poolers in transaction mode (Supabase port 6543) do not support them.
# pool_pre_ping drops dead connections, which hosted databases close when idle.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"prepare_threshold": None},
)


def sql_to_text(sql: str) -> TextClause:
    """Wrap a SQL string for SQLAlchemy.

    text() treats ':name' as a bind parameter. LLM SQL can contain ':' in strings, like '12:30'.
    We write each ':' as '\\:' so that SQLAlchemy sends the SQL as it is.
    """
    return text(sql.replace(":", "\\:"))


def start_readonly(conn: Connection) -> None:
    """Make the current transaction read-only and set the statement timeout.

    Call it first on a new connection. This is a PostgreSQL feature.
    SET LOCAL lasts only for the current transaction, so the pooled connection stays clean.
    """
    conn.execute(text("SET TRANSACTION READ ONLY"))
    conn.execute(text(f"SET LOCAL statement_timeout = {int(settings.statement_timeout_ms)}"))


def error_message(error: DBAPIError) -> str:
    """Return the first line of a database error. The first line has the useful part."""
    return str(error.orig).splitlines()[0]


def get_dialect() -> str:
    """Return the SQL dialect name, for example 'postgresql'."""
    return engine.dialect.name


def check_connection() -> bool:
    """Run SELECT 1. Return True if the database answers, False if it does not."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        # Log the error, but do not crash: /health must be able to report the problem.
        logger.exception("Database connection check failed")
        return False
