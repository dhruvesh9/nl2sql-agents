.PHONY: help db-load db-local-reset dbsvc knowledge kb-generate agent eval-tables test lint
.DEFAULT_GOAL := help

# Plain "make" only prints this list. It never starts anything.
help:
	@echo "Database (local PostgreSQL):"
	@echo "  make db-load         load sample data and read-only role (needs PGPASSWORD)"
	@echo "  make db-local-reset  delete all tables in schema public, then load again"
	@echo "Run:    make dbsvc | make knowledge | make agent"
	@echo "KB:     make kb-generate  (build graph.json from the live database; dbsvc and knowledge must run)"
	@echo "Eval:   make eval-tables  (broken for now: POST /analyze was removed)"
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

# Score the Table Classifier with eval/ground_truth/table_classifier.csv. Start "make agent" first.
# BROKEN for now: it calls POST /analyze, which agent-service no longer has. The eval will be redone.
eval-tables:
	cd eval && .venv/bin/python run_table_classifier.py

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
