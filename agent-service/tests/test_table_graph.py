"""Tests for app/table_graph.py: the table graph as prompt text."""

from app import table_graph
from app.agents import table_classifier

GRAPH = {
    "nodes": [
        {"id": "customers", "description": "People who buy."},
        {"id": "addresses", "description": "Postal addresses."},
        {"id": "tax_rates", "description": ""},  # a table with no comment in the database
    ],
    "edges": [
        {
            "source": "customers",
            "target": "addresses",
            "columns": ["installation_address_id"],
            "ref_columns": ["id"],
        },
        {
            "source": "customers",
            "target": "addresses",
            "columns": ["billing_address_id"],
            "ref_columns": ["id"],
        },
    ],
}


def test_tables_text_has_one_sorted_line_per_table() -> None:
    assert table_graph.tables_text(GRAPH) == (
        "- addresses: Postal addresses.\n- customers: People who buy.\n- tax_rates:"
    )


def test_the_classifier_can_read_every_table_name_back() -> None:
    # Also the table without a description: a lost name means the LLM answer for it is dropped.
    names = table_classifier.list_table_names(table_graph.tables_text(GRAPH))
    assert names == ["addresses", "customers", "tax_rates"]


def test_relationships_text_keeps_both_join_paths_with_columns() -> None:
    text = table_graph.relationships_text(GRAPH)
    assert text.startswith(table_graph.RELATIONSHIPS_HEADER)
    assert text.endswith(
        "customers.billing_address_id -> addresses.id\n"
        "customers.installation_address_id -> addresses.id"
    )


def test_no_edges_gives_an_empty_text() -> None:
    assert table_graph.relationships_text({"nodes": [], "edges": []}) == ""
