#!/bin/bash
# codex-autoupdate.sh: keep the Homebrew Codex CLI current, unattended.
#
#   ~/.claude/scripts/codex-autoupdate.sh [--scheduled]
#
# Zalo, 2026-10-03: "can you update codex automatically always, so I dont have
# to manually update everytime". The LaunchAgent
# ~/Library/LaunchAgents/com.zalo.codex-autoupdate.plist runs this with
# --scheduled daily at 02:30 and again at 05:15. Codex's own startup update
# prompt is off (check_for_update_on_startup = false, projected by
# codex-sync.py): it held codex-bare for a morning and cost two outreach runs.
#
# One run, in order:
#  1. --scheduled: a run that already ended today with an exit other than 3
#     means nothing is owed, so the 05:15 slot only retries a skipped run.
#  2. Busy check, nothing touched, exit 3: a `codex exec` process, a bridge
#     background job on the Codex engine (bg.mjs ps, ENGINE column), or the
#     codex-bare pane showing "esc to interrupt" (read only). Swapping the
#     Caskroom folder under a running job can break it.
#  3. brew update, then brew info --cask codex --json=v2, on the ARM Homebrew
#     by full path: PATH puts the Intel brew in /usr/local first, and codex is
#     not installed there.
#  4. Latest newer than installed: brew upgrade --cask codex (brew reinstall
#     --cask codex once if that fails), then prove it: codex --version prints
#     the new version, codex login status still says Logged in, and the shell
#     tool runs (codex-run.sh ask mode must return the local shasum of
#     /etc/hosts; on 2026-09-11 a new build's helper sat behind a Gatekeeper
#     dialog and every shell call timed out). A version that passes all three
#     is written to ~/.claude/logs/codex-autoupdate.proven. No upgrade due, but
#     the installed version is not the proven one (its proof failed on an
#     earlier run, or none ever ran): prove it again now. A failed proof ends
#     the run with exit 1 and leaves codex-bare alone, on every run until the
#     proof passes.
#  5. codex-bare, on every run: when its codex process maps a binary from
#     another Caskroom version than the installed (and proven) one, relaunch it with
#     peer-refresh.sh --relaunch. That flag kills without a probe, so the pane
#     check from step 2 runs again right before it. Recomputed every run, so a
#     relaunch a busy run owed is paid by the next one.
#  6. One line per run in ~/.claude/logs/codex-autoupdate.log. One Telegram
#     line only when the version changed or something failed; a clean upgrade
#     goes out silent (no sound), since it lands at night.
#
# Exit: 0 current, or upgraded and proven; 1 failed; 3 skipped (busy, or the
# codex-bare relaunch is still owed); 5 codex-bare shows a prompt only Zalo can
# answer (peer-refresh.sh exit 5).
#
# Test: bash ~/.claude/scripts/codex-autoupdate.test.sh (fakes for every
# command; nothing real is upgraded, relaunched or sent).
set -u

BREW="${CODEX_AUTOUPDATE_BREW:-/opt/homebrew/bin/brew}"
CODEX="${CODEX_AUTOUPDATE_CODEX:-/opt/homebrew/bin/codex}"
CASKROOM="${CODEX_AUTOUPDATE_CASKROOM:-/opt/homebrew/Caskroom/codex}"
PEER_REFRESH="${CODEX_AUTOUPDATE_PEER_REFRESH:-$HOME/.claude/scripts/peer-refresh.sh}"
CODEX_RUN="${CODEX_AUTOUPDATE_CODEX_RUN:-$HOME/.claude/skills/codex/codex-run.sh}"
BG_MJS="${CODEX_AUTOUPDATE_BG_MJS:-$HOME/dev/claude-telegram-bridge/bg.mjs}"
LOG="${CODEX_AUTOUPDATE_LOG:-$HOME/.claude/logs/codex-autoupdate.log}"
STATE="${CODEX_AUTOUPDATE_STATE:-$HOME/.claude/logs/codex-autoupdate.state}"
PROVEN="${CODEX_AUTOUPDATE_PROVEN:-$HOME/.claude/logs/codex-autoupdate.proven}"
SETTINGS="${CODEX_AUTOUPDATE_SETTINGS:-$HOME/.claude/settings.local.json}"
BREW_TIMEOUT="${CODEX_AUTOUPDATE_BREW_TIMEOUT:-600}"
PROOF_TIMEOUT="${CODEX_AUTOUPDATE_PROOF_TIMEOUT:-300}"
REFRESH_TIMEOUT="${CODEX_AUTOUPDATE_REFRESH_TIMEOUT:-400}"
SESSION=codex-bare
export HOMEBREW_NO_ENV_HINTS=1 HOMEBREW_NO_INSTALL_CLEANUP=1

SCHEDULED=0
case "${1:-}" in
  "") ;;
  --scheduled) SCHEDULED=1 ;;
  *) echo "usage: codex-autoupdate.sh [--scheduled]" >&2; exit 1 ;;
esac

mkdir -p "$(dirname "$LOG")" "$(dirname "$STATE")"
WORK="$(mktemp -d /tmp/codex-autoupdate.XXXXXX)"
# codex-run.sh resolves codex by name: give it this exact binary, nothing else.
mkdir "$WORK/bin" && ln -s "$CODEX" "$WORK/bin/codex" && export PATH="$WORK/bin:$PATH"
TODAY="$(date +%Y-%m-%d)"
VERSION_RE='^[0-9]+(\.[0-9]+)*$'
HAVE_LOCK=0

# finish <exit> <outcome> <detail> [telegram text] [silent:true|false]
finish() {
  local note=""
  if [ -n "${4:-}" ]; then
    if tg "$4" "${5:-false}"; then note=" (telegram sent)"; else note=" (telegram NOT sent: $TG_WHY)"; fi
  fi
  printf '%s %s %s%s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$2" "$3" "$note" >> "$LOG"
  echo "codex-autoupdate: $2 $3$note"
  [ "$2" = scheduled-skip ] || echo "$TODAY $1" > "$STATE"
  rm -rf "$WORK"
  [ "$HAVE_LOCK" -eq 1 ] && rmdir "$STATE.lock" 2> /dev/null
  exit "$1"
}

TG_WHY=""
tg() {
  local token chat resp
  token="$(jq -r '.env.TELEGRAM_BOT_TOKEN // .TELEGRAM_BOT_TOKEN // empty' "$SETTINGS" 2>/dev/null)"
  chat="${TELEGRAM_CHAT_ID:-$(jq -r '.env.TELEGRAM_CHAT_ID // .TELEGRAM_CHAT_ID // empty' "$SETTINGS" 2>/dev/null)}"
  [ -n "$token" ] && [ -n "$chat" ] || { TG_WHY="no creds in $SETTINGS"; return 1; }
  resp="$(curl -sS --max-time 20 "https://api.telegram.org/bot$token/sendMessage" \
    --form-string "chat_id=$chat" --form-string "text=$1" \
    --form-string "disable_notification=$2" 2>&1)"
  case "$resp" in *'"ok":true'*) return 0 ;; esac
  TG_WHY="$(printf '%s' "$resp" | tr '\n' ' ' | cut -c1-120)"; return 1
}

# The pid and every descendant of it, so a timeout also stops what a command
# started (brew's download, codex's helpers).
tree_pids() {
  local c
  echo "$1"
  for c in $(ps -ax -o pid=,ppid= | awk -v p="$1" '$2 == p { print $1 }'); do tree_pids "$c"; done
}

# run_for <seconds> <cmd...>: the command's exit code, 124 when it overran and
# was killed with its descendants. Output goes wherever the caller redirects it.
run_for() {
  local secs="$1" pid w rc mark="$WORK/overran.$RANDOM"; shift
  "$@" < /dev/null & pid=$!
  ( sleep "$secs"; touch "$mark"; t="$(tree_pids "$pid")"; kill -TERM $t; sleep 5; kill -KILL $t ) > /dev/null 2>&1 & w=$!
  # Disowned, so killing it never prints a "Terminated" job notice into the
  # caller's captured output.
  disown "$w"
  # 2>: a command killed by a signal makes bash print a "Terminated" notice
  # here, which would replace the command's own last line in the output.
  wait "$pid" 2> /dev/null; rc=$?
  # The watcher first, so it cannot go on to signal a pid that is gone.
  kill "$w" 2> /dev/null; pkill -P "$w" 2> /dev/null
  # A marker alone is not a timeout: the command may have ended cleanly just as
  # the watcher fired, so a 0 stays 0. Any other code counts as the timeout,
  # signal or not: brew catches SIGTERM and exits 1 (brew.rb rescue Exception).
  [ -e "$mark" ] && [ "$rc" -ne 0 ] && rc=124
  return "$rc"
}

# 0 when $1 is a strictly higher dotted version than $2 (0.100.0 > 0.99.0).
version_gt() {
  [ "$1" = "$2" ] && return 1
  [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}

TMUX_BIN="$(command -v tmux || echo /usr/local/bin/tmux)"
bare_pane() { "$TMUX_BIN" capture-pane -t "=$SESSION:" -p -J -S -15 2> /dev/null; }
bare_working() { bare_pane | grep -qF 'esc to interrupt'; }

# The Caskroom version of the codex binary the codex-bare session runs. Empty
# when there is no session, no codex in it, or a binary outside the Caskroom
# (the launcher's ChatGPT.app fallback).
bare_version() {
  local pane pids path
  pane="$("$TMUX_BIN" display-message -p -t "=$SESSION:" '#{pane_pid}' 2> /dev/null)"
  case "$pane" in '' | *[!0-9]*) return 0 ;; esac
  pids="$(ps -ax -o pid=,ppid= | awk -v p="$pane" '$2 == p { printf ",%s", $1 }')"
  # 0.160.0 also maps a copy of itself under ~/.codex/packages: the Caskroom one counts.
  path="$(lsof -a -p "$pane$pids" -d txt -Fn 2> /dev/null | sed -n 's/^n//p' | grep -F "$CASKROOM/" | grep -E '/bin/codex$' | head -1)"
  case "$path" in "$CASKROOM"/*/bin/codex) path="${path#"$CASKROOM"/}"; echo "${path%%/*}" ;; esac
}

busy_reason() {
  local p job
  p="$(pgrep -fl '(^|/)codex( .*)? exec( |$)' 2> /dev/null | grep -v 'ChatGPT.app' | head -1)"
  [ -n "$p" ] && { echo "a codex exec process is running (pid ${p%% *})"; return; }
  # ENGINE by its position under the header: an empty PID cell is padded with
  # spaces, so counting whitespace fields would shift the columns.
  job="$(node "$BG_MJS" ps 2> /dev/null | awk 'NR == 1 { c = index($0, "ENGINE"); next } c && substr($0, c, 6) ~ /^codex( |$)/ { print $1; exit }')"
  [ -n "$job" ] && { echo "bridge Codex job $job is running"; return; }
  bare_working && echo "codex-bare is working (its pane shows esc to interrupt)"
}

# ---- 1. the retry slot -----------------------------------------------------
sdate=""; sexit=""
[ -r "$STATE" ] && read -r sdate sexit < "$STATE"
last_exit="$sexit"
if [ "$SCHEDULED" -eq 1 ]; then
  if [ "${sdate:-}" = "$TODAY" ] && [ -n "$sexit" ] && [ "$sexit" != 3 ]; then
    finish 0 scheduled-skip "a run already ended today with exit $sexit, nothing owed"
  fi
fi

# One run at a time; a lock older than two hours is a dead run's.
if ! mkdir "$STATE.lock" 2> /dev/null; then
  [ -n "$(find "$STATE.lock" -maxdepth 0 -mmin +120 2> /dev/null)" ] && rmdir "$STATE.lock"
  mkdir "$STATE.lock" 2> /dev/null || finish 3 busy "another run holds $STATE.lock"
fi
HAVE_LOCK=1

# ---- 2. busy ---------------------------------------------------------------
why="$(busy_reason)"
[ -n "$why" ] && finish 3 busy "$why; nothing touched, the next run retries"

# ---- 3. versions -----------------------------------------------------------
run_for 180 "$BREW" update --quiet > "$WORK/update.txt" 2>&1 || true
export HOMEBREW_NO_AUTO_UPDATE=1
run_for 60 "$BREW" info --cask codex --json=v2 > "$WORK/info.json" 2> "$WORK/info.err"
read -r latest installed < <(python3 -c 'import json,sys; c=json.load(open(sys.argv[1]))["casks"][0]; print(c.get("version") or "-", c.get("installed") or "-")' "$WORK/info.json" 2> /dev/null)
if ! [[ "${latest:-}" =~ $VERSION_RE ]]; then
  finish 1 failed "brew info gave no usable latest version ($(head -c 160 "$WORK/info.err" | tr '\n' ' '))" \
    "Codex auto update failed: brew info --cask codex gave no version. Log: ~/.claude/logs/codex-autoupdate.log"
fi
if ! [[ "${installed:-}" =~ $VERSION_RE ]]; then
  finish 1 failed "codex is not installed as a cask under $BREW (installed: ${installed:-none})" \
    "Codex auto update failed: the codex cask is not installed under /opt/homebrew. Log: ~/.claude/logs/codex-autoupdate.log"
fi

# ---- 4. upgrade and prove --------------------------------------------------
# prove <version>: the binary is <version>, the login survived, the shell tool
# runs. 0 and <version> recorded in $PROVEN, or 1 with PROVE_WHY (log) and
# PROVE_TG (Telegram) set.
PROVE_WHY=""; PROVE_TG=""; PROVE_SILENT=false
prove() {
  local v="$1" now login want prc
  PROVE_SILENT=false
  now="$(run_for 30 "$CODEX" --version 2> /dev/null | awk '{ print $NF }' | head -1)"
  if [ "$now" != "$v" ]; then
    PROVE_WHY="codex --version says '${now:-nothing}', wanted $v"
    PROVE_TG="codex --version says ${now:-nothing}, wanted $v."; return 1
  fi
  login="$(run_for 30 "$CODEX" login status 2>&1 | head -1)"
  case "$login" in
    *"Logged in"*) ;;
    *) PROVE_WHY="the login is gone: '$login'"
       PROVE_TG="codex login status says: $login. Run codex login once."; return 1 ;;
  esac
  want="$(shasum -a 1 /etc/hosts | awk '{ print $1 }')"
  printf 'Run this shell command and reply with only the 40 character hash it prints, nothing else:\nshasum -a 1 /etc/hosts\n' > "$WORK/prompt.md"
  rm -rf "$WORK/proof"
  run_for $((PROOF_TIMEOUT + 30)) "$CODEX_RUN" --mode ask --cwd "$WORK" --prompt-file "$WORK/prompt.md" \
    --ephemeral --timeout "$PROOF_TIMEOUT" --out "$WORK/proof" > "$WORK/proof.txt" 2>&1; prc=$?
  if ! grep -qF "$want" "$WORK/proof/last.md" 2> /dev/null; then
    local said; said="$(tail -1 "$WORK/proof.txt" | cut -c1-120)"
    PROVE_WHY="the shell tool proof failed (codex-run exit $prc: $said)"
    # Name the cause the output shows. A usage limit is not a dialog on the
    # screen, and it clears by itself, so that line goes out silent.
    if cat "$WORK/proof.txt" "$WORK/proof/stderr.log" 2> /dev/null | grep -qiE 'usage limit|rate limit|quota|429'; then
      PROVE_TG="its check could not run: the Codex usage limit was hit (exit $prc). The next run tries again."; PROVE_SILENT=true
    elif [ "$prc" -eq 124 ] || printf '%s' "$said" | grep -qi 'timed out'; then
      PROVE_TG="its shell tool did not run (exit $prc). A Gatekeeper or permission dialog may be waiting on the Mac screen."
    else
      PROVE_TG="its shell tool check failed (exit $prc): $said"
    fi
    return 1
  fi
  echo "$v" > "$PROVEN"
}

changed=""; news=""; kind=""
proven_before="$(cat "$PROVEN" 2> /dev/null)"
if version_gt "$latest" "$installed"; then
  # Again right before the swap: brew update can take minutes, and brew purges
  # the old Caskroom folder a job started in that window still loads from.
  why="$(busy_reason)"
  [ -n "$why" ] && finish 3 busy "$why (seen right before the upgrade); nothing touched, the next run retries"
  how="brew upgrade"
  run_for "$BREW_TIMEOUT" "$BREW" upgrade --cask codex > "$WORK/brew.txt" 2>&1; rc=$?
  if [ "$rc" -ne 0 ]; then
    how="brew reinstall (brew upgrade exit $rc)"
    run_for "$BREW_TIMEOUT" "$BREW" reinstall --cask codex >> "$WORK/brew.txt" 2>&1; rc=$?
  fi
  cp "$WORK/brew.txt" "$(dirname "$LOG")/codex-autoupdate.brew.txt" 2> /dev/null
  if ! prove "$latest"; then
    finish 1 failed "$how exit $rc; $PROVE_WHY; codex-bare left alone (brew output: logs/codex-autoupdate.brew.txt)" \
      "Codex auto update $installed to $latest failed ($how exit $rc): $PROVE_TG codex-bare was left on its old build." "$PROVE_SILENT"
  fi
  changed="from $installed to $latest ($how), version, login and shell tool proven"
  news="Codex CLI updated from $installed to $latest overnight. Login and shell tool proven."
  kind=upgraded; lead="upgraded $changed"
  installed="$latest"
elif [ "$proven_before" != "$installed" ]; then
  # No upgrade due, but this build never passed its proof (it failed on an
  # earlier run, or no run ever proved it): prove it before codex-bare moves.
  if ! prove "$installed"; then
    finish 1 failed "codex $installed is installed but not proven: $PROVE_WHY; codex-bare left alone" \
      "Codex $installed is installed but fails its check: $PROVE_TG codex-bare is not relaunched onto it." "$PROVE_SILENT"
  fi
  changed="codex $installed passed its checks (before: ${proven_before:-none proven})"
  kind=proven; lead="$changed"
  # Tell Zalo only when an earlier run told him a check failed.
  if [ -n "$proven_before" ] || [ "$last_exit" = 1 ]; then
    news="Codex $installed now passes its version, login and shell tool checks."
  fi
fi

# ---- 5. codex-bare ---------------------------------------------------------
bare="$(bare_version)"
if [ -z "$bare" ] || [ "$bare" = "$installed" ]; then
  bdesc="codex-bare on $bare"; [ -z "$bare" ] && bdesc="no Homebrew codex running in codex-bare"
  [ -n "$kind" ] && finish 0 "$kind" "$changed; $bdesc" "$news" true
  finish 0 current "codex $installed is the latest (brew $latest); $bdesc"
fi
[ -z "$kind" ] && lead="codex $installed current"
outcome=relaunched; [ "$kind" = upgraded ] && outcome=upgraded
if bare_working; then
  finish 3 owed "$lead; codex-bare still runs $bare and is working, relaunch owed to the next run" \
    "${news:+$news codex-bare was busy and moves to $installed at the next run.}" true
fi
# 150 s: a cold Codex start answers its first ping slowly (09-11, 0.154.0).
export PEER_REFRESH_PROBE_TIMEOUT=150
run_for "$REFRESH_TIMEOUT" "$PEER_REFRESH" "$SESSION" --relaunch --reason "codex upgraded to $installed" > "$WORK/refresh.txt" 2>&1; rrc=$?
after="$(bare_version)"
last="$(tail -1 "$WORK/refresh.txt" | cut -c1-200)"
case "$rrc" in
  0)
    if [ "$after" = "$installed" ]; then
      finish 0 "$outcome" "${changed:-codex $installed current}; codex-bare relaunched from $bare onto $installed and answered a ping" \
        "${news:+$news codex-bare relaunched on $installed.}" true
    fi
    finish 1 failed "$lead; peer-refresh exit 0 but codex-bare maps '${after:-nothing}', not $installed" \
      "Codex is on $installed, but codex-bare still maps ${after:-no Homebrew codex} after its relaunch. Last line: $last" ;;
  3)
    finish 3 owed "$lead; codex-bare busy at the relaunch (peer-refresh exit 3), owed to the next run" \
      "${news:+$news codex-bare was busy and moves to $installed at the next run.}" true ;;
  5)
    finish 5 blocked "$lead; codex-bare relaunch blocked by a prompt (peer-refresh exit 5): $last" \
      "${news:+$news }codex-bare shows a prompt only you can answer after its relaunch: $last" ;;
  *)
    finish 1 failed "$lead; codex-bare relaunch failed (peer-refresh exit $rrc): $last" \
      "${news:+$news }codex-bare did not come back after its relaunch (peer-refresh exit $rrc): $last" ;;
esac
