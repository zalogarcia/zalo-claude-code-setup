#!/bin/bash
# Tests for peer-refresh.sh. A fake tmux, a fake open and a fake defaults sit
# first on PATH and record every call in a scratch dir, so the script's
# escalation logic is asserted call by call and no real session, app or plugin
# cache is ever touched. Timings are cut to seconds through the PEER_REFRESH_*
# overrides.
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
grep -qF 'open -g -a ChatGPT' "$S" && ok "plugin cache check opens ChatGPT in the background (-g)" || bad "cache check open is not -g -a ChatGPT"
grep -qF -- '--check' "$S" && ok "blocking prompt check goes through peer-ask.sh --check" || bad "no peer-ask --check call"
! grep -qF 'open -a Terminal' "$S" && ok "no bare open -a Terminal left (a relaunch never takes focus)" || bad "bare open -a Terminal in the script"
grep -qF '"$OPEN_BIN" -g -a Terminal "$LAUNCHER"' "$S" && ok "relaunch opens Terminal with -g" || bad "relaunch open is not -g -a Terminal"

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
    if [ "$last" = "Enter" ]; then echo 0 > "$S/caps"; [ -f "$S/fresh" ] && touch "$S/fresh_entered"; else
      printf '%s\n' "$last" >> "$S/typed"
      [ "$last" = "/new" ] && touch "$S/fresh"
      [ "$last" = "ping" ] && [ "$(cat "$S/mode")" = "panel-on-ping" ] && touch "$S/panel"
    fi
    exit 0 ;;
  capture-pane)
    [ -f "$S/alive" ] || exit 1
    healthy() { echo "• pong"; echo "› Ask Codex to do anything"; echo "  gpt-6-astra default"; }
    stopped() { echo "■ This application session has been explicitly stopped by the user for this turn"; echo "› Ask Codex to do anything"; }
    # the three startup panels seen or found on 2026-09-23 (text from the live
    # pane and the Codex 0.154.0 binary)
    hooks_panel() { echo "› Ask Codex to do anything"; echo "Hooks need review"; echo "5 hooks need review before they can run."; echo "Press t to trust all; enter to review hooks; esc to close"; }
    update_modal() { echo "✨ Update available! 0.154.0 -> 0.156.1"; echo "Release notes: https://github.com/openai/codex/releases/latest"; echo "› 1. Update now (runs brew upgrade --cask codex)"; echo "  2. Skip"; echo "  3. Skip until next version"; echo "Press enter to continue"; }
    migrate_modal() { echo "Choose how you'd like Codex to proceed."; echo "› Try new model"; echo "  Use existing model"; echo "Press enter to continue"; }
    # panels that are on screen whatever the capture count
    case "$mode" in
      hooks-prompt) hooks_panel; exit 0 ;;
      panel-on-ping) [ -f "$S/panel" ] && { hooks_panel; exit 0; } ;;
      update-after-relaunch|stopped-then-update) [ -f "$S/relaunched" ] && { update_modal; exit 0; } ;;
      migrate-after-new) [ -f "$S/fresh_entered" ] && { migrate_modal; exit 0; } ;;
      # the composer draws first and the hooks panel opens half a second after
      # the relaunch, i.e. after the idle wait first sees the composer
      late-panel) if [ -f "$S/relaunched_at" ] && perl -MTime::HiRes=time -e 'exit(time - $ARGV[0] >= 0.5 ? 0 : 1)' "$(cat "$S/relaunched_at")"; then hooks_panel; exit 0; fi ;;
      # the passive banner Codex prints on every start while an update is
      # dismissed: NOT a prompt, the probe must go through
      passive-banner) echo "✨ Update available! 0.154.0 -> 0.156.1"; echo "Run brew upgrade --cask codex to update." ;;
    esac
    n=$(cat "$S/caps" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$S/caps"
    # the first capture after Enter is the baseline peer-ask takes: still typing
    if [ "$n" -lt 2 ]; then echo "• typing"; echo "› working"; exit 0; fi
    case "$mode" in
      healthy) healthy ;;
      busy) echo "• Working (12s • esc to interrupt)" ;;
      stopped-until-new) if [ -f "$S/fresh" ]; then healthy; else stopped; fi ;;
      stopped-until-relaunch) if [ -f "$S/relaunched" ]; then healthy; else stopped; fi ;;
      stopped-then-update) stopped ;;
      *) healthy ;;
    esac
    exit 0 ;;
  *) exit 0 ;;
esac
SHIM
cat > "$BIN/open" <<'SHIM'
#!/bin/bash
# fake open: records the call. "open -g -a ChatGPT" is the plugin cache
# check: it writes the app's version directory into the fake cache when the
# case says the app refreshes it. Anything else (open -g -a Terminal <launcher>)
# "launches" the session unless mode is never-up.
S="$SHIM_STATE"
printf 'open %s\n' "$*" >> "$S/calls.log"
if [ "$*" = "-g -a ChatGPT" ]; then
  [ -f "$S/cache_refreshes" ] && mkdir -p "$S/cua/$(cat "$S/app_version")"
  exit 0
fi
[ "$(cat "$S/mode")" = "never-up" ] && exit 0
touch "$S/alive" "$S/relaunched"; rm -f "$S/fresh" "$S/fresh_entered"; echo 0 > "$S/caps"
perl -MTime::HiRes=time -e 'printf "%.3f\n", time' > "$S/relaunched_at"
exit 0
SHIM
cat > "$BIN/defaults" <<'SHIM'
#!/bin/bash
# fake defaults: records the call, prints the case's ChatGPT app version.
S="$SHIM_STATE"
printf 'defaults %s\n' "$*" >> "$S/calls.log"
[ -f "$S/app_version" ] || exit 1
cat "$S/app_version"
SHIM
chmod +x "$BIN/tmux" "$BIN/open" "$BIN/defaults"

# run <name> <mode> <alive:0|1> <args...>; leaves RC, CALLS, LOG, OUT set.
# The plugin cache case comes from the caller's environment: APPV (the ChatGPT
# version; "none" = unreadable), CACHEV (space separated cache directory names;
# empty = no cache) and CACHE_REFRESH=1 (the app writes its directory when
# opened). Default: app and cache both at 26.917.51856.
run() {
  name="$1"; mode="$2"; alive="$3"; shift 3
  # Never fall through to the real multiplexer: without the shim in front of
  # PATH the script under test would act on the live session.
  [ -x "$BIN/tmux" ] && [ -x "$BIN/open" ] && [ -x "$BIN/defaults" ] || { echo "run $name: shim missing under $BIN, refusing to touch the real session" >&2; exit 1; }
  ST="$ROOT/$name"; mkdir -p "$ST/cua"; echo "$mode" > "$ST/mode"; : > "$ST/calls.log"
  [ "$alive" = 1 ] && touch "$ST/alive"
  [ "${APPV-26.917.51856}" = none ] || echo "${APPV-26.917.51856}" > "$ST/app_version"
  for d in ${CACHEV-26.917.51856}; do mkdir -p "$ST/cua/$d"; done
  [ "${CACHE_REFRESH:-0}" = 1 ] && touch "$ST/cache_refreshes"
  OUT="$(SHIM_STATE="$ST" PATH="$BIN:$PATH" PEER_REFRESH_LOG="$ST/refresh.log" \
    PEER_REFRESH_PROBE_TIMEOUT=12 PEER_REFRESH_THREAD_WAIT=4 PEER_REFRESH_RELAUNCH_WAIT=6 PEER_REFRESH_POLL=1 \
    PEER_REFRESH_CHATGPT_APP="$ST/ChatGPT.app" PEER_REFRESH_CUA_CACHE="$ST/cua" PEER_REFRESH_CACHE_WAIT=3 \
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
printf '%s' "$OUT" | grep -qF '5 blocking prompt on screen' && ok "usage text documents exit 5" || bad "usage text lacks exit 5: $OUT"
run usage2 healthy 1 codex-bare --bogus
[ $RC -eq 1 ] && [ -z "$CALLS" ] && ok "unknown flag -> exit 1, nothing touched" || bad "unknown flag rc=$RC"

# 5. dry run: allowlisted, prints the plan, touches nothing
run dry healthy 1 codex-bare --dry-run
[ $RC -eq 0 ] && ok "dry run -> exit 0" || bad "dry run rc=$RC"
! printf '%s\n' "$CALLS" | grep -qvE '^(defaults read .*)?$' && ok "dry run made no tmux or open calls (only the version read)" || bad "dry run calls: $CALLS"
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
has '^defaults read ' && ok "healthy: the plugin cache check ran (every run)" || bad "healthy: no plugin cache check"
printf '%s\n' "$LOG" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}[+-][0-9]{4} codex-bare probe healthy .* reason: shim test$' && ok "log line: timestamp, session, step, outcome, reason" || bad "log line shape: $LOG"
[ "$(printf '%s\n' "$LOG" | grep -c .)" -eq 2 ] && printf '%s\n' "$LOG" | head -1 | grep -q 'plugin-cache current' && ok "two log lines: the plugin cache check, then the probe" || bad "log lines: $LOG"

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
has '^open -g -a Terminal /Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-codex-bare.sh$' && ok "relaunched via open -g -a Terminal + the xbar launcher" || bad "launcher call missing: $CALLS"
n=$(first_line_matching '/new'); k=$(first_line_matching '^kill-session'); o=$(first_line_matching '^open ')
[ "$n" -lt "$k" ] && [ "$k" -lt "$o" ] && ok "order: /new, then kill, then launch" || bad "order: /new@$n kill@$k open@$o"
[ "$(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')" -eq 3 ] && ok "three probes: initial, after /new, after relaunch" || bad "ping count: $(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')"
printf '%s\n' "$LOG" | grep -q "fresh-thread still unhealthy" && printf '%s\n' "$LOG" | grep -q "relaunch killed" && printf '%s\n' "$LOG" | grep -q "relaunch healthy" && ok "log: still unhealthy, killed, healthy" || bad "log: $LOG"

# 11. no session at all -> skip /new and the kill, launch, healthy
run none healthy 0 codex-bare
[ $RC -eq 0 ] && ok "no session -> launch -> exit 0" || bad "no session rc=$RC ($OUT)"
! has '/new' && ok "no session: /new skipped" || bad "no session: /new sent"
! has '^kill-session' && ok "no session: nothing to kill" || bad "no session: kill-session called"
has '^open -g -a Terminal ' && ok "no session: launcher called" || bad "no session: launcher not called"
printf '%s\n' "$LOG" | grep -q "probe no such session" && ok "log: no such session" || bad "log: $LOG"

# 12. relaunch failed -> exit 2
run dead never-up 0 codex-bare
[ $RC -eq 2 ] && ok "session never comes up -> exit 2" || bad "never-up rc=$RC ($OUT)"
printf '%s\n' "$LOG" | grep -q "relaunch no idle prompt within" && ok "log: relaunch failed with the wait" || bad "log: $LOG"

# 13. --relaunch on a HEALTHY session: no probe first, no /new, kill and relaunch outright
run relaunch healthy 1 codex-bare --relaunch --reason "launcher changed"
[ $RC -eq 0 ] && ok "--relaunch -> exit 0" || bad "--relaunch rc=$RC ($OUT)"
has 'kill-session -t =codex-bare' && ok "--relaunch: kill-session on the exact name" || bad "--relaunch: no kill"
has '^open -g -a Terminal .*launch-codex-bare' && ok "--relaunch: relaunched via the launcher" || bad "--relaunch: no launch"
! printf '%s\n' "$CALLS" | grep -q -- '-l -- /new' && ok "--relaunch: /new never typed" || bad "--relaunch typed /new"
[ "$(printf '%s\n' "$CALLS" | grep -c -- '-l -- ping')" -eq 1 ] && ok "--relaunch: one probe, after the relaunch" || bad "ping count under --relaunch"
[ "$(first_line_matching 'kill-session')" -lt "$(first_line_matching 'l -- ping')" ] && ok "--relaunch: kill before the probe" || bad "--relaunch order"
printf '%s\n' "$LOG" | grep -q "probe skipped (--relaunch)" && printf '%s\n' "$LOG" | grep -q "fresh-thread skipped (--relaunch)" && ok "log: probe and fresh-thread skipped (--relaunch)" || bad "log: $LOG"

# 14. blocking prompts (2026-09-23). Every case: exit 5, the log names the
#     prompt, and nothing is typed into the panel.
sends() { printf '%s\n' "$CALLS" | grep -c '^send-keys'; }
# after <regex>: the send-keys calls recorded after the first call matching it
sends_after() { printf '%s\n' "$CALLS" | awk -v re="$1" 'f && /^send-keys/ {c++} $0 ~ re {f=1} END {print c+0}'; }

# 14a. default path: the hooks review panel is up when the probe starts
run blk-probe hooks-prompt 1 codex-bare --reason "shim test"
[ $RC -eq 5 ] && ok "hooks panel at the probe -> exit 5" || bad "hooks probe rc=$RC ($OUT)"
[ "$(sends)" -eq 0 ] && ok "hooks panel at the probe: zero send-keys (no ping, no Enter)" || bad "hooks probe typed: $CALLS"
! has '^kill-session' && ! has '^open ' && ok "hooks panel at the probe: no kill, no relaunch" || bad "hooks probe escalated: $CALLS"
printf '%s\n' "$LOG" | grep -q 'probe blocked by the Codex hooks review prompt (saw "hooks need review"), on screen: Hooks need review; nothing typed into it, a human must answer it' && ok "log names the hooks review prompt and the pane line" || bad "log: $LOG"
printf '%s' "$OUT" | grep -q 'blocked by the Codex hooks review prompt' && ok "stdout names the hooks review prompt" || bad "stdout: $OUT"

# 14b. fresh-thread path: --force-thread onto the hooks panel types no /new
run blk-thread hooks-prompt 1 codex-bare --force-thread
[ $RC -eq 5 ] && ok "--force-thread onto the hooks panel -> exit 5" || bad "force-thread hooks rc=$RC ($OUT)"
[ "$(sends)" -eq 0 ] && ok "--force-thread onto the hooks panel: /new never typed" || bad "force-thread hooks typed: $CALLS"
! has '^kill-session' && ! has '^open ' && ok "--force-thread onto the hooks panel: no relaunch (the panel comes back on every start)" || bad "force-thread hooks escalated: $CALLS"
printf '%s\n' "$LOG" | grep -q 'fresh-thread blocked by the Codex hooks review prompt (saw "hooks need review"), on screen: Hooks need review; /new not typed' && ok "log: fresh-thread blocked, names the prompt" || bad "log: $LOG"

# 14c. fresh-thread path: /new opens a model migration prompt
run blk-new migrate-after-new 1 codex-bare --force-thread
[ $RC -eq 5 ] && ok "a Press enter prompt after /new -> exit 5" || bad "migrate rc=$RC ($OUT)"
[ "$(sends_after '-l -- /new')" -eq 1 ] && ok "after /new only its own Enter went in (no ping)" || bad "sends after /new: $(sends_after '-l -- /new') ($CALLS)"
! has '^kill-session' && ! has '^open ' && ok "Press enter prompt after /new: no relaunch" || bad "migrate escalated: $CALLS"
printf '%s\n' "$LOG" | grep -q 'fresh-thread blocked by a "Press enter to" prompt (saw "Press enter to")' && ok "log names the Press enter prompt" || bad "log: $LOG"

# 14d. relaunch path: --relaunch comes up on the update prompt
run blk-relaunch update-after-relaunch 1 codex-bare --relaunch
[ $RC -eq 5 ] && ok "update prompt after --relaunch -> exit 5" || bad "update relaunch rc=$RC ($OUT)"
has '^open -g -a Terminal ' && ok "update prompt after --relaunch: the relaunch itself ran" || bad "no launch: $CALLS"
[ "$(sends)" -eq 0 ] && ok "update prompt after --relaunch: zero send-keys (Update now is never picked)" || bad "update relaunch typed: $CALLS"
printf '%s\n' "$LOG" | grep -qF 'relaunch blocked by the Codex update prompt (saw "Update now (runs"), on screen: › 1. Update now (runs brew upgrade --cask codex); nothing typed' && ok "log names the update prompt and the pane line" || bad "log: $LOG"

# 14e. escalation: stopped, /new does not help, the relaunch lands on the update prompt
run blk-escalate stopped-then-update 1 codex-bare
[ $RC -eq 5 ] && ok "escalation ending on the update prompt -> exit 5" || bad "escalation rc=$RC ($OUT)"
[ "$(sends_after '^open -g -a Terminal')" -eq 0 ] && ok "escalation: nothing typed after the relaunch" || bad "typed after relaunch: $CALLS"
printf '%s\n' "$LOG" | grep -q 'relaunch blocked by the Codex update prompt' && ok "log: relaunch blocked by the update prompt" || bad "log: $LOG"

# 14f. the composer draws first and the hooks panel opens 0.5 s after the
#      relaunch: the extra poll after the composer shows catches it before the
#      probe types (without that poll, ping went in and only the check before
#      Enter stopped it)
run blk-late late-panel 1 codex-bare --relaunch
[ $RC -eq 5 ] && ok "late hooks panel after a relaunch -> exit 5" || bad "late panel rc=$RC ($OUT)"
[ "$(sends)" -eq 0 ] && ok "late hooks panel: the probe never typed" || bad "late panel typed: $CALLS"
printf '%s\n' "$LOG" | grep -q 'relaunch blocked by the Codex hooks review prompt' && ok "log: relaunch blocked by the late hooks panel" || bad "log: $LOG"

# 14g2. the panel opens while "ping" is going in: Enter is never pressed, and
#       the log says the ping is in the pane rather than "nothing typed"
run blk-midping panel-on-ping 1 codex-bare
[ $RC -eq 5 ] && ok "panel opens mid ping -> exit 5" || bad "mid ping rc=$RC ($OUT)"
has '^send-keys -t codex-bare -l -- ping$' && ! has '^send-keys -t codex-bare Enter$' && ok "panel opens mid ping: ping typed, Enter never pressed" || bad "mid ping calls: $CALLS"
printf '%s\n' "$LOG" | grep -q 'probe blocked by the Codex hooks review prompt .*; the ping is in the pane but Enter was not pressed, a human must answer it' && ok "log says the ping is in the pane, not nothing typed" || bad "log: $LOG"

# 14h. the check itself cannot run: fail closed, never type /new blind
BROKEN="$ROOT/broken"; mkdir -p "$BROKEN"; cp "$S" "$BROKEN/peer-refresh.sh"
printf '#!/bin/bash\nexit 126\n' > "$BROKEN/peer-ask.sh"; chmod +x "$BROKEN/peer-refresh.sh" "$BROKEN/peer-ask.sh"
S_REAL="$S"; S="$BROKEN/peer-refresh.sh"
run blk-broken healthy 1 codex-bare --force-thread
S="$S_REAL"
[ $RC -eq 5 ] && ok "broken prompt check -> exit 5 (fail closed)" || bad "broken check rc=$RC ($OUT)"
[ "$(sends)" -eq 0 ] && ok "broken prompt check: /new never typed" || bad "broken check typed: $CALLS"
printf '%s\n' "$LOG" | grep -q 'fresh-thread blocked by no screen check (peer-ask.sh --check exit 126' && ok "log: the failed check is named" || bad "log: $LOG"

# 14g. the passive update banner is not a prompt: the probe goes through
run passive passive-banner 1 codex-bare
[ $RC -eq 0 ] && ok "passive Update available banner -> healthy, exit 0" || bad "passive banner rc=$RC ($OUT)"
has '^send-keys -t codex-bare -l -- ping$' && ok "passive banner: ping typed" || bad "passive banner: no ping ($CALLS)"

# 15. plugin cache check on a --relaunch run
chatgpt_opens() { printf '%s\n' "$CALLS" | grep -c '^open -g -a ChatGPT$'; }

# 15a. app newer than the cache, the app refreshes it
APPV=26.918.100 CACHEV=26.917.51856 CACHE_REFRESH=1 run cache-newer healthy 1 codex-bare --relaunch --reason "cache test"
[ $RC -eq 0 ] && ok "app newer: relaunch still healthy, exit 0" || bad "cache newer rc=$RC ($OUT)"
[ "$(chatgpt_opens)" -eq 1 ] && ok "app newer: open -g -a ChatGPT called once" || bad "app newer: ChatGPT opens=$(chatgpt_opens) ($CALLS)"
g=$(first_line_matching '^open -g -a ChatGPT'); k=$(first_line_matching '^kill-session'); o=$(first_line_matching '^open -g -a Terminal')
[ -n "$g" ] && [ -n "$k" ] && [ -n "$o" ] && [ "$g" -lt "$k" ] && [ "$k" -lt "$o" ] && ok "app newer: ChatGPT opened before the kill and the launch" || bad "order: chatgpt@$g kill@$k launch@$o"
printf '%s\n' "$LOG" | grep -q 'plugin-cache stale (app 26.918.100, cache 26.917.51856), opening ChatGPT in the background reason: cache test' && ok "log: stale, with both versions" || bad "log: $LOG"
printf '%s\n' "$LOG" | grep -q 'plugin-cache refreshed to 26.918.100 after' && ok "log: refreshed" || bad "log: $LOG"

# 15b. app newer, the cache never refreshes: logged, the relaunch goes ahead
APPV=26.918.100 CACHEV=26.917.51856 run cache-stuck healthy 1 codex-bare --relaunch
[ $RC -eq 0 ] && has '^open -g -a Terminal ' && ok "cache never refreshes: relaunch still runs, exit 0" || bad "cache stuck rc=$RC ($OUT)"
[ "$(chatgpt_opens)" -eq 1 ] && ok "cache never refreshes: ChatGPT opened once" || bad "cache stuck opens=$(chatgpt_opens)"
printf '%s\n' "$LOG" | grep -q 'plugin-cache no 26.918.100 directory within 3 s, going on without a refresh' && ok "log: the wait ran out, the relaunch goes on" || bad "log: $LOG"

# 15c. app equal to the cache: no open
APPV=26.917.51856 CACHEV=26.917.51856 run cache-equal healthy 1 codex-bare --relaunch
[ $RC -eq 0 ] && [ "$(chatgpt_opens)" -eq 0 ] && ok "app equal to the cache: ChatGPT not opened" || bad "cache equal rc=$RC opens=$(chatgpt_opens)"
printf '%s\n' "$LOG" | grep -q 'plugin-cache current (app 26.917.51856, cache 26.917.51856)' && ok "log: current" || bad "log: $LOG"

# 15d. no cache directory at all: no open
APPV=26.917.51856 CACHEV="" run cache-missing healthy 1 codex-bare --relaunch
[ $RC -eq 0 ] && [ "$(chatgpt_opens)" -eq 0 ] && ok "cache missing: ChatGPT not opened" || bad "cache missing rc=$RC opens=$(chatgpt_opens)"
printf '%s\n' "$LOG" | grep -q 'plugin-cache skipped, no version directory under' && ok "log: cache missing, skipped" || bad "log: $LOG"

# 15e. versions compare as numbers, not text; non version names ("latest") are ignored
APPV=26.1000.2 CACHEV="26.999.1 26.917.51856 latest" run cache-numeric healthy 1 codex-bare --relaunch
[ "$(chatgpt_opens)" -eq 1 ] && printf '%s\n' "$LOG" | grep -q 'stale (app 26.1000.2, cache 26.999.1)' && ok "26.1000.2 is newer than 26.999.1 (numeric compare)" || bad "numeric compare: $LOG"
APPV=26.917.51856 CACHEV="26.901.100 26.917.51856 latest" run cache-several healthy 1 codex-bare --relaunch
[ "$(chatgpt_opens)" -eq 0 ] && printf '%s\n' "$LOG" | grep -q 'current (app 26.917.51856, cache 26.917.51856)' && ok "several cache dirs: the newest one is compared" || bad "several dirs: $LOG"

# 15f. no readable app version: no open
APPV=none run cache-noapp healthy 1 codex-bare --relaunch
[ $RC -eq 0 ] && [ "$(chatgpt_opens)" -eq 0 ] && printf '%s\n' "$LOG" | grep -q 'plugin-cache skipped, no ChatGPT version readable' && ok "no app version: skipped, not opened" || bad "no app rc=$RC: $LOG"

# 16. the plugin cache check runs on EVERY run, before the first step (until
#     2026-09-23 it ran only before a relaunch, so schedule #67's --force-thread
#     run skipped it whenever /new succeeded)
newflag() { printf '%s\n' "$CALLS" | grep -c -- '-l -- /new'; }
no_relaunch() { ! has '^kill-session' && ! has '^open -g -a Terminal'; }

# 16a. healthy --force-thread, app newer, the app refreshes the cache: ChatGPT
#      opened once, then kill and launch instead of /new
APPV=26.918.100 CACHEV=26.917.51856 CACHE_REFRESH=1 run every-force healthy 1 codex-bare --force-thread --reason "every run"
[ $RC -eq 0 ] && ok "force-thread, app newer, cache refreshed -> exit 0" || bad "every-force rc=$RC ($OUT)"
[ "$(chatgpt_opens)" -eq 1 ] && ok "force-thread, app newer: open -g -a ChatGPT once" || bad "every-force opens=$(chatgpt_opens) ($CALLS)"
g=$(first_line_matching '^open -g -a ChatGPT'); k=$(first_line_matching '^kill-session'); o=$(first_line_matching '^open -g -a Terminal')
[ -n "$g" ] && [ -n "$k" ] && [ -n "$o" ] && [ "$g" -lt "$k" ] && [ "$k" -lt "$o" ] && ok "force-thread, app newer: ChatGPT, then kill, then launch" || bad "order: chatgpt@$g kill@$k launch@$o"
[ "$(newflag)" -eq 0 ] && ok "force-thread, cache refreshed: /new not typed (the relaunch is the fresh thread)" || bad "every-force typed /new: $CALLS"
printf '%s\n' "$LOG" | head -1 | grep -q 'plugin-cache stale (app 26.918.100, cache 26.917.51856)' && ok "log: the check is the first line of the run" || bad "log: $LOG"
printf '%s\n' "$LOG" | grep -q 'plugin-cache refreshed to 26.918.100 after .*relaunch' && printf '%s\n' "$LOG" | grep -q 'fresh-thread skipped, the plugin cache was refreshed and only a relaunch loads it reason: every run' && printf '%s\n' "$LOG" | grep -q 'relaunch killed' && printf '%s\n' "$LOG" | grep -q 'relaunch healthy' && ok "log: refreshed, fresh-thread skipped, killed, healthy" || bad "log: $LOG"

# 16b. healthy --force-thread, versions equal: exactly as before (/new, no open)
APPV=26.917.51856 CACHEV=26.917.51856 run every-equal healthy 1 codex-bare --force-thread
[ $RC -eq 0 ] && [ "$(newflag)" -eq 1 ] && ok "force-thread, versions equal: /new, exit 0" || bad "every-equal rc=$RC ($CALLS)"
! has '^open ' && no_relaunch && ok "force-thread, versions equal: no open, no kill, no launch" || bad "every-equal calls: $CALLS"
printf '%s\n' "$LOG" | grep -q 'plugin-cache current (app 26.917.51856, cache 26.917.51856)' && ok "log: current, on a run with no relaunch" || bad "log: $LOG"

# 16c. healthy --force-thread, no cache directory: logged, no open, no relaunch
APPV=26.917.51856 CACHEV="" run every-nocache healthy 1 codex-bare --force-thread
[ $RC -eq 0 ] && [ "$(newflag)" -eq 1 ] && ! has '^open ' && no_relaunch && ok "force-thread, cache missing: /new only, no open, no relaunch" || bad "every-nocache rc=$RC ($CALLS)"
printf '%s\n' "$LOG" | grep -q 'plugin-cache skipped, no version directory under' && ok "log: cache missing" || bad "log: $LOG"

# 16d. healthy --force-thread, no readable app version: logged, no open
APPV=none run every-noapp healthy 1 codex-bare --force-thread
[ $RC -eq 0 ] && ! has '^open ' && no_relaunch && printf '%s\n' "$LOG" | grep -q 'plugin-cache skipped, no ChatGPT version readable' && ok "force-thread, no app version: logged, no open, no relaunch" || bad "every-noapp rc=$RC: $LOG"

# 16e. the cache wait runs out: never blocks, the run goes on exactly as before
APPV=26.918.100 CACHEV=26.917.51856 run every-stuck healthy 1 codex-bare --force-thread
[ $RC -eq 0 ] && ok "cache wait runs out -> run goes on, exit 0" || bad "every-stuck rc=$RC ($OUT)"
[ "$(chatgpt_opens)" -eq 1 ] && [ "$(newflag)" -eq 1 ] && no_relaunch && ok "cache wait runs out: ChatGPT opened once, then /new, no relaunch" || bad "every-stuck calls: $CALLS"
printf '%s\n' "$LOG" | grep -q 'plugin-cache no 26.918.100 directory within 3 s, going on without a refresh' && printf '%s\n' "$LOG" | grep -q 'fresh-thread healthy' && ok "log: the wait ran out, then fresh-thread healthy" || bad "log: $LOG"

# 16f. no flags, healthy probe, cache refreshed: the probe runs, then a relaunch
APPV=26.918.100 CACHEV=26.917.51856 CACHE_REFRESH=1 run every-default healthy 1 codex-bare
[ $RC -eq 0 ] && ok "healthy probe, cache refreshed -> relaunch -> exit 0" || bad "every-default rc=$RC ($OUT)"
g=$(first_line_matching '^open -g -a ChatGPT'); p=$(first_line_matching 'l -- ping'); k=$(first_line_matching '^kill-session')
[ -n "$g" ] && [ -n "$p" ] && [ -n "$k" ] && [ "$g" -lt "$p" ] && [ "$p" -lt "$k" ] && has '^open -g -a Terminal ' && ok "healthy probe, cache refreshed: ChatGPT before the probe, the probe before the kill" || bad "order: chatgpt@$g ping@$p kill@$k"
printf '%s\n' "$LOG" | grep -q 'probe healthy (replied, idle prompt), relaunching to load the refreshed plugin cache' && ok "log: healthy probe escalated to a relaunch" || bad "log: $LOG"

# 16g. no flags, stopped app session, cache refreshed: straight to the relaunch
APPV=26.918.100 CACHEV=26.917.51856 CACHE_REFRESH=1 run every-unhealthy stopped-until-relaunch 1 codex-bare
[ $RC -eq 0 ] && [ "$(newflag)" -eq 0 ] && has '^kill-session' && ok "unhealthy probe, cache refreshed: no /new, relaunch, exit 0" || bad "every-unhealthy rc=$RC ($CALLS)"

# 16h. no flags, BUSY, cache refreshed: still nothing touched, the log owes a relaunch
APPV=26.918.100 CACHEV=26.917.51856 CACHE_REFRESH=1 run every-busy busy 1 codex-bare
[ $RC -eq 3 ] && [ "$(chatgpt_opens)" -eq 1 ] && [ "$(newflag)" -eq 0 ] && no_relaunch && ok "busy, cache refreshed: exit 3, no /new, no kill, no launch" || bad "every-busy rc=$RC ($CALLS)"
printf '%s\n' "$LOG" | grep -q 'probe busy .*loads only after a relaunch (run --relaunch once it is idle)' && ok "log: busy, a relaunch is still owed" || bad "log: $LOG"

# 16i. dry run with the app newer: prints the check and today's versions, opens nothing
APPV=26.918.100 CACHEV=26.917.51856 CACHE_REFRESH=1 run every-dry healthy 1 codex-bare --force-thread --dry-run
[ $RC -eq 0 ] && ! printf '%s\n' "$CALLS" | grep -qvE '^(defaults read .*)?$' && [ ! -d "$ROOT/every-dry/cua/26.918.100" ] && [ -z "$LOG" ] && ok "dry run, app newer: no tmux, no open, no log, cache untouched" || bad "every-dry rc=$RC calls: $CALLS log: $LOG"
printf '%s' "$OUT" | grep -q '0) plugin cache check, every run' && printf '%s' "$OUT" | grep -q 'now: app 26.918.100 is newer than cache 26.917.51856' && printf '%s' "$OUT" | grep -qF 'open -g -a Terminal' && ok "dry run prints the every-run check, today's versions and the -g launch" || bad "dry run output: $OUT"

# The cleanup stays LAST. A case appended below the rm once ran against the real
# tmux and killed the live codex-bare session twice (2026-09-11); run() now
# refuses to start without the shim, so that shape fails loudly instead.
rm -rf "$ROOT"
echo "$pass/$((pass+fail)) passed"; [ $fail -eq 0 ]
