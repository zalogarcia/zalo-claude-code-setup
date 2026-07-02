#!/usr/bin/env bash
# voice-test-stack — bring the full local voice-test stack up (or down):
# gateway (:3000, built JS + node) + dashboard (:5174, vite) + tunnel
# (cloudflared or ngrok, auto-picked from GATEWAY_URL in .env), then print
# the callable state: health, URLs, and webhook URL shapes.
#
# Usage:
#   voice-test-stack.sh up   [REPO_DIR] [--tunnel auto|cloudflared|ngrok|none] [--no-build]
#   voice-test-stack.sh down [REPO_DIR]
#   voice-test-stack.sh status [REPO_DIR]
#
# REPO_DIR defaults to /Users/zalo/dev/delta-agents. Pass a worktree path to
# run the stack from a branch checked out elsewhere. Ports are fixed
# (3000/5174) — one stack at a time, whichever checkout you point at.
#
# Exit codes: 0 ok · 1 gateway failed · 2 dashboard failed · 3 tunnel failed
# Logs: /tmp/voice-stack-{gateway,dashboard,tunnel}.log
# PIDs: /tmp/voice-stack-{gateway,dashboard,tunnel}.pid

set -uo pipefail

MODE="${1:-up}"
[ $# -gt 0 ] && shift
ROOT="/Users/zalo/dev/delta-agents"
GATEWAY_PORT="${GATEWAY_PORT:-3000}"
DASH_PORT="${DASH_PORT:-5174}"
TUNNEL_MODE="auto"
DO_BUILD=1
TIMEOUT_S="${TIMEOUT_S:-45}"

# First non-flag arg = REPO_DIR (main checkout or a worktree)
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then
  [ -d "$1" ] || { echo "ERROR: REPO_DIR '$1' is not a directory" >&2; exit 64; }
  ROOT="$1"; shift
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --tunnel) TUNNEL_MODE="${2:-auto}"; shift 2 ;;
    --no-build) DO_BUILD=0; shift ;;
    *) shift ;;
  esac
done

GW_LOG=/tmp/voice-stack-gateway.log
DASH_LOG=/tmp/voice-stack-dashboard.log
TUN_LOG=/tmp/voice-stack-tunnel.log

kill_port() { # kill_port PORT LABEL
  local pids
  pids=$(lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Killing $2 listener(s) on :$1 — $pids"
    kill $pids 2>/dev/null || true
    sleep 1
    pids=$(lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null || true)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  fi
}

kill_pidfile() { # kill_pidfile /tmp/foo.pid
  if [ -f "$1" ]; then
    local pid; pid=$(cat "$1")
    kill "$pid" 2>/dev/null || true
    rm -f "$1"
  fi
}

poll_http() { # poll_http URL WANT_REGEX TIMEOUT_S -> echoes final code, rc 0/1
  local i code
  for i in $(seq 1 $(( $3 * 2 ))); do
    code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null || echo 000)
    if echo "$code" | grep -qE "$2"; then echo "$code"; return 0; fi
    sleep 0.5
  done
  echo "$code"; return 1
}

# ── down ────────────────────────────────────────────────────────────────────
stack_down() {
  kill_pidfile /tmp/voice-stack-tunnel.pid
  kill_pidfile /tmp/voice-stack-gateway.pid
  kill_pidfile /tmp/voice-stack-dashboard.pid
  kill_port "$GATEWAY_PORT" gateway
  kill_port "$DASH_PORT" dashboard
  echo "voice-test-stack: down (ports $GATEWAY_PORT/$DASH_PORT free, tunnel pidfile cleared)"
}

# ── status ──────────────────────────────────────────────────────────────────
stack_status() {
  local gw dash
  gw=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://localhost:$GATEWAY_PORT/health" 2>/dev/null || echo 000)
  dash=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://localhost:$DASH_PORT/" 2>/dev/null || echo 000)
  echo "gateway   :$GATEWAY_PORT /health → $gw"
  echo "dashboard :$DASH_PORT / → $dash"
  if [ -f /tmp/voice-stack-tunnel.pid ] && kill -0 "$(cat /tmp/voice-stack-tunnel.pid)" 2>/dev/null; then
    echo "tunnel    pid $(cat /tmp/voice-stack-tunnel.pid) running (log $TUN_LOG)"
  else
    echo "tunnel    not running (started by this script)"
  fi
}

case "$MODE" in
  down)   stack_down; exit 0 ;;
  status) stack_status; exit 0 ;;
  up)     : ;;
  *) echo "usage: voice-test-stack.sh up|down|status [REPO_DIR] [--tunnel MODE] [--no-build]" >&2; exit 64 ;;
esac

# ── up: preconditions ───────────────────────────────────────────────────────
[ -f "$ROOT/.env" ] || { echo "ERROR: $ROOT/.env missing — copy .env.example first" >&2; exit 1; }
[ -d "$ROOT/node_modules" ] || { echo "ERROR: $ROOT/node_modules missing — run 'npm ci' in $ROOT first (worktree gotcha)" >&2; exit 1; }

BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo "?")
GATEWAY_URL=$(grep -E '^GATEWAY_URL=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"' || true)
echo "voice-test-stack: ROOT=$ROOT branch=$BRANCH GATEWAY_URL=${GATEWAY_URL:-<unset>}"

# ── kill stale listeners (by port, not name) ────────────────────────────────
kill_port "$GATEWAY_PORT" gateway
kill_port "$DASH_PORT" dashboard

# ── build (mirrors scripts/dev.sh standard mode) ────────────────────────────
if [ "$DO_BUILD" = 1 ]; then
  echo "Building packages (tsc chain, mirrors scripts/dev.sh)…"
  (cd "$ROOT/packages/shared"      && npx tsc)           >/dev/null 2>&1 || true
  (cd "$ROOT/packages/providers"   && npx tsc --noCheck) >/dev/null 2>&1 || true
  (cd "$ROOT/packages/core"        && npx tsc --noCheck) >/dev/null 2>&1 || true
  (cd "$ROOT/packages/mcp-servers" && npx tsc --noCheck) >/dev/null 2>&1 || true
  (cd "$ROOT/apps/gateway"         && npx tsc)           >/dev/null 2>&1 || true
fi
[ -f "$ROOT/apps/gateway/dist/index.js" ] || { echo "ERROR: gateway dist/index.js missing after build — run 'npx tsc' in apps/gateway and read errors" >&2; exit 1; }

# ── gateway (built JS + node, like dev.sh standard mode) ────────────────────
echo "Starting gateway :$GATEWAY_PORT (node dist/index.js)…"
( cd "$ROOT/apps/gateway" && nohup node --env-file="$ROOT/.env" dist/index.js > "$GW_LOG" 2>&1 & echo $! > /tmp/voice-stack-gateway.pid )
GW_CODE=$(poll_http "http://localhost:$GATEWAY_PORT/health" '^200$' "$TIMEOUT_S") || {
  echo "GATEWAY FAILED (/health → $GW_CODE). Last 30 log lines:" >&2
  tail -30 "$GW_LOG" >&2
  exit 1
}
# /ready is the sticky boot gate (pool warm-up) — report, don't block long
READY_CODE=$(poll_http "http://localhost:$GATEWAY_PORT/ready" '^200$' 20) || true

# ── dashboard (vite, port pinned like dev.sh) ───────────────────────────────
echo "Starting dashboard :$DASH_PORT (vite)…"
( cd "$ROOT/apps/dashboard" && nohup npx vite --port "$DASH_PORT" --strictPort > "$DASH_LOG" 2>&1 & echo $! > /tmp/voice-stack-dashboard.pid )
DASH_CODE=$(poll_http "http://localhost:$DASH_PORT/" '^[23]' "$TIMEOUT_S") || {
  echo "DASHBOARD FAILED (/ → $DASH_CODE). Last 30 log lines:" >&2
  tail -30 "$DASH_LOG" >&2
  exit 2
}

# ── tunnel ──────────────────────────────────────────────────────────────────
TUN_HOST=""; TUN_CODE="-"; TUN_STARTED=0
if [ "$TUNNEL_MODE" = "auto" ]; then
  case "${GATEWAY_URL:-}" in
    *ngrok*)              TUNNEL_MODE=ngrok ;;
    *blackumbrella.app*)  TUNNEL_MODE=cloudflared ;;
    *) if [ -f "$HOME/.cloudflared/config.yml" ]; then TUNNEL_MODE=cloudflared; else TUNNEL_MODE=none; fi ;;
  esac
fi
case "$TUNNEL_MODE" in
  cloudflared)
    TUN_HOST=$(awk '/hostname:/ {print $3; exit}' "$HOME/.cloudflared/config.yml" 2>/dev/null || true)
    if [ -z "$TUN_HOST" ]; then
      echo "WARN: no hostname in ~/.cloudflared/config.yml — skipping tunnel" >&2
    else
      kill_pidfile /tmp/voice-stack-tunnel.pid
      echo "Starting cloudflared tunnel → https://$TUN_HOST …"
      ( nohup cloudflared tunnel run > "$TUN_LOG" 2>&1 & echo $! > /tmp/voice-stack-tunnel.pid )
      TUN_STARTED=1
      TUN_CODE=$(poll_http "https://$TUN_HOST/health" '^200$' "$TIMEOUT_S") || {
        echo "TUNNEL FAILED (https://$TUN_HOST/health → $TUN_CODE). Last 20 log lines:" >&2
        tail -20 "$TUN_LOG" >&2
        # keep stack up; tunnel failure is exit 3 at the end
      }
    fi
    ;;
  ngrok)
    TUN_HOST=$(echo "${GATEWAY_URL:-}" | sed -E 's|https?://||; s|/.*||')
    if [ -z "$TUN_HOST" ]; then
      echo "WARN: --tunnel ngrok but GATEWAY_URL has no host — skipping tunnel" >&2
    else
      kill_pidfile /tmp/voice-stack-tunnel.pid
      echo "Starting ngrok → https://$TUN_HOST …"
      ( nohup ngrok http --url="$TUN_HOST" "$GATEWAY_PORT" --log=stdout > "$TUN_LOG" 2>&1 & echo $! > /tmp/voice-stack-tunnel.pid )
      TUN_STARTED=1
      TUN_CODE=$(poll_http "https://$TUN_HOST/health" '^200$' "$TIMEOUT_S") || {
        echo "TUNNEL FAILED (https://$TUN_HOST/health → $TUN_CODE). Last 20 log lines:" >&2
        tail -20 "$TUN_LOG" >&2
      }
    fi
    ;;
  none) : ;;
esac

# ── callable state ──────────────────────────────────────────────────────────
BASE="${TUN_HOST:+https://$TUN_HOST}"; BASE="${BASE:-http://localhost:$GATEWAY_PORT}"
echo ""
echo "════════ voice-test-stack: CALLABLE STATE ════════"
echo "branch      $BRANCH  ($ROOT)"
echo "gateway     http://localhost:$GATEWAY_PORT/health → $GW_CODE   (/ready → ${READY_CODE:-?})   log=$GW_LOG"
echo "dashboard   http://localhost:$DASH_PORT/ → $DASH_CODE   log=$DASH_LOG"
if [ "$TUN_STARTED" = 1 ]; then
  echo "tunnel      https://$TUN_HOST/health → $TUN_CODE   ($TUNNEL_MODE)   log=$TUN_LOG"
else
  echo "tunnel      not started (mode=$TUNNEL_MODE)"
fi
if [ -n "${GATEWAY_URL:-}" ] && [ -n "$TUN_HOST" ]; then
  if echo "$GATEWAY_URL" | grep -q "$TUN_HOST"; then
    echo "GATEWAY_URL $GATEWAY_URL   [MATCHES tunnel — Retell-synced URLs will resolve]"
  else
    echo "GATEWAY_URL $GATEWAY_URL   [MISMATCH vs tunnel $TUN_HOST — update .env + re-sync voice agents]"
  fi
fi
echo "webhooks    POST $BASE/hooks/:crm_type/:tenant_slug              (legacy)"
echo "            POST $BASE/hooks/:crm_type/:tenant_slug/:agent_slug  (preferred)"
echo "voice       POST $BASE/voice/mcp/:tenantId/:agentId"
echo "            POST $BASE/voice/retell/inbound/:tenantId/:agentId"
echo "            POST $BASE/voice/retell/post-call/:tenantId/:agentId"
echo "identities  see $ROOT/.claude/test-identities.md (admin account, test phone +17867810250, Retell agents)"
echo "═══════════════════════════════════════════════════"

if [ "$TUN_STARTED" = 1 ] && [ "$TUN_CODE" != "200" ]; then exit 3; fi
exit 0
