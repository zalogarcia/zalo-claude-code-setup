#!/bin/bash
# Tests for peer-refresh.sh. A fake tmux and a fake open sit first on PATH and
# record every call in a scratch dir, so the script's escalation logic is
# asserted call by call and no real session is ever touched. Timings are cut to
# seconds through the PEER_REFRESH_* overrides.
#
#   bash ~/.claude/scripts/peer-refresh.test.sh
S=~/.claude/scripts/peer-refresh.sh; pass=0; fail=0
ok() { pass=$((pass+1)); echo "ok   $1"; }; bad() { fail=$((fail+1)); echo "FAIL $1"; }
[ -x "$S" ] || { bad "peer-refresh.sh is not executable"; echo "0/1 passed"; exit 1; }

# 1. static: the script never sends a control key or an escape sequence to the pane
FORBID='send-prefix|(send-keys|send)[^|]*(-H|-X|Escape|BSpace|Tab|C-|M-|Up|Down|Left|Right|Home|End|PPage|NPage|IC|DC|F[0-9])'
if grep -nE "$FORBID" "$S" >/dev/null; then bad "control key send present in the script"; else ok "script sends only literal text and Enter"; fi
grep -qE 'kill-session -t "=\$SESSION"' "$S" && ok "kill-session targets the exact session name (= prefix)" || bad "kill-session is not exact match"
grep -qF 'launch-codex-bare.sh' "$S" && ok "relaunch goes through the xbar launcher" || bad "launcher path missing"
grep -qF '"$HOME/.claude/config/peer-refresh-allow.json"' "$S" && ok "allowlist path is fixed, not an env override" || bad "allowlist path"
# U+2012..U+2015 (figure dash, en dash, em dash, horizontal bar) as UTF-8 bytes, so this file carries none itself
dashes=0
for b in '\xe2\x80\x92' '\xe2\x80\x93' '\xe2\x80\x94' '\xe2\x80\x95'; do
  LC_ALL=C grep -q "$(printf "$b")" "$S" && dashes=1
done
[ "$dashes" -eq 0 ] && ok "no em or en dashes" || bad "em or en dash in the script"

# 2. the shim: fake tmux + fake open, driven by a mode file
ROOT="$(mktemp -d /tmp/peer-refresh-test.XXXXXX)"
BIN="$ROOT/bin"; mkdir -p "$BIN"
cat > "$BIN/tmux" <<'SHIM'
#!/bin/bash
# fake tmux: records argv, simulates one pane whose reply depends on $mode.
S="$SHIM_STATE"
printf '%s\n' "$*" >> "$S/calls.log"
cmd="$1"; shift
mode="$(cat "$S/mode")"
case "$cmd" in
  has-session) [ -f "$S/alive" ] ;;
  list-sessions) [ -f "$S/alive" ] && echo "codex-bare"; exit 0 ;;
  kill-session) rm -f "$S/alive" "$S/fresh"; echo killed >> "$S/events" ;;
  send-keys)
    [ -f "$S/alive" ] || exit 1
    last=""; for a in "$@"; do last="$a"; done
    if [ "$last" = "Enter" ]; then echo 0 > "$S/caps"; else
      printf '%s\n' "$last" >> "$S/typed"
      [ "$last" = "/new" ] && touch "$S/fresh"
    fi
    exit 0 ;;
  capture-pane)
    [ -f "$S/alive" ] || exit 1
    n=$(cat "$S/caps" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$S/caps"
    # the first capture after Enter is the baseline peer-ask takes: still typing
    if [ "$n" -lt 2 ]; then echo "• typing"; echo "› working"; exit 0; fi
    healthy() { echo "• pong"; echo "› Ask Codex to do anything"; echo "  gpt-6-astra default"; }
    stopped() { echo "■ This application session has been explicitly stopped by the user for this turn"; echo "› Ask Codex to do anything"; }
    case "$mode" in
      healthy) healthy ;;
      busy) echo "• Working (12s • esc to interrupt)" ;;
      stopped-until-new) if [ -f "$S/fresh" ]; then healthy; else stopped; fi ;;
      stopped-until-relaunch) if [ -f "$S/relaunched" ]; then healthy; else stopped; fi ;;
      *) healthy ;;
    esac
    exit 0 ;;
  *) exit 0 ;;
esac
SHIM
cat > "$BIN/open" <<'SHIM'
#!/bin/bash
# fake open: records the call; "launches" the session unless mode is never-up.
S="$SHIM_STATE"
printf 'open %s\n' "$*" >> "$S/calls.log"
[ "$(cat "$S/mode")" = "never-up" ] && exit 0
touch "$S/alive" "$S/relaunched"; rm -f "$S/fresh"; echo 0 > "$S/caps"
exit 0
SHIM
chmod +x "$BIN/tmux" "$BIN/open"

# run <name> <mode> <alive:0|1> <args...>; leaves RC, CALLS, LOG, OUT set
run() {
  name="$1"; mode="$2"; alive="$3"; shift 3
  # Never fall through to the real multiplexer: without the shim in front of
  # PATH the script under test would act on the live session.
  [ -x "$BIN/tmux" ] && [ -x "$BIN/open" ] || { echo "run $name: shim missing under $BIN, refusing to touch the real session" >&2; exit 1; }
  ST="$ROOT/$name"; mkdir -p "$ST"; echo "$mode" > "$ST/mode"; : > "$ST/calls.log"
  [ "$alive" = 1 ] && touch "$ST/alive"
  OUT="$(SHIM_STATE="$ST" PATH="$BIN:$PATH" PEER_REFRESH_LOG="$ST/refresh.log" \
    PEER_REFRESH_PROBE_TIMEOUT=12 PEER_REFRESH_THREAD_WAIT=4 PEER_REFRESH_RELAUNCH_WAIT=6 PEER_REFRESH_POLL=1 \
    "$S" "$@" 2>&1)"; RC=$?
  CALLS="$(cat "$ST/calls.log")"; LOG="$(cat "$ST/refresh.log" 2>/dev/null)"
}
has()  { printf '%s\n' "$CALLS" | grep -qE "$1"; }
first_line_matching() { printf '%s\n' "$CALLS" | grep -nE "$1" | head -1 | cut -d: -f1; }

# 3. refused before anything is touched: a session outside the allowlist
run refused healthy 1 delta-agents
[ $RC -eq 1 ] && ok "non allowlisted session -> exit 1" || bad "non allowlisted rc=$RC"
[ -z "$CALLS" ] && ok "refusal touched nothing (no tmux calls)" || bad "refusal made tmux calls: $CALLS"
[ -z "$LOG" ] && ok "refusal wrote no log line" || bad "refusal logged: $LOG"
printf '%s' "$OUT" | grep -q "REFUSED" && ok "refusal names the allowlist" || bad "refusal message: $OUT"

# 4. usage errors are refusals too
run usage healthy 1
[ $RC -eq 1 ] && [ -z "$CALLS" ] && ok "no session arg -> exit 1, nothing touched" || bad "no session arg rc=$RC"
run usage2 healthy 1 codex-bare --bogus
[ $RC -eq 1 ] && [ -z "$CALLS" ] && ok "unknown flag -> exit 1, nothing touched" || bad "unknown flag rc=$RC"

# 5. dry run: allowlisted, prints the plan, touches nothing
run dry healthy 1 codex-bare --dry-run
[ $RC -eq 0 ] && ok "dry run -> exit 0" || bad "dry run rc=$RC"
[ -z "$CALLS" ] && ok "dry run made no tmux or open calls" || bad "dry run calls: $CALLS"
printf '%s' "$OUT" | grep -q "launch-codex-bare.sh" && ok "dry run names the launcher" || bad "dry run output: $OUT"

# 6. step a: healthy at the probe -> done, nothing else
run a healthy 1 codex-bare --reason "shim test"
[ $RC -eq 0 ] && ok "healthy probe -> exit 0" || bad "healthy probe rc=$RC ($OUT)"
has '^has-session -t =codex-bare$' && ok "probe checked the exact session name" || bad "no exact has-session"
has '^send-keys -t codex-bare -l -- ping$' && ok "probe typed ping as literal text" || bad "ping not typed literally"
has '^send-keys -t codex-bare Enter$' && ok "probe pressed Enter separately" || bad "no separate Enter"
! has '/new' && ok "healthy: no /new sent" || bad "healthy: /new was sent"
! has '^kill-session' && ok "healthy: no kill-session" || bad "healthy: kill-session was called"
! has '^open ' && ok "healthy: no relaunch" || bad "healthy: open was called"
printf '%s\n' "$LOG" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}[+-][0-9]{4} codex-bare probe healthy .* reason: shim test$' && ok "log line: timestamp, session, step, outcome, reason" || bad "log line shape: $LOG"
[ "$(printf '%s\n' "$LOG" | grep -c .)" -eq 1 ] && ok "exactly one log line for one step" || bad "log lines: $LOG"

# 7. step a busy (probe timeout) -> exit 3, nothing touched beyond the probe
run busy busy 1 codex-bare
[ $RC -eq 3 ] && ok "busy probe -> exit 3" || bad "busy rc=$RC ($OUT)"
! has '/new' && ! has '^kill-session' && ! has '^open ' && ok "busy: no /new, no kill, no relaunch" || bad "busy touched the session: $CALLS"
printf '%s\n' "$LOG" | grep -q "probe busy" && ok "busy logged as busy" || bad "busy log: $LOG"

# 8. step b: probe replies but the app session is stopped -> /new fixes it
run b stopped-until-new 1 codex-bare
[ $RC -eq 0 ] && ok "stopped app session -> /new -> exit 0" || bad "step b rc=$RC ($OUT)"
has '^send-keys -t codex-bare -l -- /new$' && ok "/new typed as literal text" || bad "/new not typed literally"
p=$(first_line_matching 'ping'); n=$(first_line_matching '/new')
[ -n "$p" ] && [ -n "$n" ] && [ "$p" -lt "$n" ] && ok "probe ran before /new" || bad "order: ping@$p /new@$n"
[ "$(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')" -eq 2 ] && ok "probed again after /new" || bad "ping count: $(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')"
! has '^kill-session' && ! has '^open ' && ok "step b: no kill, no relaunch" || bad "step b escalated: $CALLS"
printf '%s\n' "$LOG" | grep -q "probe unhealthy (replied but the app session is stopped)" && ok "log names the stopped app session" || bad "log: $LOG"
printf '%s\n' "$LOG" | grep -q "fresh-thread healthy" && ok "log: fresh-thread healthy" || bad "log: $LOG"

# 9. --force-thread skips the probe and starts at /new
run force stopped-until-new 1 codex-bare --force-thread
[ $RC -eq 0 ] && ok "--force-thread -> exit 0" || bad "--force-thread rc=$RC ($OUT)"
firstsend="$(printf '%s\n' "$CALLS" | grep -E '^send-keys' | head -1)"
[ "$firstsend" = "send-keys -t codex-bare -l -- /new" ] && ok "--force-thread: first thing typed is /new" || bad "--force-thread first send: $firstsend"
[ "$(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')" -eq 1 ] && ok "--force-thread: one probe, after /new" || bad "ping count under --force-thread"
printf '%s\n' "$LOG" | grep -q "probe skipped (--force-thread)" && ok "log: probe skipped" || bad "log: $LOG"

# 10. step c: /new does not help -> kill, relaunch through the launcher, healthy
run c stopped-until-relaunch 1 codex-bare
[ $RC -eq 0 ] && ok "stopped after /new -> relaunch -> exit 0" || bad "step c rc=$RC ($OUT)"
has '^kill-session -t =codex-bare$' && ok "kill-session on the exact name" || bad "no exact kill-session"
has '^open -a Terminal /Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-codex-bare.sh$' && ok "relaunched via open -a Terminal + the xbar launcher" || bad "launcher call missing: $CALLS"
n=$(first_line_matching '/new'); k=$(first_line_matching '^kill-session'); o=$(first_line_matching '^open ')
[ "$n" -lt "$k" ] && [ "$k" -lt "$o" ] && ok "order: /new, then kill, then launch" || bad "order: /new@$n kill@$k open@$o"
[ "$(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')" -eq 3 ] && ok "three probes: initial, after /new, after relaunch" || bad "ping count: $(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')"
printf '%s\n' "$LOG" | grep -q "fresh-thread still unhealthy" && printf '%s\n' "$LOG" | grep -q "relaunch killed" && printf '%s\n' "$LOG" | grep -q "relaunch healthy" && ok "log: still unhealthy, killed, healthy" || bad "log: $LOG"

# 11. no session at all -> skip /new and the kill, launch, healthy
run none healthy 0 codex-bare
[ $RC -eq 0 ] && ok "no session -> launch -> exit 0" || bad "no session rc=$RC ($OUT)"
! has '/new' && ok "no session: /new skipped" || bad "no session: /new sent"
! has '^kill-session' && ok "no session: nothing to kill" || bad "no session: kill-session called"
has '^open -a Terminal ' && ok "no session: launcher called" || bad "no session: launcher not called"
printf '%s\n' "$LOG" | grep -q "probe no such session" && ok "log: no such session" || bad "log: $LOG"

# 12. relaunch failed -> exit 2
run dead never-up 0 codex-bare
[ $RC -eq 2 ] && ok "session never comes up -> exit 2" || bad "never-up rc=$RC ($OUT)"
printf '%s\n' "$LOG" | grep -q "relaunch no idle prompt within" && ok "log: relaunch failed with the wait" || bad "log: $LOG"

# 13. --relaunch on a HEALTHY session: no probe first, no /new, kill and relaunch outright
run relaunch healthy 1 codex-bare --relaunch --reason "launcher changed"
[ $RC -eq 0 ] && ok "--relaunch -> exit 0" || bad "--relaunch rc=$RC ($OUT)"
has 'kill-session -t =codex-bare' && ok "--relaunch: kill-session on the exact name" || bad "--relaunch: no kill"
has '^open -a Terminal .*launch-codex-bare' && ok "--relaunch: relaunched via the launcher" || bad "--relaunch: no launch"
! printf '%s\n' "$CALLS" | grep -q -- '-l -- /new' && ok "--relaunch: /new never typed" || bad "--relaunch typed /new"
[ "$(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')" -eq 1 ] && ok "--relaunch: one probe, after the relaunch" || bad "ping count under --relaunch"
[ "$(first_line_matching 'kill-session')" -lt "$(first_line_matching 'l -- ping')" ] && ok "--relaunch: kill before the probe" || bad "--relaunch order"
printf '%s\n' "$LOG" | grep -q "probe skipped (--relaunch)" && printf '%s\n' "$LOG" | grep -q "fresh-thread skipped (--relaunch)" && ok "log: probe and fresh-thread skipped (--relaunch)" || bad "log: $LOG"

# The cleanup stays LAST. A case appended below the rm once ran against the real
# tmux and killed the live codex-bare session twice (2026-09-11); run() now
# refuses to start without the shim, so that shape fails loudly instead.
rm -rf "$ROOT"
echo "$pass/$((pass+fail)) passed"; [ $fail -eq 0 ]
