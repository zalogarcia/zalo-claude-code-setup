#!/bin/bash
# peer-refresh.sh: bring a named tmux session back to a healthy idle prompt.
#
#   ~/.claude/scripts/peer-refresh.sh <session> [--force-thread] [--relaunch] [--dry-run] [--reason "text"]
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
# First, on EVERY run (2026-09-23), the plugin cache check. When the ChatGPT app
# (CFBundleShortVersionString) is newer than the newest version directory under
# ~/.codex/plugins/cache/openai-bundled/unified-computer-use/, Computer Use fails
# in codex-bare ("CUA_REPL_ENABLED_SURFACES is required"), because only the
# running app rewrites that cache. The check reads both versions without
# touching the session; when the app is newer it runs open -g -a ChatGPT
# (background, no focus) and waits up to 60 s for the app's version directory.
# If it appears, the Codex already running has the old plugin loaded, so the run
# ends in (c) instead of stopping at a healthy (a) or (b): a relaunch is the one
# path proven to load a refreshed cache (09-23 08:39). A busy session is still
# left alone (exit 3). Equal versions, no cache, no readable app version and a
# directory that never appears are logged and the run goes on as before; the
# check never blocks. It used to run only before a relaunch, so schedule #67's
# --force-thread run skipped it whenever /new succeeded.
#
# Right after it, also on every run (2026-09-23 afternoon), the session age
# check. The ChatGPT app refreshes that cache by itself while it runs, and then
# the versions read equal while the Codex in the session still holds the plugin
# it loaded when it started. So the check compares the birth time of the newest
# version directory with the session's creation time (tmux #{session_created});
# a directory born more than AGE_MARGIN (5 s, for clock skew) after the session
# ends the run in (c) exactly like a refresh, a busy session still excepted.
# Birth time, not modify time: a new version always lands as a new directory,
# while a file replaced inside an existing one moves only its modify and change
# times (measured 09-23: the directory born 08:38:49, its .mcp.json replaced
# 08:38:52, which moved the directory's modify time and left its birth). An
# isolated same version re-add through ChatGPT's own codex app-server left all
# three unchanged. A same version install does recreate the directory, but the
# app's code installs a plugin that is current only when forced (its debug
# reload) or when its bundled content variant changed, and then one relaunch is
# right (read from the app bundle and its 09-10 log, bundled_plugin_install_
# skipped_current; a same version app relaunch has not been observed yet, and
# if it did recreate the directory the cost is one extra idle relaunch). A
# relaunch makes the session newer than the directory, so the next run does not
# relaunch again, and a relaunch owed by a busy run is recomputed and paid by
# the next idle run.
#
# Then three escalating steps, each verified before the next one runs:
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
#      attaches, so it needs a TTY) with open -g, so the new window never takes
#      focus from whoever is typing (a focused relaunch on 09-23 took stray
#      keystrokes), wait up to 90 s in 5 s polls for the idle prompt, probe
#      again. A session that never existed skips (b) and the kill.
#
# Blocking prompts (2026-09-23): no step types into a panel that takes the next
# keypress as its answer. The probe goes through peer-ask.sh, which refuses on
# its own; step (b) runs peer-ask.sh --check (it types nothing) before /new and
# again before its Enter; the idle waits check on every poll and once more one
# poll after the composer first shows. That morning the probe's ping plus Enter
# went into the Codex hooks review panel, and another picked "Update now" on
# the update prompt, which quit Codex. Trusting hooks and taking an update stay
# the owner's decisions, so the run stops with exit 5 and names the prompt and
# the pane line that matched. It does not relaunch to get past a prompt (both
# panels come back on every start); a prompt that appears on a session this run
# has just relaunched stops it the same way, after the "relaunch killed" line.
# If the check itself cannot run (peer-ask.sh missing or broken), that also
# stops the run with exit 5 rather than typing blind.
#
# Exit codes: 0 healthy, 1 refused (session not in the allowlist, or usage),
# 2 relaunch failed (still not healthy after step c), 3 busy (probe timed out on
# a session that was not forced; nothing touched), 5 blocked (a prompt that
# takes the next keypress as its answer is on screen, such as the Codex hooks
# review panel, the Codex update prompt or any "Press enter to" prompt, or the
# check could not run; Enter never goes into it, and the log line and stdout
# name it and say whether the probe's ping had already gone in). 4 is unused on purpose: peer-ask.sh's 4 means "session ended", and
# 5 means blocked in both.
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
# The plugin cache check's inputs, overridable only so the shim test never
# reads the real app or cache.
CHATGPT_APP="${PEER_REFRESH_CHATGPT_APP:-/Applications/ChatGPT.app}"
CUA_CACHE="${PEER_REFRESH_CUA_CACHE:-$HOME/.codex/plugins/cache/openai-bundled/unified-computer-use}"
CACHE_WAIT="${PEER_REFRESH_CACHE_WAIT:-60}"
# The session age check's clock skew margin, in seconds.
AGE_MARGIN=5

usage() {
  echo "usage: peer-refresh.sh <session> [--force-thread] [--relaunch] [--dry-run] [--reason \"text\"]" >&2
  echo "every run first checks the ChatGPT app against the Computer Use plugin cache, and the newest plugin directory's birth time against the session's creation time; when it refreshes a stale cache or the directory is newer than the session, the run ends in a relaunch (a busy session is left alone)" >&2
  echo "exit: 0 healthy, 1 refused or usage, 2 relaunch failed, 3 busy (nothing touched), 5 blocking prompt on screen (Enter never goes into it; the output names it)" >&2
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
DEFAULTS_BIN="$(command -v defaults || echo /usr/bin/defaults)"
# BSD stat by full path: a GNU stat earlier on PATH reads -f as filesystem mode.
STAT_BIN=/usr/bin/stat
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
    5) echo "blocked by $(block_name "$PROBE_OUT"); $(probe_typed)" ;;
    *) echo "peer-ask exit $PROBE_RC" ;;
  esac
}

# The prompt peer-ask.sh named in its "BLOCKED by <name>" line, plus the pane
# line that matched, so a false positive is visible in the log at a glance.
block_name() {
  name="$(printf '%s\n' "$1" | sed -n 's/^peer-ask: BLOCKED by //p' | head -1)"
  seen="$(printf '%s\n' "$1" | sed -n 's/^peer-ask: on screen: //p' | head -1)"
  printf '%s%s\n' "${name:-an unnamed blocking prompt}" "${seen:+, on screen: $seen}"
}

# What the probe put into the pane before it stopped: peer-ask.sh refuses before
# typing, or, when the panel opened while "ping" was going in, before Enter.
probe_typed() {
  if printf '%s\n' "$PROBE_OUT" | grep -qF 'Enter was NOT pressed'; then
    echo "the ping is in the pane but Enter was not pressed"
  else
    echo "nothing typed into it"
  fi
}

# Blocking prompt check through peer-ask.sh --check, which types nothing.
# 0 and BLOCK_DESC set when a prompt that would take a keypress as its answer
# is on screen, or when the check itself failed: a broken check must not read
# as "clear" and let /new plus Enter go in blind. Its exit 2 (no such session)
# is clear, since the session can vanish mid relaunch and the callers handle it.
BLOCK_DESC=""
blocked() {
  chk="$("$PEER_ASK" "$SESSION" --check 2>&1)"; chk_rc=$?
  case "$chk_rc" in
    0|2) return 1 ;;
    5) BLOCK_DESC="$(block_name "$chk")" ;;
    *) BLOCK_DESC="no screen check (peer-ask.sh --check exit $chk_rc, so nothing is typed blind)" ;;
  esac
  return 0
}

# Wait up to $1 seconds, polling every $POLL, for the idle composer to be on
# screen. Returns 0 when seen, 1 on timeout, 5 when a blocking prompt is on
# screen (BLOCK_DESC names it). A startup panel can open a moment after the
# composer first draws, so the composer only counts once a further poll still
# shows no blocking prompt.
wait_idle() {
  limit="$1"; waited=0
  while :; do
    if alive; then
      if blocked; then return 5; fi
      if capture | grep -qF "$IDLE_MARK"; then
        sleep "$POLL"
        if blocked; then return 5; fi
        return 0
      fi
    fi
    [ "$waited" -ge "$limit" ] && return 1
    sleep "$POLL"; waited=$((waited + POLL))
  done
}

# Step b: /new plus Enter, then the idle prompt, then a probe. Returns 0
# healthy, 5 blocked by a prompt (nothing more typed), 1 otherwise.
fresh_thread() {
  if ! alive; then log fresh-thread "skipped, no session to type into"; return 1; fi
  if blocked; then log fresh-thread "blocked by $BLOCK_DESC; /new not typed, a human must answer it"; return 5; fi
  t send-keys -t "$SESSION" -l -- "/new" || { log fresh-thread "send-keys failed"; return 1; }
  sleep 0.4
  if blocked; then log fresh-thread "blocked by $BLOCK_DESC after /new went in; Enter not pressed, a human must answer it"; return 5; fi
  t send-keys -t "$SESSION" Enter || { log fresh-thread "send-keys Enter failed"; return 1; }
  wait_idle "$THREAD_WAIT"; rc=$?
  if [ "$rc" -eq 5 ]; then log fresh-thread "blocked by $BLOCK_DESC after /new was sent; nothing typed into it, a human must answer it"; return 5; fi
  if [ "$rc" -ne 0 ]; then log fresh-thread "no idle prompt within $THREAD_WAIT s"; return 1; fi
  if probe; then log fresh-thread "healthy ($(probe_desc))"; return 0; fi
  if [ "$PROBE_RC" -eq 5 ]; then log fresh-thread "$(probe_desc), a human must answer it"; return 5; fi
  log fresh-thread "still unhealthy ($(probe_desc))"
  return 1
}

# Dotted numeric compare: 0 when $1 is a strictly higher version than $2.
version_gt() {
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}

# The ChatGPT app version and the newest numeric cache directory; either may be
# empty. Read only: the dry run calls this too.
APP_VER=""; CACHE_VER=""
newest_cache_ver() { ls -1 "$CUA_CACHE" 2>/dev/null | grep -E '^[0-9]+(\.[0-9]+)*$' | sort -V | tail -1; }
read_versions() {
  APP_VER="$("$DEFAULTS_BIN" read "$CHATGPT_APP/Contents/Info" CFBundleShortVersionString 2>/dev/null)"
  CACHE_VER="$(newest_cache_ver)"
}

# Every run, before the first step (see the header). Sets RELOAD=1 when this run
# refreshed the cache. Logs every step and never fails the run.
RELOAD=0
plugin_cache_check() {
  read_versions
  if [ -z "$APP_VER" ]; then log plugin-cache "skipped, no ChatGPT version readable at $CHATGPT_APP"; return 0; fi
  if [ -z "$CACHE_VER" ]; then log plugin-cache "skipped, no version directory under $CUA_CACHE (app $APP_VER)"; return 0; fi
  if ! version_gt "$APP_VER" "$CACHE_VER"; then log plugin-cache "current (app $APP_VER, cache $CACHE_VER)"; return 0; fi
  log plugin-cache "stale (app $APP_VER, cache $CACHE_VER), opening ChatGPT in the background"
  if ! "$OPEN_BIN" -g -a ChatGPT; then log plugin-cache "open -g -a ChatGPT failed, going on without a refresh"; return 0; fi
  waited=0
  while [ ! -d "$CUA_CACHE/$APP_VER" ]; do
    if [ "$waited" -ge "$CACHE_WAIT" ]; then log plugin-cache "no $APP_VER directory within $CACHE_WAIT s, going on without a refresh"; return 0; fi
    sleep "$POLL"; waited=$((waited + POLL))
  done
  RELOAD=1
  log plugin-cache "refreshed to $APP_VER after $waited s; a running Codex keeps the old plugin until a relaunch"
  return 0
}

# The session age check's reading (see the header). Read only: the dry run
# calls this too. Sets AGE_VER, AGE_BORN and AGE_CREATED (epoch seconds) and
# AGE_STATE: newer, current, nodir, nosession, or unreadable (AGE_WHY says which).
# The target needs the trailing colon: on tmux 3.7b, -t =name prints an empty
# #{session_created} with exit 0, while -t =name: prints the time (measured).
AGE_VER=""; AGE_BORN=""; AGE_CREATED=""; AGE_STATE=""; AGE_WHY=""
plugin_age_read() {
  AGE_VER="$(newest_cache_ver)"; AGE_BORN=""; AGE_CREATED=""; AGE_WHY=""
  if [ -z "$AGE_VER" ]; then AGE_STATE=nodir; return; fi
  if ! alive; then AGE_STATE=nosession; return; fi
  AGE_BORN="$("$STAT_BIN" -f %B "$CUA_CACHE/$AGE_VER" 2>/dev/null)"
  AGE_CREATED="$(t display-message -p -t "=$SESSION:" '#{session_created}' 2>/dev/null)"
  AGE_STATE=unreadable
  case "$AGE_BORN" in ''|*[!0-9]*) AGE_WHY="no birth time readable for $CUA_CACHE/$AGE_VER"; return ;; esac
  case "$AGE_CREATED" in ''|*[!0-9]*) AGE_WHY="no session creation time readable from tmux"; return ;; esac
  if [ "$AGE_BORN" -gt $((AGE_CREATED + AGE_MARGIN)) ]; then AGE_STATE=newer; else AGE_STATE=current; fi
}
ts_of() { date -r "$1" +%Y-%m-%dT%H:%M:%S 2>/dev/null || echo "$1"; }
age_times() { echo "plugin $AGE_VER created $(ts_of "$AGE_BORN"), session created $(ts_of "$AGE_CREATED")"; }

# Every run, right after the plugin cache check. Sets RELOAD=1 when the newest
# plugin directory is newer than the session. Logs its reading, never fails.
session_age_check() {
  plugin_age_read
  case "$AGE_STATE" in
    nodir) log plugin-age "skipped, no version directory under $CUA_CACHE" ;;
    nosession) log plugin-age "skipped, no session" ;;
    unreadable) log plugin-age "skipped, $AGE_WHY" ;;
    current) log plugin-age "current ($(age_times))" ;;
    newer)
      RELOAD=1
      log plugin-age "newer than the session ($(age_times)); a running Codex keeps the plugin it started with until a relaunch" ;;
  esac
  return 0
}

# Step c: kill (if present), launch through the xbar script, wait, probe.
# Returns 0 healthy, 5 blocked by a prompt (no Enter into it), 1 otherwise.
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
  "$OPEN_BIN" -g -a Terminal "$LAUNCHER" || { log relaunch "open -g -a Terminal failed"; return 1; }
  wait_idle "$RELAUNCH_WAIT"; rc=$?
  if [ "$rc" -eq 5 ]; then log relaunch "blocked by $BLOCK_DESC; nothing typed into it, a human must answer it"; return 5; fi
  if [ "$rc" -ne 0 ]; then
    log relaunch "no idle prompt within $RELAUNCH_WAIT s (sessions now: $(t list-sessions -F '#{session_name}' 2>/dev/null | tr '\n' ' '))"
    return 1
  fi
  if probe; then log relaunch "healthy ($(probe_desc))"; return 0; fi
  if [ "$PROBE_RC" -eq 5 ]; then log relaunch "$(probe_desc), a human must answer it"; return 5; fi
  log relaunch "launched but unhealthy ($(probe_desc))"
  return 1
}

# ---- main ------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  read_versions
  if [ -z "$APP_VER" ]; then cache_now="no ChatGPT version readable, would log it and go on"
  elif [ -z "$CACHE_VER" ]; then cache_now="app $APP_VER, no cache directory, would log it and go on"
  elif version_gt "$APP_VER" "$CACHE_VER"; then cache_now="app $APP_VER is newer than cache $CACHE_VER: would open -g -a ChatGPT, and a refresh ends the run in c)"
  else cache_now="app $APP_VER, cache $CACHE_VER: current, nothing to do"; fi
  echo "peer-refresh: DRY RUN for '$SESSION' (allowlisted). Would run, in order, stopping at the first healthy probe:"
  echo "  0) plugin cache check, every run: ChatGPT.app version vs the newest dir under $CUA_CACHE; if the app is newer, open -g -a ChatGPT and wait up to $CACHE_WAIT s; if its dir appears, go on to c) instead of stopping at a healthy a) or b) (a busy session is still left alone)"
  echo "     now: $cache_now"
  plugin_age_read
  case "$AGE_STATE" in
    nodir) age_now="no version directory, would log it and go on" ;;
    nosession) age_now="no session, would log it and go on" ;;
    unreadable) age_now="$AGE_WHY, would log it and go on" ;;
    current) age_now="$(age_times): the session is newer, no relaunch needed" ;;
    newer) age_now="$(age_times): the plugin is newer than the session, would end the run in c) (a busy session is still left alone)" ;;
  esac
  echo "  0b) session age check, every run: the newest plugin directory's birth time vs the session's creation time; newer by more than $AGE_MARGIN s ends the run in c) like a refresh"
  echo "     now: $age_now"
  if [ "$RELAUNCH" -eq 1 ]; then echo "  a) probe and b) fresh thread: skipped (--relaunch)"; elif [ "$FORCE_THREAD" -eq 1 ]; then echo "  a) probe: skipped (--force-thread)"; else echo "  a) probe: $PEER_ASK $SESSION --timeout $PROBE_TIMEOUT -m ping"; fi
  echo "  b) fresh thread: send-keys -l /new, Enter; wait up to $THREAD_WAIT s for '$IDLE_MARK'; probe"
  echo "  c) relaunch: kill-session -t =$SESSION; open -g -a Terminal \"$LAUNCHER\" (background, no focus); wait up to $RELAUNCH_WAIT s; probe"
  echo "  every step: a blocking prompt on screen (peer-ask.sh --check) stops the run with exit 5, Enter never goes into it"
  echo "  log: $LOG"
  exit 0
fi

plugin_cache_check
session_age_check
RELOAD_NOTE="skipped, the plugin cache is newer than the running Codex and only a relaunch loads it"

if [ "$RELAUNCH" -eq 1 ]; then
  log probe "skipped (--relaunch)"
  log fresh-thread "skipped (--relaunch)"
  relaunch; rc=$?
  case "$rc" in 0|5) exit "$rc" ;; esac
  exit 2
fi

if [ "$FORCE_THREAD" -eq 1 ]; then
  log probe "skipped (--force-thread)"
  if [ "$RELOAD" -eq 1 ]; then
    log fresh-thread "$RELOAD_NOTE"
  elif alive; then
    fresh_thread; rc=$?
    case "$rc" in 0|5) exit "$rc" ;; esac
  else
    log fresh-thread "skipped, no session"
  fi
  relaunch; rc=$?
  case "$rc" in 0|5) exit "$rc" ;; esac
  exit 2
fi

if probe; then
  if [ "$RELOAD" -eq 1 ]; then
    log probe "healthy ($(probe_desc)), relaunching to load the newer plugin cache"
    relaunch; rc=$?
    case "$rc" in 0|5) exit "$rc" ;; esac
    exit 2
  fi
  log probe "healthy ($(probe_desc))"
  exit 0
fi
case "$PROBE_RC" in
  3)
    # Busy, not broken. A fresh thread or a kill here would destroy real work,
    # even when the plugin cache is newer than the session. The session age
    # check recomputes that on every run, so the next idle run pays the debt.
    if [ "$RELOAD" -eq 1 ]; then
      log probe "busy ($(probe_desc)); nothing touched, but a relaunch is owed: the plugin cache is newer than the running Codex and loads only after a relaunch (the next idle run relaunches)"
    else
      log probe "busy ($(probe_desc)); nothing touched, use --force-thread if it is hung"
    fi
    exit 3 ;;
  5)
    # A prompt waiting for an answer. Typing /new or relaunching would answer it
    # or bring it straight back; the owner decides.
    log probe "$(probe_desc), a human must answer it"
    exit 5 ;;
  2|4)
    log probe "$(probe_desc)"
    relaunch; rc=$?
    case "$rc" in 0|5) exit "$rc" ;; esac
    exit 2 ;;
  *)
    log probe "unhealthy ($(probe_desc))"
    if [ "$RELOAD" -eq 1 ]; then
      log fresh-thread "$RELOAD_NOTE"
    else
      fresh_thread; rc=$?
      case "$rc" in 0|5) exit "$rc" ;; esac
    fi
    relaunch; rc=$?
    case "$rc" in 0|5) exit "$rc" ;; esac
    exit 2 ;;
esac
