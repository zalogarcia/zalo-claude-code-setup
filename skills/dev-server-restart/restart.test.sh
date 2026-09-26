#!/usr/bin/env bash
# Tests for the kill step of restart.sh: it kills by PORT only, never by process name.
#
# Run:  bash ~/.claude/skills/dev-server-restart/restart.test.sh
#
# Regression covered: restart.sh used to follow the port kill with a machine wide
# `pkill -f "next dev"`, `pkill -f "vite"` and `pkill -f "react-scripts start"`.
# With several sessions running on this Mac that killed other sessions' vite and
# vitest runs (and once Operator Base's vite on :5173 while restarting an
# unrelated app on :3000). Removed 2026-09-26.
#
# Two layers:
#   1. Static: no executable line of restart.sh may run pkill or killall. This runs
#      FIRST and aborts before anything is executed, so running this test against
#      an old restart.sh is harmless (it never evals a machine wide kill).
#   2. Behavioural: the kill step is EXTRACTED from restart.sh at run time (from the
#      "# 2." marker to the "# 3." marker, not copied, so it cannot drift) and run
#      against a fake listener on a free port, with fake dev runners on other ports.
#      Only the listener may die.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${RESTART_SH:-$SCRIPT_DIR/restart.sh}"

PASS=0
FAIL=0
check() {
  if [ "$2" = "1" ]; then
    PASS=$((PASS + 1)); echo "  ok   $1"
  else
    FAIL=$((FAIL + 1)); echo "  FAIL $1 ${3:-}"
  fi
}

echo "restart.sh kills by port only"

# 1. Static: any executable (non comment) line naming pkill or killall.
NAME_KILLS=$(grep -nE '^[^#]*\b(pkill|killall)\b' "$TARGET" || true)
if [ -n "$NAME_KILLS" ]; then
  echo "  FAIL no machine wide kill by process name in restart.sh"
  printf '%s\n' "$NAME_KILLS" | sed 's/^/       /'
  echo ""
  echo "$PASS passed, 1 failed (aborted before running anything)"
  exit 1
fi
check "no machine wide kill by process name (pkill/killall) in restart.sh" 1

# 2. Behavioural.
BLOCK=$(awk '/^# 2\. /{f=1} /^# 3\. /{exit} f{print}' "$TARGET")
[ -n "$BLOCK" ] || { echo "FATAL: could not extract the kill step (# 2. to # 3.) from $TARGET"; exit 1; }
printf '%s\n' "$BLOCK" | grep -q 'lsof -ti tcp:"\$PORT"' || { echo "FATAL: extracted kill step does not kill by port"; exit 1; }

PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
OTHER=/tmp/dsr-test-other-project

# The listener this run owns: a server on $PORT dressed as a vite dev server.
bash -c "exec -a 'node /tmp/dsr-test-proj/node_modules/vite/bin/vite.js --port $PORT' python3 -m http.server $PORT --bind 127.0.0.1" >/dev/null 2>&1 &
L_PID=$!
# Other sessions' runners, NOT on $PORT. Each one matched a pkill pattern the old script ran.
bash -c "exec -a 'node $OTHER/node_modules/vite/bin/vite.js --port 5173' sleep 25" &
V_PID=$!
bash -c "exec -a 'node $OTHER/node_modules/vitest/vitest.mjs run' sleep 25" &
T_PID=$!
bash -c "exec -a 'node $OTHER/node_modules/.bin/next dev -p 3001' sleep 25" &
N_PID=$!
bash -c "exec -a 'node $OTHER/node_modules/react-scripts/bin/react-scripts.js react-scripts start' sleep 25" &
R_PID=$!

# Wait up to 5 s for the listener to bind.
for _ in $(seq 1 50); do
  lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && break
  sleep 0.1
done
check "fake listener bound :$PORT before the kill" "$(lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && echo 1 || echo 0)"

eval "$BLOCK" > /tmp/dsr-test-out.txt 2>&1

alive() { kill -0 "$1" 2>/dev/null && echo 1 || echo 0; }
check "kills the listener on :$PORT" "$([ "$(alive "$L_PID")" = "0" ] && echo 1 || echo 0)" "(pid $L_PID still alive)"
check "port :$PORT is free afterwards" "$(lsof -ti tcp:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && echo 0 || echo 1)"
check "leaves another session's vite alone" "$(alive "$V_PID")" "(pid $V_PID was killed)"
check "leaves another session's vitest alone" "$(alive "$T_PID")" "(pid $T_PID was killed)"
check "leaves another session's next dev alone" "$(alive "$N_PID")" "(pid $N_PID was killed)"
check "leaves another session's react-scripts start alone" "$(alive "$R_PID")" "(pid $R_PID was killed)"
check "reports what it killed" "$(grep -q "Killing PID(s) on :$PORT" /tmp/dsr-test-out.txt && echo 1 || echo 0)" "$(cat /tmp/dsr-test-out.txt)"

kill "$L_PID" "$V_PID" "$T_PID" "$N_PID" "$R_PID" 2>/dev/null
wait 2>/dev/null

echo ""
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
