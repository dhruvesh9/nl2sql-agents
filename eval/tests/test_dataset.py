"""Checks of the dataset file. A wrong gold answer would punish a correct system.

We compare the file with the real sample schema in database/init/01_schema.sql
and with the runbook files of knowledge-service.
"""

import re
from pathlib import Path

import pytest

import dataset

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = ROOT / "database" / "init" / "01_schema.sql"
RUNBOOK_DIR = ROOT / "knowledge-service" / "knowledge_base" / "runbooks"

# Links that are not foreign keys. The runbook usage_subscriptions_link describes this one.
LINKS_WITHOUT_FOREIGN_KEY = {frozenset({"usage_records", "subscriptions"})}
DATA_CATEGORIES = {"simple", "runbook", "payments", "devices", "support"}


def read_schema() -> tuple[set[str], set[frozenset[str]]]:
    """Return the table names and the foreign key links of the sample schema."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    tables: set[str] = set()
    links: set[frozenset[str]] = set()
    for match in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, flags=re.DOTALL):
        table, body = match.groups()
        tables.add(table)
        links |= {frozenset({table, ref}) for ref in re.findall(r"REFERENCES (\w+) \(", body)}
    return tables, links


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


ROWS = dataset.load_questions()
DATA_ROWS = [row for row in ROWS if not dataset.expects_refusal(row)]


def test_the_schema_file_was_read() -> None:
    tables, links = read_schema()
    # A broken pattern would give an empty schema, and then every other test here would pass.
    assert len(tables) >= 20
    assert frozenset({"orders", "accounts"}) in links


def test_ids_and_questions_are_unique_and_not_empty() -> None:
    assert len({row["id"] for row in ROWS}) == len(ROWS)
    questions = [row["question"].strip().lower() for row in ROWS]
    assert all(questions)
    assert len(set(questions)) == len(questions)


def test_every_row_has_a_known_split_and_category() -> None:
    for row in ROWS:
        assert row["split"] in dataset.SPLITS, row["id"]
        assert row["category"] in DATA_CATEGORIES | dataset.REFUSE_CATEGORIES, row["id"]


def test_both_splits_and_every_refusal_category_exist() -> None:
    assert {row["split"] for row in ROWS} == dataset.SPLITS
    assert {row["category"] for row in ROWS} >= dataset.REFUSE_CATEGORIES


def test_data_questions_have_gold_tables_and_refusals_have_none() -> None:
    assert all(row["gold_tables"] for row in DATA_ROWS)
    refusals = [row for row in ROWS if dataset.expects_refusal(row)]
    assert not any(row["gold_tables"] or row["gold_sql"] for row in refusals)


def test_gold_tables_exist_once_in_the_schema() -> None:
    tables, _ = read_schema()
    for row in DATA_ROWS:
        assert set(row["gold_tables"]) <= tables, row["id"]
        assert len(row["gold_tables"]) == len(set(row["gold_tables"])), row["id"]


def test_gold_runbooks_exist() -> None:
    names = {path.stem for path in RUNBOOK_DIR.glob("*.md")}
    assert names  # a wrong folder would make the next check pass for nothing
    for row in ROWS:
        assert set(row["gold_runbooks"]) <= names, row["id"]


def test_gold_tables_form_one_join_path() -> None:
    # If the gold tables are not connected, no SQL can join them. The row is wrong.
    _, foreign_keys = read_schema()
    links = foreign_keys | LINKS_WITHOUT_FOREIGN_KEY
    for row in DATA_ROWS:
        assert is_connected(row["gold_tables"], links), f"{row['id']}: {row['gold_tables']}"


def test_the_connection_check_finds_a_gap() -> None:
    # Proof that the check above can fail: customers and invoices need accounts between them.
    _, links = read_schema()
    assert not is_connected(["customers", "invoices"], links)
    assert is_connected(["customers", "accounts", "invoices"], links)


@pytest.mark.parametrize("row", [row for row in ROWS if row["gold_sql"]], ids=lambda row: row["id"])
def test_gold_sql_is_one_select(row: dict) -> None:
    sql = row["gold_sql"].strip().rstrip(";").lower()
    assert sql.startswith(("select", "with"))
    assert ";" not in sql
