"""Tests for the table graph: build_graph, POST /generate, and GET /graph.

A fake catalog replaces db-service, so db-service does not need to run.
"""

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from networkx.readwrite import json_graph

from app import graph_builder


def table(name: Any, description: Any = "", **extra: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "foreign_keys": [],
    } | extra


def fk(columns: list[str], ref_table: str) -> dict[str, Any]:
    return {"columns": columns, "ref_table": ref_table, "ref_columns": ["id"]}


CATALOG = {
    "dialect": "postgresql",
    "tables": [
        # customers comes BEFORE addresses: an edge may point to a table that comes later.
        table(
            "customers",
            "People who buy.",
            foreign_keys=[
                fk(["billing_address_id"], "addresses"),
                fk(["installation_address_id"], "addresses"),
            ],
        ),
        table("addresses", "Postal addresses."),
    ],
}


@pytest.fixture
def fake_catalog(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    catalog = json.loads(json.dumps(CATALOG))  # a deep copy, so a test can change it
    monkeypatch.setattr(graph_builder, "fetch_catalog", lambda: catalog)
    return catalog


def test_two_foreign_keys_to_the_same_table_give_two_edges() -> None:
    graph, warnings = graph_builder.build_graph(CATALOG)
    assert graph.number_of_edges("customers", "addresses") == 2
    keys = sorted(key for _, _, key in graph.edges(keys=True))
    assert keys == ["billing_address_id", "installation_address_id"]
    assert warnings == []


@pytest.mark.parametrize(("raw", "clean"), [(None, ""), ("   ", ""), (5, ""), (" A\n  b ", "A b")])
def test_clean_text_handles_missing_and_messy_comments(raw: Any, clean: str) -> None:
    assert graph_builder.clean_text(raw) == clean


def test_a_table_without_a_comment_is_kept_and_reported_once() -> None:
    catalog = {"tables": [table("a", None), table("b", "  "), table("c", "C table")]}
    graph, warnings = graph_builder.build_graph(catalog)
    assert "description" not in graph.nodes["a"]  # only the id, no empty field
    assert warnings == ["2 tables have no comment: a, b"]


def test_an_edge_holds_only_the_tables_and_the_columns() -> None:
    graph, _ = graph_builder.build_graph(CATALOG)
    edge = graph.get_edge_data("customers", "addresses", key="billing_address_id")
    assert edge == {"columns": ["billing_address_id"], "ref_columns": ["id"]}


def test_the_graph_holds_no_columns() -> None:
    # Columns come live from /schema. In the graph they would only make the prompt bigger.
    catalog = {"tables": [table("subs", "S", column_descriptions={"msisdn": "Phone number"})]}
    graph, _ = graph_builder.build_graph(catalog)
    assert graph.nodes["subs"] == {"description": "S"}


def test_bad_tables_are_skipped_with_a_warning() -> None:
    catalog = {
        "tables": [
            table("a", "first"),
            table("a", "second copy"),
            table(None, "no name"),
            table("b", "B", foreign_keys=[fk(["x_id"], "other_schema_table")]),
        ]
    }
    graph, warnings = graph_builder.build_graph(catalog)
    assert sorted(graph.nodes) == ["a", "b"]
    assert graph.nodes["a"]["description"] == "first"
    assert "other_schema_table" not in graph  # no empty node for the unknown table
    assert len(warnings) == 3


def test_an_empty_catalog_gives_an_empty_graph() -> None:
    graph, warnings = graph_builder.build_graph({})
    assert graph.number_of_nodes() == 0
    assert warnings == []


def test_generate_writes_a_file_that_networkx_can_load_again(
    client: TestClient, kb, fake_catalog: dict[str, Any]
) -> None:
    response = client.post("/generate")
    assert response.status_code == 200
    assert response.json()["tables"] == 2
    assert response.json()["foreign_keys"] == 2

    graph = json_graph.node_link_graph(json.loads((kb / "graph.json").read_text()), edges="edges")
    assert graph.is_multigraph() and graph.is_directed()
    assert graph.nodes["customers"]["description"] == "People who buy."
    assert graph.graph["generated_at"]
    assert not list(kb.glob("*.tmp"))  # the temporary file is gone after the rename


def test_get_graph_returns_the_generated_file(
    client: TestClient, kb, fake_catalog: dict[str, Any]
) -> None:
    client.post("/generate")
    body = client.get("/graph").json()
    assert {node["id"] for node in body["nodes"]} == {"customers", "addresses"}
    assert len(body["edges"]) == 2


def test_get_graph_before_generate_returns_404(client: TestClient, kb) -> None:
    response = client.get("/graph")
    assert response.status_code == 404
    assert "POST /generate" in response.json()["detail"]


def test_generate_returns_502_when_db_service_is_down(
    client: TestClient, kb, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*args: Any, **kwargs: Any) -> None:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", down)
    response = client.post("/generate")
    assert response.status_code == 502
    assert not (kb / "graph.json").exists()  # a failed run never leaves a broken file
