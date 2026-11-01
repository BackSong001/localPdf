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
setsid "$PROJECT_ROOT/.venv/bin/uvicorn" app.main:app --app-dir backend --host 127.0.0.1 --port 8000 </dev/null > "$PROJECT_ROOT/backend.log" 2>&1 &
BACKEND_PID=$!

# ---------------------------------------------------------------------------
# Start frontend (Vite dev server) – log to frontend.log
# ---------------------------------------------------------------------------
cd "$PROJECT_ROOT/frontend"
setsid npm run dev </dev/null > "$PROJECT_ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!

# Return to project root and store PIDs
cd "$PROJECT_ROOT"
echo "$BACKEND_PID $FRONTEND_PID" > "$PID_FILE"
chmod 600 "$PID_FILE"

echo "=========================================="
echo "• 백엔드 API (FastAPI) : http://127.0.0.1:8000"
echo "  예) GET http://127.0.0.1:8000/api/health"
echo "• 프론트엔드 UI (Vite 개발 서버) : http://127.0.0.1:5173"
echo "=========================================="
echo "🚀 모든 서비스가 시작되었습니다 (Backend PID: $BACKEND_PID, Frontend PID: $FRONTEND_PID)"
