# knowledge-service

This service owns the knowledge base. It runs on port 8002. It reads files and serves them.
`POST /generate` also builds `graph.json` from the live database, through db-service. It calls no LLM.
agent-service is the client. It never reads these files from disk.

## Run

```bash
make knowledge     # from the project root
```

Settings are in `.env` (copy `.env.example`). The files are in `knowledge_base/`:

| File | Content |
|---|---|
| `index.md` | Runbook names, keywords, and short descriptions. Step 1 uses it. |
| `graph.json` | Generated table graph: tables, comments, and foreign keys. Step 2 uses it. Do not edit it by hand: run `make kb-generate`. |
| `runbooks/<name>.md` | Business rules and special cases. Step 5 uses them. |

To add a runbook: add the file to `runbooks/` and add a row to `index.md`. No code change is needed.

## API

There is no authentication for now (later: Keycloak and JWT).
Each document endpoint answers with `{"content": "<Markdown text>"}`.

| Request | Answer |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /index` | The text of `index.md`. |
| `GET /runbooks/{name}` | The text of one runbook. The name has no `.md`. |
| `GET /graph` | `graph.json` as node-link JSON (`nodes`, `edges`). 404 before the first generate. |
| `POST /generate` | Builds `graph.json` again. Returns the counts and the warnings. 502 if db-service fails. |

Errors:
- 404: the file does not exist, for example an unknown runbook.
- 400: the runbook name has other characters than letters, digits, and underscores.

Example:
```bash
curl localhost:8002/runbooks/invoice_status
```

## How agent-service uses it

`agent-service/app/knowledge.py` caches each text for `KNOWLEDGE_CACHE_TTL_SECONDS` (default 300).
When a refresh fails, it uses the old copy and logs a warning. So a change in a file shows up
in the agent after the cache time, and a short outage does not stop the agent.

## The table graph (graph.json)

`POST /generate` (or `make kb-generate`) does these steps. No LLM call is made.

1. `GET /catalog` on db-service: every table with its comment and foreign keys.
2. Build a networkx `MultiDiGraph`. A node is a table. An edge is a foreign key, from the table
   that holds the key to the table it points to. A multigraph keeps two keys to the same table
   (for example `customers` -> `addresses` for billing and for installation).
3. Save it as node-link JSON. The file is written to a temporary file first and then renamed,
   so `GET /graph` never sees a half-written file.

Bad data does not stop the build. It shows up in `warnings`: tables with no comment,
a table listed twice, or a foreign key to a table that is not in the catalog (for example in another schema).

Load it in Python:
```python
import json
from networkx.readwrite import json_graph

graph = json_graph.node_link_graph(json.load(open("knowledge_base/graph.json")), edges="edges")
```

## Request ID and logs

Every request has a request ID (the `X-Request-ID` header, or a new one). It is in every log line and in the
response header. Logs are JSON, one object per line (`LOG_FORMAT=text` for a terminal). Each request writes one
`request` line with the method, path, status, and `duration_ms`.
