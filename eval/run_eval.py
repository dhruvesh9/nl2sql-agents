"""Runs the eval and prints the report. This is the entry point: make eval.

Run it from the agent-service folder with its venv, because levels 1 and 2 import the agent code
(make eval does this). Start db-service, knowledge-service, and agent-service first.

Examples:
    make eval                                   # all levels, dev split, one attempt
    make eval ARGS="--level classifier --limit 5"
    make eval ARGS="--repeat 3"                 # run each question 3 times, report the spread
    make eval ARGS="--endpoint ask"             # level 3 against the full pipeline
    make eval ARGS="--baseline results/run_X/summary.json"   # exit 1 if a number fell

Use the dev split while you change prompts. Use the test split only to report a number.
"""

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dataset
import levels
import report
import usage

logger = logging.getLogger("eval")
LEVELS = ["classifier", "sql", "system"]


def grade(run: Callable[[], dict[str, Any]], row: dict, level: str, attempt: int) -> dict[str, Any]:
    """Run one question. Add the time and tokens. Turn an exception into an ERROR result."""
    usage.reset()
    start = time.perf_counter()
    try:
        result = run()
    except Exception as error:  # noqa: BLE001 - one broken question must not stop the whole run
        result = {"status": "ERROR", "detail": f"{type(error).__name__}: {error}"}
    result["elapsed_ms"] = int((time.perf_counter() - start) * 1000)
    result["tokens"] = usage.read()["tokens"]
    return {
        "id": row["id"],
        "category": row["category"],
        "level": level,
        "attempt": attempt,
    } | result


def run_attempt(
    rows: list[dict], level_names: list[str], attempt: int, endpoint: str, gold_cache: dict
) -> list[dict]:
    """Grade every question on every selected level, one time."""
    analyses: dict[str, dict] = {}  # the Query Analyzer runs once per question and attempt
    details: list[dict] = []
    for row in rows:
        runners = {
            "classifier": lambda row=row: levels.run_classifier(row, analyses, gold_cache),
            "sql": lambda row=row: levels.run_sql_generator(row, analyses, gold_cache),
            "system": lambda row=row: levels.run_system(row, endpoint, gold_cache),
        }
        for level in level_names:
            result = grade(runners[level], row, level, attempt)
            details.append(result)
            if result["status"] not in ("PASS", "WARN", "MATCH", "REFUSED", "SKIP"):
                logger.info(
                    "%s %-10s %-9s %s", row["id"], level, result["status"], result["detail"]
                )
    return details


def agent_models() -> dict[str, str]:
    """The model of each agent, for the run record. Empty if the agent code cannot be imported."""
    try:
        from app import llm
    except ImportError:
        return {}
    agents = ["query_analyzer", "table_classifier", "sql_generator"]
    return {name: llm.options_for(name)["model"] for name in agents}


def format_metric(value: dict) -> str:
    text = f"{value['mean']:5.1f}%"
    if value["min"] != value["max"]:
        text += f"  (min {value['min']:.1f}, max {value['max']:.1f})"
    return text


def print_summary(summary: dict) -> None:
    meta = summary["meta"]
    print(
        f"\ncommit {meta['git_commit']}{'+dirty' if meta['git_dirty'] else ''}"
        f"  prompts {meta['prompt_version']}  split {meta['split']}  repeat {meta['repeat']}"
    )
    for level, data in summary["levels"].items():
        print(f"\n== {level}: {data['questions']} questions, {data['skipped']} skipped")
        for name, value in data["metrics"].items():
            print(f"  {name:<20} {format_metric(value)}")
        latency = data["latency_ms"]
        print(f"  latency p50 {latency['p50']:.0f} ms, p95 {latency['p95']:.0f} ms")
        if data["tokens_per_question"]:
            print(f"  tokens per question  {data['tokens_per_question']:.0f}")
        if data["unstable_questions"]:
            print(f"  unstable (result changed between attempts): {data['unstable_questions']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NL-to-SQL dev eval")
    parser.add_argument("--level", choices=[*LEVELS, "all"], default="all")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--repeat", type=int, default=1, help="attempts per question")
    parser.add_argument("--limit", type=int, default=None, help="only the first N questions")
    parser.add_argument("--endpoint", choices=["ask-quick", "ask"], default="ask-quick")
    parser.add_argument("--baseline", help="summary.json of an earlier run")
    parser.add_argument(
        "--max-drop", type=float, default=5.0, help="allowed fall in percent points"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("httpx", "together"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    usage.start_counting()

    rows = dataset.load_questions(args.split, args.limit)
    level_names = LEVELS if args.level == "all" else [args.level]
    logger.info("%d questions, levels %s, %d attempt(s)", len(rows), level_names, args.repeat)

    gold_cache: dict[str, dict] = {}
    details: list[dict] = []
    for attempt in range(1, args.repeat + 1):
        logger.info("attempt %d of %d", attempt, args.repeat)
        details += run_attempt(rows, level_names, attempt, args.endpoint, gold_cache)

    summary = {
        "meta": report.run_meta(args.split, args.repeat, args.endpoint, agent_models()),
        "levels": {
            level: report.summarize_level(level, [d for d in details if d["level"] == level])
            for level in level_names
        },
    }
    print_summary(summary)
    print(f"\nsaved: {report.save_run(summary, details)}")

    if args.baseline:
        # make eval runs in agent-service/, so also accept a path from the project root.
        baseline = Path(args.baseline)
        if not baseline.exists():
            baseline = Path(__file__).resolve().parents[1] / args.baseline
        with baseline.open(encoding="utf-8") as file:
            problems = report.regressions(summary, json.load(file), args.max_drop)
        if problems:
            print("\nREGRESSION:", *problems, sep="\n  ")
            return 1
        print("\nno regression against the baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
