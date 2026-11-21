.PHONY: help db-load db-local-reset dbsvc knowledge kb-generate agent eval eval-check test lint
.DEFAULT_GOAL := help

# Plain "make" only prints this list. It never starts anything.
help:
	@echo "Database (local PostgreSQL):"
	@echo "  make db-load         load sample data and read-only role (needs PGPASSWORD)"
	@echo "  make db-local-reset  delete all tables in schema public, then load again"
	@echo "Run:    make dbsvc | make knowledge | make agent"
	@echo "KB:     make kb-generate  (build graph.json from the live database; dbsvc and knowledge must run)"
	@echo "Eval:   make eval  (3 levels, see eval/README.md)"
	@echo "Check:  make test | make lint"

# The owner of the nl2sql database runs the SQL files.
# Set the password with PGPASSWORD or ~/.pgpass. Do not put it in this file.
# Example: PGPASSWORD=... make db-load
LOCAL_DB_URL ?= postgresql://admin@localhost:5432/nl2sql

# Load the sample data and the read-only role. Run it once.
db-load:
	for f in database/init/*.sql; do psql "$(LOCAL_DB_URL)" -v ON_ERROR_STOP=1 -f $$f || exit 1; done

# Delete all tables in the public schema, then load everything again.
db-local-reset:
	psql "$(LOCAL_DB_URL)" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	$(MAKE) db-load

# Run db-service on port 8001.
dbsvc:
	cd db-service && .venv/bin/uvicorn app.main:app --port 8001 --reload

# Run knowledge-service on port 8002. Start it before agent-service.
knowledge:
	cd knowledge-service && .venv/bin/uvicorn app.main:app --port 8002 --reload

# Build knowledge-service/knowledge_base/graph.json from the live database. No LLM call.
# db-service and knowledge-service must run.
kb-generate:
	curl -sS -X POST localhost:8002/generate; echo

# Run agent-service on port 8000.
agent:
	cd agent-service && .venv/bin/uvicorn app.main:app --port 8000 --reload

# The dev eval: 3 levels (classifier, sql, system). It needs dbsvc, knowledge, and agent running.
# It uses the agent-service venv, because levels 1 and 2 call the agent code directly.
# Examples: make eval   |   make eval ARGS="--level sql --repeat 3"   (see eval/README.md)
eval:
	cd agent-service && PYTHONPATH=../eval .venv/bin/python -m run_eval $(ARGS)

# Run every gold SQL on the database. Each must give rows. Needs dbsvc.
eval-check:
	cd eval && .venv/bin/python check_gold.py

# Run the tests of all projects. The db-service tests need the database (make db-load).
test:
	cd db-service && .venv/bin/pytest -q
	cd agent-service && .venv/bin/pytest -q
	cd knowledge-service && .venv/bin/pytest -q
	cd eval && .venv/bin/pytest -q

# Check the code style of all projects.
lint:
	cd db-service && .venv/bin/ruff check .
	cd knowledge-service && .venv/bin/ruff check .
	cd agent-service && .venv/bin/ruff check .
	cd eval && .venv/bin/ruff check .
