"""Reads the knowledge base files: index.md, graph.json, and runbooks.

Pipeline step: serves steps 1A (index), 2A (tables and relationships), and 5A (runbooks) of agent-service.

We do not use RAG here. The files are small, so the agent passes the whole text to the LLM.
This is simpler, and there are no retrieval errors.
"""

import json
import re
from pathlib import Path
from typing import Any

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


def read_graph() -> dict[str, Any]:
    """Return graph.json: the table graph that POST /generate builds (node-link JSON)."""
    path = _base_dir() / "graph.json"
    if not path.is_file():
        raise FileNotFoundError("graph.json not found. Run POST /generate first.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        # Only a hand edit can break the file: /generate writes it in one atomic step.
        raise RuntimeError(f"graph.json is not valid JSON: {error}") from error


def read_runbook(name: str) -> str:
    """Return the text of one runbook, for example read_runbook("active_customer").

    The name has no ".md" at the end. It may hold only letters, digits, and underscores.
    This blocks names like "../../.env", so nobody can read other files.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"Invalid runbook name: {name!r}")
    return _read_file(_base_dir() / "runbooks" / f"{name}.md")
