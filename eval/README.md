# eval: development-time evaluation

This project measures how well the pipeline works. It has three levels.
Run it every time you change a prompt, a model, or the code. Compare the numbers before and after.

| Level | Name | What it tests | Input | Main metric |
|---|---|---|---|---|
| 1 | `classifier` | Query Analyzer + Table Classifier | The question | Table recall, runbook recall |
| 2 | `sql` | SQL Generator alone | The question, the **gold** tables, the **gold** runbooks | Execution accuracy |
| 3 | `system` | The whole pipeline (`/ask-quick` now, `/ask` later) | The question | Execution accuracy, refusal accuracy |

Why level 2 gets gold input: if it used the classifier output, a wrong table would look like an SQL error.
Each level then measures only its own agent. Level 3 shows what the errors add up to.

## Run

Start `make dbsvc`, `make knowledge`, and `make agent`. Then, from the project root:
```bash
make eval                                    # all levels, dev split, 1 attempt
make eval ARGS="--level sql"                 # one level: classifier, sql, or system
make eval ARGS="--limit 5"                   # the first 5 questions (a quick check)
make eval ARGS="--repeat 3"                  # each question 3 times: mean, min, max, unstable questions
make eval ARGS="--endpoint ask"              # level 3 against POST /ask (when it exists)
make eval ARGS="--split test"                # the held-out split. Use it to report, not to tune.
make eval ARGS="--baseline eval/results/run_X/summary.json --max-drop 5"   # exit 1 if a number fell
```
Level 3 reads `answer` and `data` from the client response. `data` (`columns`, `rows`, `truncated`) is there only when the query gave rows. That response has no SQL, so the level 3
details have no SQL. Level 2 keeps the generated SQL for debugging.

It uses the agent-service venv, because levels 1 and 2 call the agent code directly (no HTTP, so the
client response can stay small). Level 3 uses HTTP, like a real client. `AGENT_URL` changes the URL.

## The dataset: `dataset/questions.toml`

One file for all levels. The fields are in the header of the file. Each question has a `split`:
- `dev`: tune prompts on these.
- `test`: look at these rarely. The number you report comes from here.

Questions in the categories `chitchat`, `unanswerable`, and `adversarial` must be refused.
They have no gold fields. A question with no `gold_sql` is skipped in levels 2 and 3 (the report says how many).

Rules for a gold SQL: it gives one clear answer. If the question can mean two things
(for example "per customer": the id or the name?), change the question. Run `make eval-check` after a change: it runs every gold SQL and warns about 0 rows
(a system that returns nothing would then "match").
`pytest` checks that gold tables and runbooks exist and that the tables form one join path.

## Metrics (all in percent)

| Metric | Meaning |
|---|---|
| `table_recall` | Share of the gold tables that the classifier selected. The main number: a missing table is fatal. |
| `table_precision` | Share of the selected tables that are gold tables. Extra tables only cost tokens. |
| `table_accuracy` | Questions with no missing table (PASS or WARN). |
| `exact_tables` | Questions with exactly the gold tables (PASS). |
| `runbook_recall` | Share of the gold runbooks that the Query Analyzer found. |
| `execution_accuracy` | The generated SQL gives the same rows as the gold SQL. We compare rows, not SQL text. |
| `valid_sql` | The SQL ran without an error. |
| `answered` | Level 3: the system returned data (right or wrong). |
| `refusal_accuracy` | Level 3: chit-chat, unanswerable, and adversarial questions got no data. |
| latency p50 / p95 | Time per question. |
| tokens per question | Levels 1 and 2 only. Level 3 runs in another process (see Langfuse). |
| unstable questions | The result changed between attempts (`--repeat`). Temperature 0 is not fully repeatable. |

Comparing rows (`compare.py`): column names are ignored, numbers are rounded to 2 decimals,
the row order is ignored (unless `ordered = true`), and another column order is accepted.

## Results

Each run writes `results/run_<time>/`:
- `summary.json`: the numbers, and the run record: git commit (and `dirty`), a hash of the prompt files,
  the model of each agent, the split, the number of attempts. With this record you can repeat a run.
- `details.jsonl`: one line per question and attempt: status, generated SQL, the reason, time, tokens.

Failed questions are also printed during the run. `results/` is not committed.

## Files

| File | Job |
|---|---|
| `run_eval.py` | Entry point and console report |
| `levels.py` | The three level functions (one question in, one result out) |
| `dataset.py` | Loads `dataset/questions.toml` |
| `compare.py` | Execution accuracy: compares two result sets |
| `scoring.py` | Table and runbook scores, percentile |
| `report.py` | Summary, spread over attempts, saving, baseline check |
| `usage.py` | Counts LLM tokens from the agent log lines |

## Tests

`make test` runs the tests of this project. They need no running service.

## Limits (known)

- The dataset is small. Add questions where the system fails in real use. That loop makes the eval better.
- The questions run one after the other, so a full run takes a few minutes.
- Level 1 and 2 use the real Query Analyzer output. A mistake in step 1 can lower the level 2 number.
- No LLM judge. If you add one, check it against human labels first.
