#!/usr/bin/env bash
# Starts the Miren API (port 8001) and the Next.js dashboard (port 3001).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "Starting Miren..."

[ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; echo "Created .env from .env.example"; }

cd "$ROOT/backend"
[ -d .venv ] || python3 -m venv .venv
if command -v uv >/dev/null; then
  uv pip install -q --python .venv/bin/python -r requirements.txt
else
  .venv/bin/python -m pip install -q -r requirements.txt
fi
.venv/bin/uvicorn main:app --reload --port 8001 &
BACKEND_PID=$!

cd "$ROOT/frontend"
[ -d node_modules ] || npm install
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8001}" npm run dev -- --port 3001 &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM

echo "Backend:  http://localhost:8001  (docs at /docs)"
echo "Frontend: http://localhost:3001"
wait
