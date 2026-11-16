"""Tests for foreign key expansion with a small fake graph. They need no database."""

from app.schema_reader import find_related_tables

# customers <-> orders <-> order_items, and a cycle a <-> b <-> c <-> a
GRAPH = {
    "customers": {"orders"},
    "orders": {"customers", "order_items"},
    "order_items": {"orders"},
    "a": {"b", "c"},
    "b": {"a", "c"},
    "c": {"a", "b"},
    "self_link": {"self_link"},
}


def test_depth_zero_returns_nothing() -> None:
    assert find_related_tables(["orders"], 0, GRAPH) == []


def test_negative_depth_returns_nothing() -> None:
    assert find_related_tables(["orders"], -3, GRAPH) == []


def test_depth_one_returns_direct_neighbours() -> None:
    assert find_related_tables(["orders"], 1, GRAPH) == ["customers", "order_items"]


def test_depth_two_goes_one_step_further() -> None:
    assert find_related_tables(["customers"], 1, GRAPH) == ["orders"]
    assert find_related_tables(["customers"], 2, GRAPH) == ["orders", "order_items"]


def test_start_tables_are_not_in_the_result() -> None:
    result = find_related_tables(["customers", "orders"], 2, GRAPH)
    assert result == ["order_items"]


def test_cycle_does_not_run_forever() -> None:
    assert find_related_tables(["a"], 10, GRAPH) == ["b", "c"]


def test_table_that_links_to_itself() -> None:
    assert find_related_tables(["self_link"], 3, GRAPH) == []


def test_start_table_missing_from_graph() -> None:
    assert find_related_tables(["unknown"], 2, GRAPH) == []
