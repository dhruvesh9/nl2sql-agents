"""Checks of the ground truth file. A wrong expected answer would punish a correct classifier.

We compare the file with the real sample schema in database/init/01_schema.sql.
"""

import csv
import re
from pathlib import Path

import pytest

import run_table_classifier as ev

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "database" / "init" / "01_schema.sql"

# Links that are not foreign keys. The runbook usage_subscriptions_link describes this one.
LINKS_WITHOUT_FOREIGN_KEY = {frozenset({"usage_records", "subscriptions"})}


def read_schema() -> tuple[set[str], set[frozenset[str]]]:
    """Return the table names and the foreign key links of the sample schema."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    tables: set[str] = set()
    links: set[frozenset[str]] = set()
    for match in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, flags=re.DOTALL):
        table, body = match.groups()
        tables.add(table)
        for referenced in re.findall(r"REFERENCES (\w+) \(", body):
            links.add(frozenset({table, referenced}))
    return tables, links


def read_rows() -> list[dict]:
    with ev.GROUND_TRUTH_FILE.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def is_connected(tables: list[str], links: set[frozenset[str]]) -> bool:
    """True when the tables form one connected group. Only links between these tables count."""
    group = set(tables)
    inside = {link for link in links if link <= group}
    reached = {tables[0]}
    changed = True
    while changed:
        changed = False
        for link in inside:
            if link & reached and not link <= reached:
                reached |= link
                changed = True
    return reached == group


def test_the_schema_file_was_read() -> None:
    tables, links = read_schema()
    # A broken pattern would give an empty schema, and then every other test here would pass.
    assert len(tables) >= 20
    assert frozenset({"orders", "accounts"}) in links


def test_ids_are_unique_and_questions_are_not_empty() -> None:
    rows = read_rows()
    ids = [row["id"] for row in rows]
    questions = [row["question"].strip().lower() for row in rows]
    assert len(set(ids)) == len(ids)
    assert all(questions)
    assert len(set(questions)) == len(questions)


def test_every_question_expects_at_least_one_table() -> None:
    # A question that needs no table (a greeting) belongs to the Query Analyzer eval, not here.
    assert all(ev.split_list(row["expected_tables"]) for row in read_rows())


def test_expected_tables_exist_in_the_schema() -> None:
    tables, _ = read_schema()
    for row in read_rows():
        unknown = set(ev.split_list(row["expected_tables"])) - tables
        assert not unknown, f"{row['id']} expects tables that do not exist: {unknown}"


def test_no_table_is_listed_twice_in_one_row() -> None:
    for row in read_rows():
        names = ev.split_list(row["expected_tables"])
        assert len(names) == len(set(names)), row["id"]


def test_expected_tables_form_one_join_path() -> None:
    # If the expected tables are not connected, no SQL can join them. The row is wrong.
    _, foreign_keys = read_schema()
    links = foreign_keys | LINKS_WITHOUT_FOREIGN_KEY
    for row in read_rows():
        names = ev.split_list(row["expected_tables"])
        assert is_connected(names, links), f"{row['id']} is not one join path: {names}"


def test_the_connection_check_finds_a_gap() -> None:
    # Proof that the check above can fail: customers and invoices need accounts between them.
    _, links = read_schema()
    assert not is_connected(["customers", "invoices"], links)
    assert is_connected(["customers", "accounts", "invoices"], links)


@pytest.mark.parametrize("category", ["simple", "runbook", "payments", "devices", "support"])
def test_each_category_has_questions(category: str) -> None:
    assert any(row["category"] == category for row in read_rows())
