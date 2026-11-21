"""Turns the raw results of a run into numbers (summary), saves the run, and checks a baseline.

Eval step: reporting. Every metric is a percent from 0 to 100.
With --repeat N each metric is computed per attempt, and we keep the mean, min and max.
The spread shows how stable the system is, because temperature 0 is not fully repeatable.
"""

import hashlib
import json
import statistics
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import scoring

RESULTS_DIR = Path(__file__).parent / "results"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "agent-service" / "app" / "prompts"

# The numbers that a regression gate watches. All are "higher is better".
HEADLINE = {
    "classifier": ["table_accuracy", "table_recall"],
    "sql": ["execution_accuracy"],
    "system": ["execution_accuracy", "refusal_accuracy"],
}


def pct(flags: list[bool]) -> float | None:
    """Percent of True values. None when the list is empty (the metric does not apply)."""
    return 100 * sum(flags) / len(flags) if flags else None


def mean(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return statistics.fmean(known) if known else None


def metrics_of_attempt(level: str, results: list[dict]) -> dict[str, float | None]:
    """Compute the metrics of one level for one attempt. SKIP results do not count."""
    graded = [result for result in results if result["status"] != "SKIP"]
    if level == "classifier":
        return {
            "table_accuracy": pct([r["status"] in ("PASS", "WARN") for r in graded]),
            "exact_tables": pct([r["status"] == "PASS" for r in graded]),
            "table_recall": mean([r.get("recall", 0.0) for r in graded]),
            "table_precision": mean([r.get("precision", 0.0) for r in graded]),
            "runbook_recall": mean([r.get("runbook_recall") for r in graded]),
        }
    if level == "sql":
        return {
            "execution_accuracy": pct([r["status"] == "MATCH" for r in graded]),
            "valid_sql": pct([r["status"] != "ERROR" for r in graded]),
        }
    answers = [r for r in graded if r.get("kind") == "answer"]
    refusals = [r for r in graded if r.get("kind") == "refuse"]
    return {
        "execution_accuracy": pct([r["status"] == "MATCH" for r in answers]),
        "answered": pct([r["status"] in ("MATCH", "MISMATCH") for r in answers]),
        "refusal_accuracy": pct([r["status"] == "REFUSED" for r in refusals]),
    }


def summarize_level(level: str, results: list[dict]) -> dict[str, Any]:
    """Return the metrics (mean, min, max over attempts), latency, tokens, and unstable questions."""
    attempts = sorted({result["attempt"] for result in results})
    per_attempt = [
        metrics_of_attempt(level, [r for r in results if r["attempt"] == attempt])
        for attempt in attempts
    ]
    metrics: dict[str, Any] = {}
    for name in per_attempt[0]:
        values = [m[name] for m in per_attempt if m[name] is not None]
        if values:
            metrics[name] = {"mean": mean(values), "min": min(values), "max": max(values)}
    graded = [r for r in results if r["status"] != "SKIP"]
    times = [r["elapsed_ms"] for r in graded]
    by_question: dict[str, set[str]] = {}
    for result in graded:
        by_question.setdefault(result["id"], set()).add(result["status"])
    return {
        "questions": len(by_question),
        "attempts": len(attempts),
        "skipped": len({r["id"] for r in results} - set(by_question)),
        "metrics": metrics,
        "latency_ms": {"p50": scoring.percentile(times, 50), "p95": scoring.percentile(times, 95)},
        "tokens_per_question": mean([r["tokens"] for r in graded if r.get("tokens")]),
        "unstable_questions": sorted(q for q, seen in by_question.items() if len(seen) > 1),
    }


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def prompt_version() -> str:
    """A short hash of all prompt files. A prompt change gives a new value, so runs stay comparable."""
    digest = hashlib.sha256()
    for path in sorted(PROMPTS_DIR.glob("*.md")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def run_meta(split: str, repeat: int, endpoint: str, models: dict[str, str]) -> dict[str, Any]:
    """Everything that is needed to repeat the run later."""
    return {
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "prompt_version": prompt_version(),
        "split": split,
        "repeat": repeat,
        "endpoint": endpoint,
        "models": models,
    }


def save_run(summary: dict, details: list[dict]) -> Path:
    """Write summary.json and details.jsonl into results/run_<time>/. Return the folder."""
    folder = RESULTS_DIR / f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [json.dumps(detail, ensure_ascii=False) for detail in details]
    (folder / "details.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def regressions(current: dict, baseline: dict, max_drop: float) -> list[str]:
    """List the headline metrics that fell by more than max_drop percent points."""
    problems: list[str] = []
    for level, names in HEADLINE.items():
        for name in names:
            now = current["levels"].get(level, {}).get("metrics", {}).get(name)
            before = baseline["levels"].get(level, {}).get("metrics", {}).get(name)
            if now and before and before["mean"] - now["mean"] > max_drop:
                problems.append(f"{level}.{name}: {before['mean']:.1f} -> {now['mean']:.1f}")
    return problems
