# knowledge-service

This service owns the knowledge base. It runs on port 8002. It only reads files and serves them.
agent-service is the client. It never reads these files from disk.

## Run

```bash
make knowledge     # from the project root
```

Settings are in `.env` (copy `.env.example`). The files are in `knowledge_base/`:

| File | Content |
|---|---|
| `index.md` | Runbook names, keywords, and short descriptions. Step 1 uses it. |
| `tables.md` | One line per table: `- table_name: description`. Step 2 uses it. |
| `table_relationship.md` | One `A -> B` line per foreign key. Step 2 uses it. Optional. |
| `runbooks/<name>.md` | Business rules and special cases. Step 5 uses them. |

To add a runbook: add the file to `runbooks/` and add a row to `index.md`. No code change is needed.

## API

Send the header `X-API-Key: <SERVICE_API_KEY>` with every request, except `/health`.
Each document endpoint answers with `{"content": "<Markdown text>"}`.

| Request | Answer |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /index` | The text of `index.md`. |
| `GET /tables` | The text of `tables.md`. |
| `GET /relationships` | The text of `table_relationship.md`. It is `""` if the file is empty or missing. |
| `GET /runbooks/{name}` | The text of one runbook. The name has no `.md`. |

Errors:
- 401: the API key is missing or wrong.
- 404: the file does not exist, for example an unknown runbook.
- 400: the runbook name has other characters than letters, digits, and underscores.

Example:
```bash
curl -H "X-API-Key: change-me" localhost:8002/runbooks/invoice_status
```

## How agent-service uses it

`agent-service/app/knowledge.py` caches each text for `KNOWLEDGE_CACHE_TTL_SECONDS` (default 300).
When a refresh fails, it uses the old copy and logs a warning. So a change in a file shows up
in the agent after the cache time, and a short outage does not stop the agent.
