#!/usr/bin/env bash
# Starts the Miren API (port 8001) and the Next.js dashboard (port 3001). Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "Starting Miren..."

[ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; echo "Created .env from .env.example"; }

command -v node >/dev/null || { echo "Node.js 18+ is required: https://nodejs.org"; exit 1; }

# the backend needs Python 3.11 or newer
find_python() {
  for py in python3.12 python3.13 python3.11 python3; do
    if command -v "$py" >/dev/null && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
      echo "$py"
      return
    fi
  done
}

cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  PY="$(find_python)"
  if [ -n "$PY" ]; then
    "$PY" -m venv .venv
  elif command -v uv >/dev/null; then
    uv venv -q --python 3.12 .venv
  else
    echo "Python 3.11+ is required: https://www.python.org/downloads/"
    exit 1
  fi
fi
echo "Installing backend dependencies..."
if command -v uv >/dev/null; then
  uv pip install -q --python .venv/bin/python -r requirements.txt
else
  .venv/bin/python -m pip install -q -r requirements.txt
fi
.venv/bin/uvicorn main:app --reload --port 8001 &
BACKEND_PID=$!

# the dashboard reads NEXT_PUBLIC_API_URL from the root .env unless it is already set in the shell
if [ -z "${NEXT_PUBLIC_API_URL:-}" ]; then
  NEXT_PUBLIC_API_URL="$(grep -E '^NEXT_PUBLIC_API_URL=' "$ROOT/.env" | tail -1 | cut -d= -f2- || true)"
fi
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8001}"

cd "$ROOT/frontend"
[ -d node_modules ] || { echo "Installing frontend dependencies..."; npm install --no-audit --no-fund; }
npm run dev -- --port 3001 &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM

echo "Backend:  http://localhost:8001  (API docs at http://localhost:8001/docs)"
echo "Frontend: http://localhost:3001"
echo "Press Ctrl+C to stop both."
wait
