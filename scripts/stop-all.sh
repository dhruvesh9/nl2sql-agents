#!/usr/bin/env bash
# Stops the three services that start-all.sh started. It leaves PostgreSQL running.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for name in agent-service knowledge-service db-service; do
  pid_file="$ROOT/.run/$name.pid"
  if [ -f "$pid_file" ]; then
    kill "$(cat "$pid_file")" 2>/dev/null && echo "stopped $name"
    rm -f "$pid_file"
  fi
done
