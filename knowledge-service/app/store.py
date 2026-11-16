"""Reads the knowledge base files: index.md, tables.md, table_relationship.md, and runbooks.

Pipeline step: serves steps 1A (index), 2A (tables and relationships), and 5A (runbooks) of agent-service.

We do not use RAG here. The files are small, so the agent passes the whole text to the LLM.
This is simpler, and there are no retrieval errors.
"""

import re
from pathlib import Path

from app.config import settings


def _base_dir() -> Path:
    return Path(settings.knowledge_base_dir)


def _read_file(path: Path) -> str:
    """Read one text file. Raise a clear error if the file does not exist."""
    if not path.is_file():
        raise FileNotFoundError(f"Knowledge base file not found: {path.name}")
    return path.read_text(encoding="utf-8")


def read_index() -> str:
    """Return the text of index.md."""
    return _read_file(_base_dir() / "index.md")


def read_tables() -> str:
    """Return the text of tables.md (one line per table)."""
    return _read_file(_base_dir() / "tables.md")


def read_relationships() -> str:
    """Return the text of table_relationship.md, or "" if the file is empty or missing.

    The file shows how the tables link to each other. It is optional,
    so a missing file is not an error.
    """
    path = _base_dir() / "table_relationship.md"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def read_runbook(name: str) -> str:
    """Return the text of one runbook, for example read_runbook("active_customer").

    The name has no ".md" at the end. It may hold only letters, digits, and underscores.
    This blocks names like "../../.env", so nobody can read other files.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Invalid runbook name: {name!r}")
    return _read_file(_base_dir() / "runbooks" / f"{name}.md")
