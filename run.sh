#!/usr/bin/env bash
# run.sh – start backend (uvicorn) and frontend (npm dev) services
# Stores PIDs in .run.pid for later termination via stop.sh

set -e

# Resolve project root (directory of this script)
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PID_FILE="$PROJECT_ROOT/.run.pid"

if [[ -f "$PID_FILE" ]]; then
  echo "⚠️  Detected existing PID file ($PID_FILE). Stop existing services first with ./stop.sh"
  exit 1
fi

cd "$PROJECT_ROOT"

# Activate Python virtual environment
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "⚠️  Virtual environment not found. Create it first with 'python -m venv .venv && source .venv/bin/activate && pip install -e \"backend[dev]\"'"
  exit 1
fi
source .venv/bin/activate

# ---------------------------------------------------------------------------
# Start backend (FastAPI) – log to backend.log
# ---------------------------------------------------------------------------
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "✅ Backend started (PID $BACKEND_PID), logs: $PROJECT_ROOT/backend.log"

# ---------------------------------------------------------------------------
# Start frontend (Vite dev server) – log to frontend.log
# ---------------------------------------------------------------------------
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo "✅ Frontend started (PID $FRONTEND_PID), logs: $PROJECT_ROOT/frontend.log"

# Return to project root and store PIDs
cd "$PROJECT_ROOT"
echo "$BACKEND_PID $FRONTEND_PID" > "$PID_FILE"
chmod 600 "$PID_FILE"

echo "🚀 All services are up. PID file stored at $PID_FILE"
