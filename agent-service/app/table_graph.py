"""Turns the table graph (graph.json from knowledge-service) into short text for the prompts.

Pipeline step: 2A. The Table Classifier gets this text.

The graph is node-link JSON: each node is a table, each edge is a foreign key.
We send text, not the JSON, because text is shorter. That matters for a schema with 1000 tables.
"""

from typing import Any

RELATIONSHIPS_HEADER = (
    'Each line "A.column -> B.column" is a foreign key: join A and B on these columns.\n'
    "A link works in both directions. To connect two tables, follow the lines from one to the other."
)


def tables_text(graph: dict[str, Any]) -> str:
    """Return one line per table: "- name: description". Sorted by name.

    A table without a comment in the database gets "- name:" with no text after it.
    The Table Classifier reads the names back from these lines, so keep the format.

    Example:
        tables_text({"nodes": [{"id": "invoices", "description": "Monthly bills."}]})
        -> "- invoices: Monthly bills."
    """
    lines = []
    for node in sorted(graph.get("nodes", []), key=lambda item: item["id"]):
        lines.append(f"- {node['id']}: {node.get('description') or ''}".rstrip())
    return "\n".join(lines)


def relationships_text(graph: dict[str, Any]) -> str:
    """Return one line per foreign key, with its columns. Return "" when there are no foreign keys.

    The column names matter: customers has two keys to addresses (billing and installation),
    and only the columns tell the LLM that there are two different join paths.

    Example:
        -> "customers.billing_address_id -> addresses.id"
    """
    lines = []
    for edge in graph.get("edges", []):
        columns = ",".join(edge.get("columns", []))
        ref_columns = ",".join(edge.get("ref_columns", []))
        lines.append(f"{edge['source']}.{columns} -> {edge['target']}.{ref_columns}")
    if not lines:
        return ""
    # sorted() gives the same prompt on every run, so the LLM answer is easier to compare.
    return RELATIONSHIPS_HEADER + "\n\n" + "\n".join(sorted(lines))
