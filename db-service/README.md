# db-service: API reference for agent-service

db-service is the only component that connects to the database.
Base URL: `http://localhost:8001`. There is no authentication for now (later: Keycloak and JWT).
From Python, use `agent-service/app/db_client.py`: `get_schema`, `get_plan`, `run_query`.

## Errors

| Status | Meaning |
|---|---|
| 400 | The SQL was rejected. `{"detail": "<reason>"}`. Examples: not a SELECT, more than one statement, wrong column, timeout. |
| 422 | The request body has the wrong shape. |

`db_client` raises `DbServiceError(status_code, detail)` for every status of 400 or more.
Use `detail` as feedback for the SQL generator.

## GET /catalog

Every table in the database, for knowledge-service `POST /generate`.
It reads the whole schema with the SQLAlchemy `get_multi_*` functions: about 3 catalog queries in total,
not 5 per table. It returns only table comments and foreign keys. Column types come live from `/schema`.

```bash
curl -s localhost:8001/catalog
# {"dialect":"postgresql","tables":[{"name":"accounts","description":"Billing accounts. ...",
#   "foreign_keys":[...]}, ...]}
```

## POST /schema

Reads the live structure of the tables. With `fk_depth` above 0, it also adds the tables
linked by foreign keys (both directions). `fk_depth` is limited by `MAX_FK_DEPTH` (default 3).
The discovered tables are in `tables` too, so one call is enough.

```bash
curl -s -X POST localhost:8001/schema -H 'Content-Type: application/json' \
  -d '{"tables": ["invoices", "nope"], "fk_depth": 1}'
```
Result: `tables` (invoices, accounts, invoice_lines, payments), `discovered_tables`
(accounts, invoice_lines, payments), `not_found` (nope), `dialect` (postgresql).
Each table has columns (name, type, nullable), primary_key, foreign_keys, and description.

## POST /plan

Checks the SQL and asks the database for the plan. It never runs the query.
A database error (wrong table or column) is not an HTTP error. You get `valid: false` and the message.

```bash
curl -s -X POST localhost:8001/plan -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT nme FROM customers"}'
# {"valid":false,"error":"column \"nme\" does not exist",...}
```
Good SQL gives `valid: true`, `estimated_cost`, `estimated_rows`, and `plan`.
SQL that is not a single SELECT gives HTTP 400.

## POST /query

Runs the SQL in a read-only transaction with a timeout (`STATEMENT_TIMEOUT_MS`, default 5000).
`max_rows` is optional. The default is `DEFAULT_MAX_ROWS` (100). The largest value is `MAX_ROWS_LIMIT` (1000).
`truncated: true` means the database had more rows than `max_rows`.
`Decimal` values become numbers. Dates become ISO text.

```bash
curl -s -X POST localhost:8001/query -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT status, COUNT(*) AS n FROM invoices GROUP BY status", "max_rows": 10}'
# {"columns":["status","n"],"rows":[["C",20],["O",60],["P",120]],"row_count":3,"truncated":false,"elapsed_ms":3}
```

## Safety layers

1. The SQL guard (`sql_guard.py`): one SELECT only.
2. The database user `nl2sql_reader`: `SELECT` only.
3. A read-only transaction and a statement timeout on every query.
4. A row limit.

## Run the tests

```bash
cd db-service && .venv/bin/pytest -q
```
The database tests skip when PostgreSQL is not running.

## Request ID and logs

Every request has a request ID (the `X-Request-ID` header, or a new one). It is in every log line and in the
response header. Logs are JSON, one object per line (`LOG_FORMAT=text` for a terminal). Each request writes one
`request` line with the method, path, status, and `duration_ms`.

## Errors

Each database failure has its own status, so the agent can react in the right way:

| Status | Meaning |
|---|---|
| 400 | The SQL is not allowed or the database rejects it (wrong column, syntax). `detail` says why. |
| 504 | The query was valid but ran longer than `STATEMENT_TIMEOUT_MS`. The agent must not "fix" the SQL. |
| 503 | The database cannot be reached, is out of connections, or the connection pool is full. |
| 500 | A bug. The body is `{"detail": "Internal server error", "request_id": "..."}`. |
