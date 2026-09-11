#!/bin/bash
# peer-refresh.sh: bring a named tmux session back to a healthy idle prompt.
#
#   ~/.claude/scripts/peer-refresh.sh <session> [--force-thread] [--dry-run] [--reason "text"]
#
# The ONLY sanctioned way for a Claude session (M, the Telegram bridge, or any
# peer) to start a fresh thread in, or terminate and relaunch, another tmux
# session. Zalo authorized it on 2026-09-11 ("find a way so you can always
# refresh that so it doesn't need me") for the sessions listed in
# ~/.claude/config/peer-refresh-allow.json and for nothing else. The allowlist is
# checked before anything is touched, and the PreToolUse guard
# (~/.claude/hooks/tmux-peer-guard.py) reads the same file and blocks this script
# from being aimed at any other session, from a bash -c wrapper, or from any path
# other than this one. Adding a session to the allowlist is an owner decision made
# in the owner's own terminal, never on a peer's say so.
#
# Three escalating steps, each verified before the next one runs:
#   a) probe: peer-ask.sh "ping" with a 25 s timeout. A reply that shows the idle
#      prompt and does not contain "explicitly stopped" is healthy: done, exit 0.
#      A timeout here means the session is BUSY (a real job is running), not
#      broken: nothing is touched, exit 3. Use --force-thread when it is hung.
#   b) fresh thread: type /new plus Enter into the pane (the Codex TUI command that
#      starts a new conversation), wait up to 20 s for the idle prompt, probe
#      again. --force-thread skips (a) and starts here: on 2026-09-11 the TUI
#      answered pings while its Computer Use app session was stopped ("This
#      application session has been explicitly stopped by the user for this turn").
#   c) relaunch: kill the session, run the xbar launcher through Terminal (it
#      attaches, so it needs a TTY), wait up to 90 s in 5 s polls for the idle
#      prompt, probe again. A session that never existed skips (b) and the kill.
#
# Exit codes: 0 healthy, 1 refused (session not in the allowlist, or usage),
# 2 relaunch failed (still not healthy after step c), 3 busy (probe timed out on
# a session that was not forced; nothing touched).
# Every step appends one line to ~/.claude/logs/peer-refresh.log:
#   <timestamp> <session> <step> <outcome> [reason: <text>]
#
# Test: bash ~/.claude/scripts/peer-refresh.test.sh (a fake tmux and a fake open
# on PATH record every call; no real session is ever touched by the test).
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ALLOW_FILE="$HOME/.claude/config/peer-refresh-allow.json"
PEER_ASK="$HERE/peer-ask.sh"
LAUNCHER="$HOME/Library/Application Support/xbar/plugins/scripts/launch-codex-bare.sh"
LOG="${PEER_REFRESH_LOG:-$HOME/.claude/logs/peer-refresh.log}"
IDLE_MARK="Ask Codex to do anything"
# Timings are overridable only so the shim test can run in seconds.
PROBE_TIMEOUT="${PEER_REFRESH_PROBE_TIMEOUT:-25}"
THREAD_WAIT="${PEER_REFRESH_THREAD_WAIT:-20}"
RELAUNCH_WAIT="${PEER_REFRESH_RELAUNCH_WAIT:-90}"
POLL="${PEER_REFRESH_POLL:-5}"

usage() {
  echo "usage: peer-refresh.sh <session> [--force-thread] [--relaunch] [--dry-run] [--reason \"text\"]" >&2
  exit 1
}

SESSION="${1:-}"
[ -n "$SESSION" ] || usage
case "$SESSION" in -*) usage ;; esac
shift
FORCE_THREAD=0; RELAUNCH=0; DRY_RUN=0; REASON=""
while [ $# -gt 0 ]; do
  case "$1" in
    --force-thread) FORCE_THREAD=1 ;;
    # --relaunch: skip the probe and the fresh thread, kill and relaunch outright.
    # For a session whose TUI answers pings but whose process is wrong (a
    # launcher change that must take effect, a helper wedged inside the process).
    --relaunch) RELAUNCH=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --reason) [ $# -ge 2 ] || { echo "peer-refresh: --reason needs a value" >&2; exit 1; }; REASON="$2"; shift ;;
    *) echo "peer-refresh: unknown arg '$1'" >&2; usage ;;
  esac
  shift
done

# ---- the allowlist gate, before anything else ------------------------------
allowed() {
  [ -r "$ALLOW_FILE" ] || return 1
  python3 - "$ALLOW_FILE" "$SESSION" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    sessions = data.get("sessions") or []
except Exception:
    sys.exit(1)
sys.exit(0 if sys.argv[2] in sessions else 1)
PY
}
if ! allowed; then
  echo "peer-refresh: REFUSED: '$SESSION' is not in $ALLOW_FILE. Only the owner adds a session there, in his own terminal." >&2
  exit 1
fi

# ---- helpers ---------------------------------------------------------------
TMUX_BIN="$(command -v tmux || echo /usr/local/bin/tmux)"
OPEN_BIN="$(command -v open || echo /usr/bin/open)"
t() { "$TMUX_BIN" "$@"; }
now() { date +%Y-%m-%dT%H:%M:%S%z; }
log() {
  # <timestamp> <session> <step> <outcome> [reason: <text>]
  mkdir -p "$(dirname "$LOG")"
  if [ -n "$REASON" ]; then
    printf '%s %s %s %s reason: %s\n' "$(now)" "$SESSION" "$1" "$2" "$REASON" >> "$LOG"
  else
    printf '%s %s %s %s\n' "$(now)" "$SESSION" "$1" "$2" >> "$LOG"
  fi
  echo "peer-refresh: $SESSION $1: $2"
}
alive() { t has-session -t "=$SESSION" 2>/dev/null; }
capture() { t capture-pane -t "$SESSION:" -p -J -S -40 2>/dev/null; }

# Probe: one ping through peer-ask.sh. Sets PROBE_RC and PROBE_OUT.
#   healthy  = exit 0 and the reply does not mention the stopped app session
#   returns 1 otherwise; the caller reads PROBE_RC to tell no session (2),
#   timeout (3) and session ended (4) apart.
PROBE_RC=0; PROBE_OUT=""
probe() {
  PROBE_OUT="$("$PEER_ASK" "$SESSION" --timeout "$PROBE_TIMEOUT" -m "ping" 2>&1)"; PROBE_RC=$?
  if [ "$PROBE_RC" -eq 0 ] && ! printf '%s\n' "$PROBE_OUT" | grep -qiF "explicitly stopped"; then
    return 0
  fi
  return 1
}
probe_desc() {
  case "$PROBE_RC" in
    0) if printf '%s\n' "$PROBE_OUT" | grep -qiF "explicitly stopped"; then echo "replied but the app session is stopped"; else echo "replied, idle prompt"; fi ;;
    2) echo "no such session" ;;
    3) echo "timeout after $PROBE_TIMEOUT s" ;;
    4) echo "session ended mid probe" ;;
    *) echo "peer-ask exit $PROBE_RC" ;;
  esac
}

# Wait up to $1 seconds, polling every $POLL, for the idle composer to be on
# screen. Returns 0 when seen, 1 on timeout.
wait_idle() {
  limit="$1"; waited=0
  while :; do
    if alive && capture | grep -qF "$IDLE_MARK"; then return 0; fi
    [ "$waited" -ge "$limit" ] && return 1
    sleep "$POLL"; waited=$((waited + POLL))
  done
}

# Step b: /new plus Enter, then the idle prompt, then a probe.
fresh_thread() {
  if ! alive; then log fresh-thread "skipped, no session to type into"; return 1; fi
  t send-keys -t "$SESSION" -l -- "/new" || { log fresh-thread "send-keys failed"; return 1; }
  sleep 0.4
  t send-keys -t "$SESSION" Enter || { log fresh-thread "send-keys Enter failed"; return 1; }
  if ! wait_idle "$THREAD_WAIT"; then log fresh-thread "no idle prompt within $THREAD_WAIT s"; return 1; fi
  if probe; then log fresh-thread "healthy ($(probe_desc))"; return 0; fi
  log fresh-thread "still unhealthy ($(probe_desc))"
  return 1
}

# Step c: kill (if present), launch through the xbar script, wait, probe.
relaunch() {
  if alive; then
    t kill-session -t "=$SESSION" || { log relaunch "kill-session failed"; return 1; }
    waited=0
    while alive; do
      [ "$waited" -ge 10 ] && { log relaunch "session still present 10 s after kill"; return 1; }
      sleep 1; waited=$((waited + 1))
    done
    log relaunch "killed"
  else
    log relaunch "no session to kill, launching"
  fi
  [ -x "$LAUNCHER" ] || { log relaunch "launcher missing: $LAUNCHER"; return 1; }
  "$OPEN_BIN" -a Terminal "$LAUNCHER" || { log relaunch "open -a Terminal failed"; return 1; }
  if ! wait_idle "$RELAUNCH_WAIT"; then
    log relaunch "no idle prompt within $RELAUNCH_WAIT s (sessions now: $(t list-sessions -F '#{session_name}' 2>/dev/null | tr '\n' ' '))"
    return 1
  fi
  if probe; then log relaunch "healthy ($(probe_desc))"; return 0; fi
  log relaunch "launched but unhealthy ($(probe_desc))"
  return 1
}

# ---- main ------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  echo "peer-refresh: DRY RUN for '$SESSION' (allowlisted). Would run, in order, stopping at the first healthy probe:"
  if [ "$RELAUNCH" -eq 1 ]; then echo "  a) probe and b) fresh thread: skipped (--relaunch)"; elif [ "$FORCE_THREAD" -eq 1 ]; then echo "  a) probe: skipped (--force-thread)"; else echo "  a) probe: $PEER_ASK $SESSION --timeout $PROBE_TIMEOUT -m ping"; fi
  echo "  b) fresh thread: send-keys -l /new, Enter; wait up to $THREAD_WAIT s for '$IDLE_MARK'; probe"
  echo "  c) relaunch: kill-session -t =$SESSION; open -a Terminal \"$LAUNCHER\"; wait up to $RELAUNCH_WAIT s; probe"
  echo "  log: $LOG"
  exit 0
fi

if [ "$RELAUNCH" -eq 1 ]; then
  log probe "skipped (--relaunch)"
  log fresh-thread "skipped (--relaunch)"
  relaunch && exit 0
  exit 2
fi

if [ "$FORCE_THREAD" -eq 1 ]; then
  log probe "skipped (--force-thread)"
  if alive; then
    fresh_thread && exit 0
  else
    log fresh-thread "skipped, no session"
  fi
  relaunch && exit 0
  exit 2
fi

if probe; then
  log probe "healthy ($(probe_desc))"
  exit 0
fi
case "$PROBE_RC" in
  3)
    # Busy, not broken. A fresh thread or a kill here would destroy real work.
    log probe "busy ($(probe_desc)); nothing touched, use --force-thread if it is hung"
    exit 3 ;;
  2|4)
    log probe "$(probe_desc)"
    relaunch && exit 0
    exit 2 ;;
  *)
    log probe "unhealthy ($(probe_desc))"
    fresh_thread && exit 0
    relaunch && exit 0
    exit 2 ;;
esac
