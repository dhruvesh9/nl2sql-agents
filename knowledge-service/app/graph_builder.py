"""Builds the table graph from the live database and saves it as graph.json. No LLM call.

Pipeline step: knowledge base generation. A person runs it by hand with POST /generate.

Nodes are tables. Edges are foreign keys, from the table that holds the key to the table it points to.
We use a networkx MultiDiGraph, because one table can have two foreign keys to the same table
(customers -> addresses for billing AND for installation). A plain DiGraph keeps only one edge.

The file uses the node-link JSON format of networkx. Graph tools (D3, Cytoscape) can read it,
and networkx can load it back with json_graph.node_link_graph().
"""

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import networkx as nx
from networkx.readwrite import json_graph

from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_FILE = "graph.json"


def fetch_catalog() -> dict[str, Any]:
    """GET /catalog from db-service: every table with its comments and foreign keys.

    knowledge-service never connects to the database. db-service is the only component that does.
    """
    response = httpx.get(
        f"{settings.db_service_url}/catalog", timeout=settings.db_service_timeout_seconds
    )
    response.raise_for_status()
    return response.json()


def clean_text(value: Any) -> str:
    """Return a one-line text. None, a non-text value, or only spaces gives "".

    A database comment can hold new lines and extra spaces. One line per value keeps
    the prompt text short and the JSON diff easy to read.
    Example: clean_text("  Bills\\n per month ") -> "Bills per month"
    """
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _unique_tables(catalog: dict[str, Any], warnings: list[str]) -> dict[str, dict[str, Any]]:
    """Return table name -> table. Skip a table with no name, and keep the first copy of a name."""
    tables: dict[str, dict[str, Any]] = {}
    for table in catalog.get("tables") or []:
        name = clean_text(table.get("name"))
        if not name:
            warnings.append("skipped a table with no name")
        elif name in tables:
            warnings.append(f"{name}: listed twice, kept the first")
        else:
            tables[name] = table
    return tables


def _add_table_node(graph: nx.MultiDiGraph, name: str, table: dict[str, Any]) -> bool:
    """Add one table node. Return False when the table has no description."""
    descriptions = table.get("column_descriptions") or {}
    # Keep only the column comments that hold text. An empty comment tells the LLM nothing.
    columns = {column: text for column, raw in descriptions.items() if (text := clean_text(raw))}
    description = clean_text(table.get("description"))
    graph.add_node(name, type="table", description=description, column_descriptions=columns)
    return bool(description)


def _add_foreign_key_edges(
    graph: nx.MultiDiGraph, name: str, table: dict[str, Any], warnings: list[str]
) -> None:
    """Add one edge for each foreign key of the table."""
    for foreign_key in table.get("foreign_keys") or []:
        target = clean_text(foreign_key.get("ref_table"))
        columns = foreign_key.get("columns") or []
        if target not in graph:
            # For example a key to a table in another schema. An edge to an unknown node
            # would make networkx add an empty node, so we skip it and report it.
            warnings.append(f"{name}.{','.join(columns)} -> {target}: unknown table, skipped")
            continue
        # The key is the column list, so the two customers -> addresses edges stay apart
        # and the key is the same on every run.
        graph.add_edge(
            name,
            target,
            key=",".join(columns),
            type="foreign_key",
            columns=columns,
            ref_columns=foreign_key.get("ref_columns") or [],
        )


def build_graph(catalog: dict[str, Any]) -> tuple[nx.MultiDiGraph, list[str]]:
    """Build the graph from the /catalog answer. Return the graph and a list of warnings.

    The warnings report data problems (no table comment, unknown tables). They never stop the build.
    """
    warnings: list[str] = []
    graph = nx.MultiDiGraph(dialect=clean_text(catalog.get("dialect")))
    tables = _unique_tables(catalog, warnings)

    # First all the nodes, then all the edges: an edge can point to a table that comes later.
    missing_description = [
        name for name, table in tables.items() if not _add_table_node(graph, name, table)
    ]
    for name, table in tables.items():
        _add_foreign_key_edges(graph, name, table, warnings)

    if missing_description:
        # One line, not one warning per table: in a big schema there can be hundreds.
        warnings.append(
            f"{len(missing_description)} tables have no comment: {', '.join(missing_description)}"
        )
    return graph, warnings


def write_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    """Save the graph as node-link JSON. Write a temporary file, then rename it.

    The rename is atomic, so a reader (GET /graph) never sees a half-written file.
    """
    data = json_graph.node_link_data(graph, edges="edges")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        handle.write(text)
    os.replace(handle.name, path)


def generate() -> dict[str, Any]:
    """Read the catalog, build the graph, and save graph.json. Return a short summary."""
    graph, warnings = build_graph(fetch_catalog())
    graph.graph["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    write_graph(graph, Path(settings.knowledge_base_dir) / GRAPH_FILE)

    for warning in warnings:
        logger.warning("generate: %s", warning)
    logger.info(
        "generate: %d tables, %d foreign keys", graph.number_of_nodes(), graph.number_of_edges()
    )
    return {
        "tables": graph.number_of_nodes(),
        "foreign_keys": graph.number_of_edges(),
        "generated_at": graph.graph["generated_at"],
        "warnings": warnings,
    }
