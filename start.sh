#!/usr/bin/env bash
#
# Start the FastAPI backend and the Vite frontend together, and shut both down
# on Ctrl-C. Run from the project root:
#
#     ./start.sh /path/to/your/original/project
#
# The argument is the folder that contains bellhop/ and ssp/. If you omit it,
# WG_DATA_ROOT from your environment is used.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -ge 1 ]; then
  export WG_DATA_ROOT="$(cd "$1" && pwd)"
fi

if [ -z "${WG_DATA_ROOT:-}" ]; then
  echo "WG_DATA_ROOT is not set."
  echo "Usage: ./start.sh /bellhop"
  exit 1
fi

for required in "$WG_DATA_ROOT/bellhop" "$WG_DATA_ROOT/ssp"; do
  if [ ! -d "$required" ]; then
    echo "Warning: $required does not exist. Runs will fail until it does."
  fi
done

echo "WG_DATA_ROOT = $WG_DATA_ROOT"

# Kill both children when this script exits for any reason.
pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "Starting backend on http://127.0.0.1:8000 ..."
( cd "$ROOT/backend" && exec uvicorn app.main:app --reload --port 8000 ) &
pids+=($!)

# Wait for the backend to answer before starting Vite, so the first page load
# doesn't hit a connection-refused error.
for _ in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Backend is up."
    break
  fi
  sleep 0.5
done

if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo
  echo "Backend did not come up. Scroll up for the uvicorn error - the usual"
  echo "causes are a missing dependency (pip install -r backend/requirements.txt)"
  echo "or Python older than 3.10."
  exit 1
fi

echo "Starting frontend on http://localhost:5173 ..."
( cd "$ROOT/frontend" && exec npm run dev ) &
pids+=($!)

wait
