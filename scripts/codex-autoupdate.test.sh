#!/bin/bash
# Tests for codex-autoupdate.sh. Fake brew, codex, pgrep, node (bg.mjs ps),
# tmux, lsof, curl, peer-refresh.sh and codex-run.sh record every call in a
# scratch dir, driven by per case state files, so nothing real is upgraded,
# relaunched or sent to Telegram.
#
#   bash ~/.claude/scripts/codex-autoupdate.test.sh
S="${CODEX_AUTOUPDATE_UNDER_TEST:-$HOME/.claude/scripts/codex-autoupdate.sh}"; pass=0; fail=0
ok() { pass=$((pass+1)); echo "ok   $1"; }; bad() { fail=$((fail+1)); echo "FAIL $1"; }
[ -x "$S" ] || { bad "codex-autoupdate.sh is not executable"; echo "0/1 passed"; exit 1; }

# 1. static
grep -qF 'BREW="${CODEX_AUTOUPDATE_BREW:-/opt/homebrew/bin/brew}"' "$S" && ok "brew is the ARM Homebrew by full path" || bad "brew path"
! grep -nE '(^|[^-])--form[ =]|curl[^#]* -F ' "$S" >/dev/null && ok "curl sends text with --form-string only (no -F, no --form)" || bad "curl -F or --form in the script"
! grep -qi 'editMessage' "$S" && ok "no editMessage call" || bad "editMessage in the script"
! grep -qE 'npm (i|install)' "$S" && ok "never installs codex through npm" || bad "npm install in the script"
grep -qF -- '--relaunch --reason "codex upgraded to $installed"' "$S" && ok "codex-bare relaunch goes through peer-refresh.sh --relaunch" || bad "relaunch call"
dashes=0
for b in '\xe2\x80\x92' '\xe2\x80\x93' '\xe2\x80\x94' '\xe2\x80\x95'; do LC_ALL=C grep -q "$(printf "$b")" "$S" && dashes=1; done
[ "$dashes" -eq 0 ] && ok "no em or en dashes" || bad "em or en dash in the script"

# 2. the fakes
ROOT="$(mktemp -d /tmp/codex-autoupdate-test.XXXXXX)"
BIN="$ROOT/bin"; mkdir -p "$BIN"
cat > "$BIN/brew" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'brew %s\n' "$*" >> "$S/calls.log"
case "$1" in
  update) exit 0 ;;
  info) [ -f "$S/info_garbage" ] && { echo "Error: no such cask" >&2; exit 1; }
        [ -f "$S/busy_after_info" ] && echo "5151 codex exec --skip-git-repo-check -C /tmp/y" > "$S/exec_running"
        printf '{"casks":[{"token":"codex","version":"%s","installed":"%s"}]}\n' "$(cat "$S/latest")" "$(cat "$S/installed")" ;;
  upgrade|reinstall)
    if [ "$1" = upgrade ] && [ -f "$S/upgrade_hangs" ]; then
      sleep 30 & echo $! > "$S/hang_child"; echo $$ > "$S/hang_parent"; wait; exit 0
    fi
    # like brew.rb: rescue Exception catches SIGTERM, then exit 1
    if [ "$1" = upgrade ] && [ -f "$S/upgrade_hangs_traps" ]; then
      trap 'echo "Error: SIGTERM" >&2; exit 1' TERM; sleep 30 & wait; exit 0
    fi
    # finishes its install, then is still exiting when the deadline hits: exit 0
    if [ "$1" = upgrade ] && [ -f "$S/upgrade_ends_at_deadline" ]; then
      cat "$S/latest" > "$S/installed"; cat "$S/latest" > "$S/codex_version"
      trap 'exit 0' TERM; sleep 30 & wait; exit 0
    fi
    [ -f "$S/${1}_ok" ] || { echo "Error: $1 failed" >&2; exit 1; }
    cat "$S/latest" > "$S/installed"; cat "$S/latest" > "$S/codex_version"
    [ -f "$S/busy_after_upgrade" ] && touch "$S/pane_busy"
    exit 0 ;;
esac
F
cat > "$BIN/codex" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'codex %s\n' "$*" >> "$S/calls.log"
case "$*" in
  --version) echo "codex-cli $(cat "$S/codex_version")" ;;
  "login status") cat "$S/login" 2>/dev/null || echo "Logged in using ChatGPT" ;;
esac
F
cat > "$BIN/pgrep" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'pgrep %s\n' "$*" >> "$S/calls.log"
[ -f "$S/exec_running" ] && { cat "$S/exec_running"; exit 0; }
exit 1
F
cat > "$BIN/node" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'node %s\n' "$*" >> "$S/calls.log"
[ -f "$S/bgps" ] && cat "$S/bgps" || echo "no background workers running"
F
cat > "$BIN/tmux" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'tmux %s\n' "$*" >> "$S/calls.log"
[ -f "$S/bare_path" ] || exit 1
case "$1" in
  display-message) echo 99999999 ;;
  capture-pane) echo "› Ask Codex to do anything"; [ -f "$S/pane_busy" ] && echo "• Working (12s • esc to interrupt)" ;;
esac
exit 0
F
cat > "$BIN/lsof" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'lsof %s\n' "$*" >> "$S/calls.log"
[ -f "$S/bare_path" ] || exit 1
# 0.160.0 also maps a copy of itself (the app-server daemon), listed first here
printf 'p99999999\nftxt\nn%s\nftxt\nn%s\nftxt\nn/usr/lib/dyld\n' "$HOME/.codex/packages/app-server-daemon/releases/0.160.0-aarch64-apple-darwin/bin/codex" "$(cat "$S/bare_path")"
F
cat > "$BIN/curl" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'curl %s\n' "$*" >> "$S/curl.log"
echo '{"ok":true,"result":{"message_id":1}}'
F
cat > "$BIN/peer-refresh.sh" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'peer-refresh %s PROBE_TIMEOUT=%s\n' "$*" "${PEER_REFRESH_PROBE_TIMEOUT:-}" >> "$S/calls.log"
if [ -f "$S/refresh_hangs" ]; then echo "peer-refresh: codex-bare relaunch: killed"; sleep 30; fi
rc="$(cat "$S/refresh_rc" 2>/dev/null || echo 0)"
if [ "$rc" = 0 ]; then echo "$S/Caskroom/$(cat "$S/installed")/bin/codex" > "$S/bare_path"; echo "peer-refresh: codex-bare relaunch: healthy"; fi
[ "$rc" = 5 ] && echo "peer-refresh: codex-bare relaunch: blocked by the Codex hooks review prompt"
exit "$rc"
F
cat > "$BIN/codex-run.sh" <<'F'
#!/bin/bash
S="$SHIM_STATE"; printf 'codex-run %s which-codex=%s\n' "$*" "$(readlink "$(command -v codex)")" >> "$S/calls.log"
out=""; prev=""; for a in "$@"; do [ "$prev" = "--out" ] && out="$a"; prev="$a"; done
mkdir -p "$out"
[ -f "$S/proof_fails" ] && { echo "codex-run: timed out negotiating with the code-mode host"; exit 2; }
[ -f "$S/proof_limit" ] && { echo "ERROR: You've hit your usage limit. Try again later." > "$out/stderr.log"; echo "CODEX ask FAILED (exit 1)"; exit 2; }
[ -f "$S/proof_other" ] && { echo "codex-run: unexpected status 500 from the backend"; exit 2; }
shasum -a 1 /etc/hosts | awk '{ print $1 }' > "$out/last.md"
F
chmod +x "$BIN"/*

# run <name> [args...]; state comes from the caller's environment:
#   INST LATEST (versions), BARE (codex-bare's Caskroom version, "none" = no
#   session), UP=1 upgrade works, RE=1 reinstall works, and touch files set up
#   by the case before the run. Leaves RC, OUT, CALLS, CURL, LOGF, STATEF.
prep() {
  ST="$ROOT/$1"; mkdir -p "$ST"; : > "$ST/calls.log"; : > "$ST/curl.log"
  echo "${INST:-0.160.0}" > "$ST/installed"; echo "${LATEST:-0.160.0}" > "$ST/latest"
  echo "${INST:-0.160.0}" > "$ST/codex_version"
  [ "${BARE:-same}" = none ] || echo "$ST/Caskroom/${BARE_V:-${INST:-0.160.0}}/bin/codex" > "$ST/bare_path"
  [ "${UP:-1}" = 1 ] && touch "$ST/upgrade_ok"; [ "${RE:-0}" = 1 ] && touch "$ST/reinstall_ok"
  printf '{"env":{"TELEGRAM_BOT_TOKEN":"TESTTOKEN","TELEGRAM_CHAT_ID":"4242"}}\n' > "$ST/settings.json"
  # the installed build passed its checks on an earlier run, unless PROVEN_V says otherwise
  [ "${PROVEN_V-x}" = none ] || echo "${PROVEN_V:-${INST:-0.160.0}}" > "$ST/autoupdate.proven"
}
run() {
  name="$1"; shift; ST="$ROOT/$name"
  for f in brew codex pgrep node tmux lsof curl peer-refresh.sh codex-run.sh; do
    [ -x "$BIN/$f" ] || { echo "run $name: fake $f missing, refusing to touch the real system" >&2; exit 1; }
  done
  OUT="$(env -u TELEGRAM_CHAT_ID SHIM_STATE="$ST" PATH="$BIN:$PATH" \
    CODEX_AUTOUPDATE_BREW="$BIN/brew" CODEX_AUTOUPDATE_CODEX="$BIN/codex" \
    CODEX_AUTOUPDATE_CASKROOM="$ST/Caskroom" CODEX_AUTOUPDATE_PEER_REFRESH="$BIN/peer-refresh.sh" \
    CODEX_AUTOUPDATE_CODEX_RUN="$BIN/codex-run.sh" CODEX_AUTOUPDATE_BG_MJS="$ST/bg.mjs" \
    CODEX_AUTOUPDATE_LOG="$ST/autoupdate.log" CODEX_AUTOUPDATE_STATE="$ST/autoupdate.state" \
    CODEX_AUTOUPDATE_PROVEN="$ST/autoupdate.proven" CODEX_AUTOUPDATE_BREW_TIMEOUT="${BT:-600}" \
    CODEX_AUTOUPDATE_REFRESH_TIMEOUT="${RT:-400}" \
    CODEX_AUTOUPDATE_SETTINGS="$ST/settings.json" CODEX_AUTOUPDATE_PROOF_TIMEOUT=5 \
    "$S" "$@" 2>&1)"; RC=$?
  CALLS="$(cat "$ST/calls.log")"; CURL="$(cat "$ST/curl.log")"
  LOGF="$(cat "$ST/autoupdate.log" 2>/dev/null)"; STATEF="$(cat "$ST/autoupdate.state" 2>/dev/null)"
  PROVENF="$(cat "$ST/autoupdate.proven" 2>/dev/null)"
}
has() { printf '%s\n' "$CALLS" | grep -qE "$1"; }
upgraded() { has '^brew upgrade --cask codex$'; }
refreshed() { has '^peer-refresh codex-bare --relaunch'; }
sent() { [ "$(printf '%s' "$CURL" | grep -c '^curl ')" -eq "$1" ]; }
TODAY="$(date +%Y-%m-%d)"

# 3. no update: installed is the latest, codex-bare on it
prep current; run current
[ $RC -eq 0 ] && ok "no update -> exit 0" || bad "no update rc=$RC ($OUT)"
has '^brew update --quiet$' && has '^brew info --cask codex --json=v2$' && ok "no update: brew update, then brew info" || bad "no update calls: $CALLS"
! upgraded && ! refreshed && ! has '^codex-run' && ok "no update: no upgrade, no proof run, no relaunch" || bad "no update touched: $CALLS"
sent 0 && ok "no update: silent, no Telegram" || bad "no update sent: $CURL"
printf '%s\n' "$LOGF" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}[+-][0-9]{4} current codex 0\.160\.0 is the latest \(brew 0\.160\.0\); codex-bare on 0\.160\.0$' && [ "$(printf '%s\n' "$LOGF" | grep -c .)" -eq 1 ] && ok "no update: exactly one log line, timestamped" || bad "no update log: $LOGF"
[ "$STATEF" = "$TODAY 0" ] && ok "no update: state records today and exit 0" || bad "state: $STATEF"

# 4. update succeeds: upgrade, prove, relaunch codex-bare, one silent Telegram line
INST=0.154.0 LATEST=0.160.0 prep up; INST=0.154.0 LATEST=0.160.0 run up
[ $RC -eq 0 ] && ok "update succeeds -> exit 0" || bad "update rc=$RC ($OUT)"
upgraded && ok "update: brew upgrade --cask codex ran" || bad "update: no upgrade ($CALLS)"
! has '^brew reinstall' && ok "update: no reinstall needed" || bad "update: reinstall ran"
has '^codex --version$' && has '^codex login status$' && ok "update: version and login checked" || bad "update: checks missing ($CALLS)"
has "^codex-run --mode ask .* which-codex=$BIN/codex$" && ok "update: shell tool proof through codex-run.sh ask mode, on the upgraded binary" || bad "update: proof call ($CALLS)"
has '^peer-refresh codex-bare --relaunch --reason codex upgraded to 0\.160\.0 PROBE_TIMEOUT=150$' && ok "update: codex-bare relaunched with a 150 s probe" || bad "update: relaunch call ($CALLS)"
p=$(printf '%s\n' "$CALLS" | grep -n '^codex-run' | cut -d: -f1); r=$(printf '%s\n' "$CALLS" | grep -n '^peer-refresh' | cut -d: -f1)
[ -n "$p" ] && [ -n "$r" ] && [ "$p" -lt "$r" ] && ok "update: the proof runs before the relaunch" || bad "order: proof@$p refresh@$r"
sent 1 && ok "update: exactly one Telegram line" || bad "update sent: $CURL"
printf '%s' "$CURL" | grep -qF -- '--form-string text=Codex CLI updated from 0.154.0 to 0.160.0 overnight. Login and shell tool proven. codex-bare relaunched on 0.160.0.' && printf '%s' "$CURL" | grep -qF -- '--form-string disable_notification=true' && printf '%s' "$CURL" | grep -qF -- '--form-string chat_id=4242' && ok "update: the line names both versions, goes out silent, to the chat id" || bad "update curl: $CURL"
[ "$PROVENF" = 0.160.0 ] && ok "update: 0.160.0 recorded as proven" || bad "update proven record: $PROVENF"
printf '%s\n' "$LOGF" | grep -q ' upgraded from 0.154.0 to 0.160.0 (brew upgrade), version, login and shell tool proven; codex-bare relaunched from 0.154.0 onto 0.160.0 and answered a ping (telegram sent)$' && ok "update: log line" || bad "update log: $LOGF"

# 5. update fails: upgrade and the reinstall fallback both fail
INST=0.154.0 LATEST=0.160.0 UP=0 prep fails; INST=0.154.0 LATEST=0.160.0 run fails
[ $RC -eq 1 ] && ok "update fails -> exit 1" || bad "fails rc=$RC ($OUT)"
upgraded && has '^brew reinstall --cask codex$' && ok "update fails: reinstall tried once after the upgrade" || bad "fails calls: $CALLS"
! refreshed && ! has '^codex-run' && ok "update fails: no proof, codex-bare left alone" || bad "fails touched: $CALLS"
sent 1 && printf '%s' "$CURL" | grep -qF -- 'Codex auto update 0.154.0 to 0.160.0 failed (brew reinstall (brew upgrade exit 1) exit 1): codex --version says 0.154.0, wanted 0.160.0. codex-bare was left on its old build.' && printf '%s' "$CURL" | grep -qF 'disable_notification=false' && ok "update fails: one Telegram line with a sound" || bad "fails curl: $CURL"
printf '%s\n' "$LOGF" | grep -q " failed brew reinstall (brew upgrade exit 1) exit 1; codex --version says '0.154.0', wanted 0.160.0; codex-bare left alone" && [ "$STATEF" = "$TODAY 1" ] && [ "$PROVENF" = 0.154.0 ] && ok "update fails: logged, state exit 1, proven record unchanged" || bad "fails log: $LOGF state: $STATEF proven: $PROVENF"

# 5b. upgrade fails, the reinstall works
INST=0.154.0 LATEST=0.160.0 UP=0 RE=1 prep reinst; INST=0.154.0 LATEST=0.160.0 run reinst
[ $RC -eq 0 ] && refreshed && printf '%s\n' "$LOGF" | grep -q '(brew reinstall (brew upgrade exit 1))' && ok "upgrade fails, reinstall works -> exit 0, relaunched" || bad "reinst rc=$RC ($LOGF)"

# 6. busy skips: nothing touched, exit 3, the reason logged
INST=0.154.0 LATEST=0.160.0 prep busy-exec
echo "4242 codex exec --skip-git-repo-check -C /tmp/x" > "$ROOT/busy-exec/exec_running"; run busy-exec
[ $RC -eq 3 ] && ok "codex exec running -> exit 3" || bad "busy-exec rc=$RC ($OUT)"
! has '^brew' && ! refreshed && sent 0 && ok "codex exec running: no brew call at all, no relaunch, no Telegram" || bad "busy-exec touched: $CALLS / $CURL"
has "^pgrep -fl \(\^\|/\)codex\( \.\*\)\? exec\( \|\\$\)$" && ok "busy: pgrep matches codex exec by its argv, not any text" || bad "pgrep call: $CALLS"
printf '%s\n' "$LOGF" | grep -q 'busy a codex exec process is running (pid 4242); nothing touched' && [ "$STATEF" = "$TODAY 3" ] && ok "busy: logged with the pid, state exit 3" || bad "busy log: $LOGF $STATEF"

INST=0.154.0 LATEST=0.160.0 prep busy-bg
# columns padded under the header, the way bg-steer.mjs psTable prints them
pstable() { printf '%-5s  %-4s  %-3s  %-7s  %-5s  %-5s  %-4s  %-6s  %s\n' RUNID LANE PID ELAPSED STEPS STEER SENT ENGINE TITLE; printf '%-5s  %-4s  %-3s  %-7s  %-5s  %-5s  %-4s  %-6s  %s\n' "$@"; }
pstable bg9-1 bg9 77 3m 4 yes 0 codex "some codex job" > "$ROOT/busy-bg/bgps"
run busy-bg
[ $RC -eq 3 ] && ! has '^brew' && printf '%s\n' "$LOGF" | grep -q 'bridge Codex job bg9-1 is running' && ok "bridge Codex background job -> exit 3, no brew" || bad "busy-bg rc=$RC ($LOGF)"

INST=0.154.0 LATEST=0.160.0 prep notbusy-bg
pstable bg9-1 bg9 77 3m 4 yes 0 claude "a codex themed claude job" > "$ROOT/notbusy-bg/bgps"
INST=0.154.0 LATEST=0.160.0 run notbusy-bg
[ $RC -eq 0 ] && upgraded && ok "a Claude engine job (codex in its title) is not busy" || bad "notbusy-bg rc=$RC ($CALLS)"

INST=0.154.0 LATEST=0.160.0 prep busy-pane; touch "$ROOT/busy-pane/pane_busy"; run busy-pane
[ $RC -eq 3 ] && ! has '^brew' && printf '%s\n' "$LOGF" | grep -q 'codex-bare is working' && ok "codex-bare mid job (esc to interrupt) -> exit 3, no brew" || bad "busy-pane rc=$RC ($LOGF)"

# 7. version compare edge: 0.100.0 is newer than 0.99.0, and not the reverse
INST=0.99.0 LATEST=0.100.0 prep edge; INST=0.99.0 LATEST=0.100.0 run edge
[ $RC -eq 0 ] && upgraded && printf '%s\n' "$LOGF" | grep -q 'upgraded from 0.99.0 to 0.100.0' && ok "0.99.0 -> 0.100.0 upgrades (numeric compare)" || bad "edge rc=$RC ($LOGF)"
INST=0.100.0 LATEST=0.99.0 prep edge-rev; INST=0.100.0 LATEST=0.99.0 run edge-rev
[ $RC -eq 0 ] && ! upgraded && printf '%s\n' "$LOGF" | grep -q 'current codex 0.100.0 is the latest (brew 0.99.0)' && ok "0.100.0 installed, brew says 0.99.0: no downgrade" || bad "edge-rev rc=$RC ($LOGF)"

# 8. the retry slot
prep slot-done; echo "$TODAY 0" > "$ROOT/slot-done/autoupdate.state"; run slot-done --scheduled
[ $RC -eq 0 ] && ! has '^brew' && ! has '^pgrep' && [ "$STATEF" = "$TODAY 0" ] && printf '%s\n' "$LOGF" | grep -q 'scheduled-skip a run already ended today with exit 0, nothing owed' && ok "--scheduled after today's clean run: skipped, state kept" || bad "slot-done rc=$RC ($CALLS) $STATEF"
INST=0.154.0 LATEST=0.160.0 prep slot-retry; echo "$TODAY 3" > "$ROOT/slot-retry/autoupdate.state"; INST=0.154.0 LATEST=0.160.0 run slot-retry --scheduled
[ $RC -eq 0 ] && upgraded && [ "$STATEF" = "$TODAY 0" ] && ok "--scheduled after today's busy run: it retries and upgrades" || bad "slot-retry rc=$RC ($CALLS)"
INST=0.154.0 LATEST=0.160.0 prep slot-old; echo "2000-01-01 0" > "$ROOT/slot-old/autoupdate.state"; INST=0.154.0 LATEST=0.160.0 run slot-old --scheduled
[ $RC -eq 0 ] && upgraded && ok "--scheduled with an older day's state: runs" || bad "slot-old rc=$RC"
prep slot-bad; run slot-bad --bogus
[ $RC -eq 1 ] && [ -z "$CALLS" ] && ok "unknown flag -> exit 1, nothing called" || bad "slot-bad rc=$RC ($CALLS)"

# 9. the proofs after an upgrade
INST=0.154.0 LATEST=0.160.0 prep nologin; echo "Not logged in" > "$ROOT/nologin/login"; INST=0.154.0 LATEST=0.160.0 run nologin
[ $RC -eq 1 ] && ! refreshed && ! has '^codex-run' && sent 1 && printf '%s' "$CURL" | grep -qF -- 'codex login status says: Not logged in. Run codex login once.' && ok "login gone after the upgrade -> exit 1, codex-bare left alone, told" || bad "nologin rc=$RC ($CALLS)"
INST=0.154.0 LATEST=0.160.0 prep noshell; touch "$ROOT/noshell/proof_fails"; INST=0.154.0 LATEST=0.160.0 run noshell
[ $RC -eq 1 ] && ! refreshed && sent 1 && printf '%s' "$CURL" | grep -qF 'shell tool did not run (exit 2). A Gatekeeper or permission dialog may be waiting' && ok "shell tool proof fails -> exit 1, codex-bare left alone, Gatekeeper named" || bad "noshell rc=$RC ($CALLS / $CURL)"

# 10. codex-bare after an upgrade
INST=0.154.0 LATEST=0.160.0 BARE=none prep nobare; INST=0.154.0 LATEST=0.160.0 BARE=none run nobare
[ $RC -eq 0 ] && upgraded && ! refreshed && sent 1 && ok "no codex-bare session: upgraded, nothing to relaunch" || bad "nobare rc=$RC ($CALLS)"
INST=0.154.0 LATEST=0.160.0 prep owed; touch "$ROOT/owed/busy_after_upgrade"; INST=0.154.0 LATEST=0.160.0 run owed
[ $RC -eq 3 ] && upgraded && ! refreshed && [ "$STATEF" = "$TODAY 3" ] && ok "codex-bare starts a job during the upgrade -> exit 3, no kill, relaunch owed" || bad "owed rc=$RC ($CALLS)"
sent 1 && printf '%s' "$CURL" | grep -qF 'codex-bare was busy and moves to 0.160.0 at the next run.' && ok "owed: the one line says the relaunch is owed" || bad "owed curl: $CURL"
rm -f "$ROOT/owed/pane_busy"; : > "$ROOT/owed/calls.log"; : > "$ROOT/owed/curl.log"; run owed --scheduled
[ $RC -eq 0 ] && ! upgraded && refreshed && sent 0 && printf '%s\n' "$LOGF" | tail -1 | grep -q ' relaunched codex 0.160.0 current; codex-bare relaunched from 0.154.0 onto 0.160.0' && ok "owed: the retry pays the relaunch, silently" || bad "owed retry rc=$RC ($CALLS) $LOGF"
INST=0.154.0 LATEST=0.160.0 prep blocked; echo 5 > "$ROOT/blocked/refresh_rc"; INST=0.154.0 LATEST=0.160.0 run blocked
[ $RC -eq 5 ] && sent 1 && printf '%s' "$CURL" | grep -qF 'codex-bare shows a prompt only you can answer after its relaunch: peer-refresh: codex-bare relaunch: blocked by the Codex hooks review prompt' && ok "relaunch blocked by a prompt -> exit 5, the prompt named" || bad "blocked rc=$RC ($CURL)"
! printf '%s' "$CURL$LOGF" | grep -q 'Terminated' && ok "no shell job notice leaks into the Telegram line or the log" || bad "job notice leaked: $CURL"
INST=0.154.0 LATEST=0.160.0 prep relfail; echo 2 > "$ROOT/relfail/refresh_rc"; INST=0.154.0 LATEST=0.160.0 run relfail
[ $RC -eq 1 ] && sent 1 && printf '%s' "$CURL" | grep -qF 'did not come back after its relaunch (peer-refresh exit 2)' && ok "relaunch fails -> exit 1, told" || bad "relfail rc=$RC ($CURL)"
prep chatgpt; echo "/Applications/ChatGPT.app/Contents/Resources/codex" > "$ROOT/chatgpt/bare_path"; run chatgpt
[ $RC -eq 0 ] && ! refreshed && ok "codex-bare on the ChatGPT.app fallback binary: not relaunched" || bad "chatgpt rc=$RC ($CALLS)"

# 10b. QA 10-03 MEDIUM: a failed proof is not forgotten. The next run sees the
#      new build installed (no upgrade due) and must prove it again before
#      codex-bare moves onto it; it moves only once the proof passes.
INST=0.154.0 LATEST=0.160.0 prep reprove; touch "$ROOT/reprove/proof_fails"; INST=0.154.0 LATEST=0.160.0 run reprove
[ $RC -eq 1 ] && ! refreshed && [ "$PROVENF" = 0.154.0 ] && ok "reprove day 1: proof fails after the upgrade -> exit 1, not relaunched, record stays 0.154.0" || bad "reprove d1 rc=$RC proven=$PROVENF ($CALLS)"
echo "2000-01-01 1" > "$ROOT/reprove/autoupdate.state"; : > "$ROOT/reprove/calls.log"; : > "$ROOT/reprove/curl.log"; run reprove --scheduled
[ $RC -eq 1 ] && ! upgraded && has '^codex-run' && ! refreshed && ok "reprove day 2: no upgrade due, the proof runs again, still fails -> exit 1, codex-bare NOT moved" || bad "reprove d2 rc=$RC ($CALLS)"
sent 1 && printf '%s' "$CURL" | grep -qF -- 'Codex 0.160.0 is installed but fails its check: its shell tool did not run (exit 2). A Gatekeeper or permission dialog may be waiting on the Mac screen. codex-bare is not relaunched onto it.' && ok "reprove day 2: told again" || bad "reprove d2 curl: $CURL"
rm -f "$ROOT/reprove/proof_fails"; echo "2000-01-01 1" > "$ROOT/reprove/autoupdate.state"; : > "$ROOT/reprove/calls.log"; : > "$ROOT/reprove/curl.log"; run reprove --scheduled
[ $RC -eq 0 ] && has '^codex-run' && refreshed && [ "$PROVENF" = 0.160.0 ] && ok "reprove day 3: the proof passes -> recorded, then relaunched, exit 0" || bad "reprove d3 rc=$RC proven=$PROVENF ($CALLS)"
p=$(printf '%s\n' "$CALLS" | grep -n '^codex-run' | cut -d: -f1); r=$(printf '%s\n' "$CALLS" | grep -n '^peer-refresh' | cut -d: -f1)
[ -n "$p" ] && [ -n "$r" ] && [ "$p" -lt "$r" ] && sent 1 && printf '%s' "$CURL" | grep -qF -- 'Codex 0.160.0 now passes its version, login and shell tool checks. codex-bare relaunched on 0.160.0.' && printf '%s' "$CURL" | grep -qF 'disable_notification=true' && ok "reprove day 3: proof before relaunch, one silent line saying it recovered" || bad "reprove d3 order p@$p r@$r curl: $CURL"
PROVEN_V=none prep firstrun; PROVEN_V=none run firstrun
[ $RC -eq 0 ] && has '^codex-run' && ! upgraded && sent 0 && [ "$PROVENF" = 0.160.0 ] && printf '%s\n' "$LOGF" | grep -q ' proven codex 0.160.0 passed its checks (before: none proven); codex-bare on 0.160.0$' && ok "first run, no proven record: proves the installed build once, silently" || bad "firstrun rc=$RC proven=$PROVENF ($LOGF)"

# 10c. QA 10-03 LOW: an empty PID cell (an app-server job before its spawn) is
#      padded with spaces; ENGINE is read by its position under the header.
INST=0.154.0 LATEST=0.160.0 prep emptypid
pstable bg9-1 bg9 "" 3s 0 yes 0 codex "a codex job" > "$ROOT/emptypid/bgps"
run emptypid
[ $RC -eq 3 ] && ! has '^brew' && printf '%s\n' "$LOGF" | grep -q 'bridge Codex job bg9-1 is running' && ok "a Codex job with an empty PID cell -> busy, exit 3" || bad "emptypid rc=$RC ($LOGF)"

# 10d. QA 10-03 LOW: a hung brew upgrade is killed with its children, reported
#      as a timeout (124), and the reinstall fallback goes on.
INST=0.154.0 LATEST=0.160.0 RE=1 prep hang; touch "$ROOT/hang/upgrade_hangs"; INST=0.154.0 LATEST=0.160.0 BT=2 run hang
[ $RC -eq 0 ] && printf '%s\n' "$LOGF" | grep -q '(brew reinstall (brew upgrade exit 124))' && ok "hung upgrade -> killed after the timeout, 124, reinstall worked" || bad "hang rc=$RC ($LOGF)"
alive=0; for f in hang_parent hang_child; do kill -0 "$(cat "$ROOT/hang/$f")" 2>/dev/null && alive=1; done
[ "$alive" -eq 0 ] && ok "hung upgrade: the fake brew and its child are both gone" || bad "hang left processes: $(cat "$ROOT/hang/hang_parent") $(cat "$ROOT/hang/hang_child")"

# 10e. QA 10-03 confirm pass, LOW 1: real brew catches SIGTERM and exits 1, so
#      a killed brew must still read as a timeout (124); and a command that
#      ends cleanly just as the deadline fires stays 0 (no needless reinstall).
INST=0.154.0 LATEST=0.160.0 RE=1 prep hangtrap; touch "$ROOT/hangtrap/upgrade_hangs_traps"; INST=0.154.0 LATEST=0.160.0 BT=2 run hangtrap
[ $RC -eq 0 ] && printf '%s\n' "$LOGF" | grep -q '(brew reinstall (brew upgrade exit 124))' && ok "brew that traps TERM and exits 1 at the timeout -> reported as 124" || bad "hangtrap rc=$RC ($LOGF)"
INST=0.154.0 LATEST=0.160.0 prep deadline; touch "$ROOT/deadline/upgrade_ends_at_deadline"; INST=0.154.0 LATEST=0.160.0 BT=2 run deadline
[ $RC -eq 0 ] && ! has '^brew reinstall' && printf '%s\n' "$LOGF" | grep -q ' upgraded from 0.154.0 to 0.160.0 (brew upgrade),' && ok "a command that exits 0 as the deadline fires stays 0: no reinstall" || bad "deadline rc=$RC ($CALLS)"

# 10f. QA 10-03 confirm pass, LOW 2: a peer-refresh timeout keeps its own last
#      line in the Telegram text, not a bash "Terminated" job notice.
INST=0.154.0 LATEST=0.160.0 prep refhang; touch "$ROOT/refhang/refresh_hangs"; INST=0.154.0 LATEST=0.160.0 RT=2 run refhang
[ $RC -eq 1 ] && sent 1 && printf '%s' "$CURL" | grep -qF -- 'did not come back after its relaunch (peer-refresh exit 124): peer-refresh: codex-bare relaunch: killed --form-string' && ok "peer-refresh timeout -> exit 1, its own last line in the Telegram text" || bad "refhang rc=$RC ($CURL)"
! printf '%s' "$CURL$LOGF" | grep -q 'Terminated' && ok "peer-refresh timeout: no job notice in the text or the log" || bad "refhang notice: $CURL $LOGF"

# 10g. a first run whose proof fails says so without claiming an old build,
#      and the run that later passes tells Zalo (the state remembers exit 1)
PROVEN_V=none prep firstfail; touch "$ROOT/firstfail/proof_fails"; PROVEN_V=none run firstfail
[ $RC -eq 1 ] && ! refreshed && printf '%s' "$CURL" | grep -qF -- 'codex-bare is not relaunched onto it.' && ok "first run, proof fails -> exit 1, honest wording" || bad "firstfail rc=$RC ($CURL)"
rm -f "$ROOT/firstfail/proof_fails"; : > "$ROOT/firstfail/curl.log"; run firstfail
[ $RC -eq 0 ] && sent 1 && printf '%s' "$CURL" | grep -qF -- 'Codex 0.160.0 now passes its version, login and shell tool checks.' && ok "first run failed, the next passes -> one silent recovery line" || bad "firstfail d2 rc=$RC ($CURL)"

# 10h. verifier 10-03 LOW: a codex exec that starts after the first busy check
#      (during brew update) still stops the upgrade: checked again before it.
INST=0.154.0 LATEST=0.160.0 prep latebusy; touch "$ROOT/latebusy/busy_after_info"; INST=0.154.0 LATEST=0.160.0 run latebusy
[ $RC -eq 3 ] && has '^brew info' && ! upgraded && ! refreshed && sent 0 && printf '%s\n' "$LOGF" | grep -q 'busy a codex exec process is running (pid 5151) (seen right before the upgrade)' && ok "codex exec starts during brew update -> exit 3 before the upgrade, nothing swapped" || bad "latebusy rc=$RC ($CALLS)"

# 10i. re-verify 10-03 LOW: the Telegram line names the cause the proof output
#      shows. A usage limit is not a Gatekeeper dialog (and goes out silent);
#      any other failure quotes codex-run's last line.
INST=0.154.0 LATEST=0.160.0 prep prooflimit; touch "$ROOT/prooflimit/proof_limit"; INST=0.154.0 LATEST=0.160.0 run prooflimit
[ $RC -eq 1 ] && ! refreshed && sent 1 && printf '%s' "$CURL" | grep -qF -- 'its check could not run: the Codex usage limit was hit (exit 2). The next run tries again.' && ! printf '%s' "$CURL" | grep -q Gatekeeper && printf '%s' "$CURL" | grep -qF 'disable_notification=true' && ok "proof hits a usage limit -> exit 1, says so, no Gatekeeper, silent" || bad "prooflimit rc=$RC ($CURL)"
INST=0.154.0 LATEST=0.160.0 prep proofother; touch "$ROOT/proofother/proof_other"; INST=0.154.0 LATEST=0.160.0 run proofother
[ $RC -eq 1 ] && sent 1 && printf '%s' "$CURL" | grep -qF -- 'its shell tool check failed (exit 2): codex-run: unexpected status 500 from the backend' && ! printf '%s' "$CURL" | grep -q Gatekeeper && printf '%s' "$CURL" | grep -qF 'disable_notification=false' && ok "proof fails another way -> codex-run's own line, with sound" || bad "proofother rc=$RC ($CURL)"

# 11. guards
prep locked; mkdir "$ROOT/locked/autoupdate.state.lock"; run locked
[ $RC -eq 3 ] && ! has '^brew' && [ -d "$ROOT/locked/autoupdate.state.lock" ] && ok "another run holds the lock -> exit 3, its lock left in place" || bad "locked rc=$RC ($CALLS)"
prep garbage; touch "$ROOT/garbage/info_garbage"; run garbage
[ $RC -eq 1 ] && ! upgraded && sent 1 && ok "brew info unusable -> exit 1, no upgrade, told" || bad "garbage rc=$RC ($CALLS)"
[ ! -d "$ROOT/up/autoupdate.state.lock" ] && ok "a finished run releases its lock" || bad "lock left behind"

rm -rf "$ROOT"
echo "$pass/$((pass+fail)) passed"; [ $fail -eq 0 ]
