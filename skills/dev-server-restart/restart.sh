#!/usr/bin/env bash
# dev-server-restart — kill any stale dev server on a port, restart in nohup,
# poll for readiness, smoke-test a route, exit with bounded output.
#
# Usage:
#   restart.sh [PORT] [CWD] [PROBE_PATH]
#   PORT=3000 CWD=. PROBE=/admin restart.sh
#
# Defaults: PORT=3000, CWD=$(pwd), PROBE=/
# Returns exit 0 on success, 1 on failure to start, 2 on probe error (5xx).
# Log lives at /tmp/dev-server-<PORT>.log

set -uo pipefail

PORT="${1:-${PORT:-3000}}"
CWD="${2:-${CWD:-$(pwd)}}"
PROBE="${3:-${PROBE:-/}}"
LOG="/tmp/dev-server-${PORT}.log"
TIMEOUT_S="${TIMEOUT_S:-30}"

# 1. Detect package manager
cd "$CWD" || { echo "ERROR: cannot cd to $CWD" >&2; exit 1; }
PM="npm"
[ -f pnpm-lock.yaml ] && PM="pnpm"
[ -f yarn.lock ] && PM="yarn"
[ -f bun.lockb ] && PM="bun"

# 2. Kill anything on the port (by port, not process name — more reliable)
EXISTING=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
  echo "Killing PID(s) on :$PORT — $EXISTING"
  kill $EXISTING 2>/dev/null || true
  sleep 1
  STILL=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
  [ -n "$STILL" ] && kill -9 $STILL 2>/dev/null || true
fi

# Belt-and-suspenders: kill known dev runners anywhere (in case they're bound to a different port)
pkill -f "next dev" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true
sleep 1

# 3. Start fresh, detached, log to /tmp
echo "Starting '$PM run dev' in $CWD"
( cd "$CWD" && nohup $PM run dev > "$LOG" 2>&1 & )
sleep 0.2

# 4. Poll for readiness (up to TIMEOUT_S, in 0.5s ticks)
START_TS=$(date +%s)
READY=0
for i in $(seq 1 $((TIMEOUT_S * 2))); do
  if curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/" 2>/dev/null | grep -qE '^[2345]'; then
    READY=1
    break
  fi
  sleep 0.5
done
ELAPSED=$(( $(date +%s) - START_TS ))

if [ "$READY" -ne 1 ]; then
  echo "DEV SERVER FAILED to start in ${ELAPSED}s. Last 30 log lines:" >&2
  tail -30 "$LOG" >&2
  exit 1
fi

# 5. Smoke-test the requested probe path
STATUS=$(curl -s -o /tmp/probe.html -w '%{http_code}' "http://localhost:$PORT$PROBE")
SIZE=$(wc -c < /tmp/probe.html | tr -d ' ')
echo "READY in ${ELAPSED}s | :$PORT$PROBE → HTTP $STATUS (${SIZE} bytes) | log=$LOG"

# Surface error region from log on 5xx
if echo "$STATUS" | grep -qE '^5'; then
  echo "--- log error region ---" >&2
  grep -nE "error|Error|ERROR|failed|Failed" "$LOG" | head -10 >&2
  exit 2
fi

exit 0
