# eval: accuracy tests for the agents

This is the third project. It does not use the agent code. It calls agent-service over HTTP.
Each agent has its own ground truth file in `ground_truth/` and its own runner script.

| Agent | Ground truth | Runner | Command |
|---|---|---|---|
| 2: Table Classifier | `ground_truth/table_classifier.csv` | `run_table_classifier.py` | `make eval-tables` |

Later agents get their own pair of files, for example `ground_truth/sql_generator.csv`.
Chit-chat and intent checks (agent 1) belong in a future `ground_truth/query_analyzer.csv`.

Rule for the project: do not build the next agent until TABLE ACCURACY is 90% or more.

## Run the Table Classifier eval

Terminal 1 and 2 (from the project root):
```bash
make knowledge
make agent
```
Terminal 3:
```bash
make eval-tables
```
The run takes about 3 minutes (30 questions, 2 LLM calls each, because `/analyze` also runs step 1).

## What you see

- Console and `results/table_classifier_<time>.log`: one block for each question. It shows what step 1
  returned, what step 2 returned, the reason of the LLM, the expected tables, and the status.
- `results/table_classifier_<time>.csv`: the same data as a table. Filter by `table_status`.
- Terminal 1 (agent-service): each LLM call (model, time, tokens) and the output of each step.

## ground_truth/table_classifier.csv

| Column | Meaning |
|---|---|
| `id`, `category` | Question number and group (simple, runbook, payments, devices, support). |
| `question` | The text that we send. |
| `expected_tables` | Tables that the SQL needs, including the tables on the join path. Separated by `;`. |

## Scoring

The eval measures one thing: does the Table Classifier select the right tables?
Table names must be exactly equal. Each question gets one status:

| Status | Meaning | Counts as success? |
|---|---|---|
| PASS | The selected tables are exactly the expected tables. | Yes |
| WARN | All expected tables are selected, plus extra tables. | Yes |
| FAIL | At least one expected table is missing. | No |

TABLE ACCURACY = (PASS + WARN) / all questions. The target is 90%. Watch the WARN count too:
extra tables make the next agents slower and less exact.

## Change things

- Run against another URL: `AGENT_URL=http://host:8000 make eval-tables`.
- Add a question: add a line to the CSV. Use the tables that a correct SQL needs, including the join path.
