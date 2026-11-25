#!/usr/bin/env bash
# Starts PostgreSQL (if it is down), db-service, knowledge-service, and agent-service.
# Then it waits until each one answers /health. Logs go to .run/*.log. Stop with scripts/stop-all.sh.
# Why no --reload: a restart in the middle of an eval run would make questions fail.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.run"
mkdir -p "$RUN"

# 1. PostgreSQL. Use Docker if it is available (it also loads the sample data on the first start).
# Otherwise start a local system cluster, which may need sudo.
if ! pg_isready -h localhost -q; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "PostgreSQL is down. Starting it with Docker..."
    (cd "$ROOT" && docker compose up -d --wait db)
  else
    echo "PostgreSQL is down. Starting cluster 17/main (sudo may ask for a password)..."
    sudo pg_ctlcluster 17 main start
    for _ in $(seq 1 20); do pg_isready -h localhost -q && break; sleep 1; done
  fi
fi
pg_isready -h localhost -q || { echo "PostgreSQL did not start."; exit 1; }
echo "postgres  ok"

# 2. The three FastAPI services. Order: db and knowledge first, because agent needs both.
start() {
  local name="$1" dir="$2" port="$3"
  if curl -fsS "localhost:$port/health" >/dev/null 2>&1; then
    echo "$name already running on :$port"
    return
  fi
  (cd "$ROOT/$dir" && nohup .venv/bin/uvicorn app.main:app --port "$port" \
    >"$RUN/$name.log" 2>&1 & echo $! >"$RUN/$name.pid")
  for _ in $(seq 1 30); do
    curl -fsS "localhost:$port/health" >/dev/null 2>&1 && { echo "$name  ok  (:$port)"; return; }
    sleep 1
  done
  echo "$name did not start. See $RUN/$name.log"
  exit 1
}

start db-service db-service 8001
start knowledge-service knowledge-service 8002
start agent-service agent-service 8000

# 3. The graph is generated from the live database. Build it only if it is missing.
if [ ! -f "$ROOT/knowledge-service/knowledge_base/graph.json" ]; then
  echo "graph.json is missing. Generating it..."
  curl -fsS -X POST localhost:8002/generate; echo
fi
echo "All services are up. Run: make eval-classifier | make eval-sql | make eval-system"
