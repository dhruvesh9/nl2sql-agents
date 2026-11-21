"""Reads table details from the live database and expands foreign keys.

Pipeline step: 3 (Live Schema Discovery), db-service side. Used by POST /schema.
"""

from sqlalchemy import inspect

from app.config import settings
from app.database import engine, get_dialect
from app.models import (
    CatalogResponse,
    CatalogTable,
    ColumnInfo,
    ForeignKeyInfo,
    SchemaResponse,
    TableInfo,
)


def read_table(table_name: str) -> TableInfo | None:
    """Read one table with SQLAlchemy inspect(engine).

    Return None if the table does not exist.
    Example: read_table("orders") -> TableInfo(name="orders", ...); read_table("nope") -> None
    """
    inspector = inspect(engine)

    if not inspector.has_table(table_name):
        return None

    columns = []
    for column in inspector.get_columns(table_name):
        # str() turns the SQLAlchemy type object into text, for example "VARCHAR(20)".
        columns.append(
            ColumnInfo(
                name=column["name"],
                type=str(column["type"]),
                nullable=column["nullable"],
                description=column.get("comment"),  # None when the column has no comment
            )
        )

    foreign_keys = []
    for item in inspector.get_foreign_keys(table_name):
        foreign_keys.append(
            ForeignKeyInfo(
                columns=item["constrained_columns"],
                ref_table=item["referred_table"],
                ref_columns=item["referred_columns"],
            )
        )

    return TableInfo(
        name=table_name,
        description=inspector.get_table_comment(table_name)["text"],
        primary_key=inspector.get_pk_constraint(table_name)["constrained_columns"],
        columns=columns,
        foreign_keys=foreign_keys,
    )


def build_fk_graph() -> dict[str, set[str]]:
    """Build a map: table name -> names of the tables linked to it by a foreign key.

    A link works in both directions. If orders points to customers, then
    orders is a neighbour of customers, and customers is a neighbour of orders.

    Example: {"orders": {"customers"}, "customers": {"orders"}}
    """
    inspector = inspect(engine)
    graph: dict[str, set[str]] = {}

    for table_name in inspector.get_table_names():
        graph.setdefault(table_name, set())
        for foreign_key in inspector.get_foreign_keys(table_name):
            other_table = foreign_key["referred_table"]
            graph[table_name].add(other_table)
            graph.setdefault(other_table, set()).add(table_name)

    return graph


def find_related_tables(
    start_tables: list[str], fk_depth: int, graph: dict[str, set[str]]
) -> list[str]:
    """Find tables linked by foreign keys, up to fk_depth steps. Use breadth-first search.

    We go one level at a time. Level 1 holds the neighbours of the start tables.
    Level 2 holds the neighbours of level 1, and so on.
    The visited set stops us from going in circles. It also keeps the start tables out of the result.

    Example:
        graph = {"orders": {"customers", "order_items"}, "customers": {"orders"}}
        find_related_tables(["orders"], 1, graph) -> ["customers", "order_items"]
    """
    visited = set(start_tables)
    current_level = list(start_tables)
    found: list[str] = []

    for _ in range(fk_depth):  # range() of 0 or a negative number does nothing
        next_level = []
        for table in current_level:
            # sorted() makes the result the same on every run
            for neighbour in sorted(graph.get(table, set())):
                if neighbour not in visited:
                    visited.add(neighbour)
                    found.append(neighbour)
                    next_level.append(neighbour)
        current_level = next_level

    return found


def get_schema(tables: list[str], fk_depth: int) -> SchemaResponse:
    """Build the full /schema response: tables, discovered_tables, and not_found.

    The discovered tables (found by foreign key expansion) are also read in full
    and added to "tables", so the caller needs only one request.
    """
    # dict.fromkeys removes duplicates and keeps the order of the request. A set would lose it.
    requested = list(dict.fromkeys(tables))
    depth = max(0, min(fk_depth, settings.max_fk_depth))

    table_infos = []
    not_found = []
    for name in requested:
        table_info = read_table(name)
        if table_info is None:
            not_found.append(name)
        else:
            table_infos.append(table_info)

    discovered: list[str] = []
    if depth > 0 and table_infos:
        found_names = [info.name for info in table_infos]
        discovered = find_related_tables(found_names, depth, build_fk_graph())
        for name in discovered:
            extra_info = read_table(name)
            if extra_info is not None:
                table_infos.append(extra_info)

    return SchemaResponse(
        dialect=get_dialect(),
        tables=table_infos,
        discovered_tables=discovered,
        not_found=not_found,
    )


def get_catalog() -> CatalogResponse:
    """Read every table in the database. knowledge-service uses it to build the table graph.

    Each get_multi_* call reads the whole schema in ONE query. read_table() sends about
    5 queries per table, so 1000 tables would need about 5000 queries.
    """
    inspector = inspect(engine)
    comments = inspector.get_multi_table_comment()
    columns = inspector.get_multi_columns()
    foreign_keys = inspector.get_multi_foreign_keys()

    tables = []
    # Each key is (schema, table_name). The schema is None for the default schema.
    # Sorting by name makes the answer the same on every run.
    for key in sorted(columns, key=lambda item: item[1]):
        tables.append(
            CatalogTable(
                name=key[1],
                description=comments.get(key, {}).get("text"),
                foreign_keys=[
                    ForeignKeyInfo(
                        columns=item["constrained_columns"],
                        ref_table=item["referred_table"],
                        ref_columns=item["referred_columns"],
                    )
                    for item in foreign_keys.get(key, [])
                ],
            )
        )
    return CatalogResponse(dialect=get_dialect(), tables=tables)
