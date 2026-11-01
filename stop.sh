#!/usr/bin/env bash
# stop.sh – terminate processes started by run.sh

set -e

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PID_FILE="$PROJECT_ROOT/.run.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "⚠️  No PID file found ($PID_FILE). Nothing to stop."
  exit 0
fi

# Read PIDs (backend first, frontend second)
read -r BACKEND_PID FRONTEND_PID < "$PID_FILE"

kill_pid() {
  local pid=$1
  local name=$2
  if kill -0 "$pid" 2>/dev/null; then
    echo "🛑 Stopping $name (PID $pid)..."
    # Kill child processes if any
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      echo "⚡ Force killing $name (PID $pid)..."
      pkill -9 -P "$pid" 2>/dev/null || true
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "⚠️  $name (PID $pid) not running."
  fi
}

kill_pid "$BACKEND_PID" "backend (uvicorn)"
kill_pid "$FRONTEND_PID" "frontend (npm dev)"

rm -f "$PID_FILE"
echo "✅ All services stopped, PID file removed."
