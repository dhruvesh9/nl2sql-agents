"""Eval for agent 2 (Table Classifier). It scores the tables that the agent selects.

It sends each question in ground_truth/table_classifier.csv to POST /analyze of agent-service.
/analyze runs step 1 (Query Analyzer) and then step 2 (Table Classifier).
Run it with: make eval-tables   (agent-service must run on port 8000, see "make agent")

We compare the selected table names with expected_tables. The names must be exactly equal.
Each question gets one status:
- PASS: the selected tables are exactly the expected tables.
- WARN: all expected tables are selected, and some extra tables too. This counts as a success.
- FAIL: at least one expected table is missing.
The headline number is TABLE ACCURACY = (PASS + WARN) / all questions.
We go to the next agent only when it is 90% or more. We also watch the WARN count,
because extra tables make the next agents slower and less exact.

Logs: every question gets a block in the console AND in results/table_classifier_<time>.log.
Step 1 output is logged for context only. It is not scored here.
"""

import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8000")
GROUND_TRUTH_FILE = Path(__file__).parent / "ground_truth" / "table_classifier.csv"
RESULTS_DIR = Path(__file__).parent / "results"
TARGET_PERCENT = 90
TIMEOUT_SECONDS = 120

logger = logging.getLogger("eval")


def setup_logging(run_name: str) -> Path:
    """Log to the console and to a file. Return the log file path."""
    RESULTS_DIR.mkdir(exist_ok=True)
    log_path = RESULTS_DIR / f"{run_name}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # hide one line per HTTP call
    return log_path


def split_list(text: str) -> list[str]:
    """Turn "a;b" into ["a", "b"]. An empty text gives an empty list."""
    return [item for item in text.split(";") if item]


def ask_analyze(client: httpx.Client, question: str) -> dict:
    """Call POST /analyze. Return the JSON answer."""
    response = client.post(f"{AGENT_URL}/analyze", json={"question": question})
    response.raise_for_status()
    return response.json()


def table_status(missing: list[str], extra: list[str]) -> str:
    """Return PASS, WARN, or FAIL. A missing table is a failure. An extra table is a warning."""
    if missing:
        return "FAIL"
    return "WARN" if extra else "PASS"


def score_question(row: dict, answer: dict) -> dict:
    """Compare the selected tables with the expected tables."""
    expected = set(split_list(row["expected_tables"]))
    got = set(answer["selected_tables"])
    missing = sorted(expected - got)
    extra = sorted(got - expected)
    return {
        "table_status": table_status(missing, extra),
        "got_tables": ";".join(sorted(got)),
        "missing_tables": ";".join(missing),
        "extra_tables": ";".join(extra),
        "reason": answer["reason"],
    }


def percent(count: int, total: int) -> float:
    return 100 * count / total if total else 0.0


def log_question(row: dict, answer: dict, result: dict) -> None:
    """Write one readable block for one question. This is the main tool to find prompt problems."""
    requirements = answer["requirements"]
    times = {entry["name"]: entry["elapsed_ms"] for entry in answer["trace"]}

    logger.info("[%s] (%s) %s", row["id"], row["category"], row["question"])
    logger.info(
        "   step 1 query_analyzer  %5d ms | intent=%s | runbooks=%s",
        times.get("query_analyzer", 0),
        requirements.get("intent"),
        requirements.get("runbook_candidates"),
    )
    logger.info(
        "      fields=%s filters=%s aggregations=%s concepts=%s",
        requirements.get("requested_fields"),
        requirements.get("filters"),
        requirements.get("aggregations"),
        requirements.get("business_concepts"),
    )
    if "table_classifier" not in times:
        logger.info("   step 2 table_classifier did not run (step 1 said: %s)", requirements.get("intent"))
    else:
        logger.info(
            "   step 2 table_classifier %5d ms | tables=%s",
            times["table_classifier"],
            answer["selected_tables"],
        )
        logger.info("      reason: %s", answer["reason"])
    logger.info("   expected tables: %s", split_list(row["expected_tables"]))

    logger.info("   TABLES: %s", result["table_status"])
    if result["missing_tables"]:
        logger.info("      missing: %s", split_list(result["missing_tables"]))
    if result["extra_tables"]:
        logger.info("      extra:   %s", split_list(result["extra_tables"]))
    logger.info("")


def run_all(rows: list[dict]) -> list[dict]:
    """Ask every question. Return one result dict for each question."""
    results = []
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        for number, row in enumerate(rows, 1):
            logger.info("===== question %d of %d =====", number, len(rows))
            try:
                answer = ask_analyze(client, row["question"])
                result = {**row, **score_question(row, answer)}
                log_question(row, answer, result)
            except httpx.ConnectError:
                sys.exit(f"Cannot connect to {AGENT_URL}. Is agent-service running? (make agent)")
            except httpx.HTTPError as error:
                # One bad answer must not stop the whole run. It counts as a failure.
                logger.info("[%s] %s\n   ERROR: %s\n", row["id"], row["question"], str(error)[:300])
                result = {**row, "table_status": "FAIL", "extra_tables": "", "reason": str(error)[:200]}
            results.append(result)
    return results


def print_summary(results: list[dict]) -> float:
    """Log the accuracy numbers. Return the table accuracy in percent."""
    total = len(results)
    statuses = ("PASS", "WARN", "FAIL")
    counts = {status: sum(r["table_status"] == status for r in results) for status in statuses}
    table_pct = percent(counts["PASS"] + counts["WARN"], total)

    logger.info("===== Summary =====")
    logger.info("Questions:        %d", total)
    logger.info("TABLE ACCURACY:   %.1f%%   (PASS + WARN, target %d%%)", table_pct, TARGET_PERCENT)
    logger.info("  PASS (exact):   %d", counts["PASS"])
    logger.info("  WARN (extra):   %d", counts["WARN"])
    logger.info("  FAIL (missing): %d", counts["FAIL"])

    warned = [r for r in results if r["table_status"] == "WARN"]
    if warned:
        extras = sum(len(split_list(r["extra_tables"])) for r in warned)
        logger.info("  average extra tables in a WARN: %.1f", extras / len(warned))
    for status in ("FAIL", "WARN"):
        ids = [r["id"] for r in results if r["table_status"] == status]
        logger.info("%s questions: %s", status, ", ".join(ids) if ids else "none")

    by_category: dict[str, list[str]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r["table_status"])
    for category, found in by_category.items():
        logger.info(
            "  %-10s PASS %d, WARN %d, FAIL %d",
            category,
            found.count("PASS"),
            found.count("WARN"),
            found.count("FAIL"),
        )

    logger.info("GO to the next agent." if table_pct >= TARGET_PERCENT else "NOT YET. Improve the prompts.")
    return table_pct


def save_results(results: list[dict], path: Path) -> None:
    columns = list(dict.fromkeys(key for result in results for key in result))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)


def main() -> None:
    # EVAL_LABEL names the experiment in the file names, for example EVAL_LABEL=plain.
    label = os.environ.get("EVAL_LABEL", "")
    run_name = f"table_classifier_{label + '_' if label else ''}{datetime.now():%Y%m%d_%H%M%S}"
    log_path = setup_logging(run_name)
    with GROUND_TRUTH_FILE.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    logger.info("Table Classifier eval: %d questions, agent-service at %s", len(rows), AGENT_URL)

    results = run_all(rows)
    table_pct = print_summary(results)

    csv_path = RESULTS_DIR / f"{run_name}.csv"
    save_results(results, csv_path)
    logger.info("Results file: %s", csv_path)
    logger.info("Log file:     %s", log_path)
    sys.exit(0 if table_pct >= TARGET_PERCENT else 1)


if __name__ == "__main__":
    main()
