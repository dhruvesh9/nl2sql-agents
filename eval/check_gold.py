"""Runs every gold SQL against db-service and prints the row count. Run it: make eval-check

Eval step: dataset quality. A gold SQL that fails, or gives 0 rows, makes the eval wrong:
a system that returns nothing would then "match". Fix the gold SQL or the question.
"""

import os
import sys

import httpx

import dataset

DB_SERVICE_URL = os.environ.get("DB_SERVICE_URL", "http://localhost:8001")


def main() -> int:
    problems = 0
    for row in dataset.load_questions():
        if not row["gold_sql"]:
            continue
        response = httpx.post(
            f"{DB_SERVICE_URL}/query", json={"sql": row["gold_sql"], "max_rows": 1000}, timeout=30
        )
        if response.status_code != 200:
            print(f"{row['id']}  ERROR  {response.text[:150]}")
            problems += 1
            continue
        count = response.json()["row_count"]
        flag = "" if count else "  <- 0 rows: weak test"
        problems += not count
        print(f"{row['id']}  {count:>4} rows{flag}")
    print(f"\n{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
