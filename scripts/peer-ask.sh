#!/bin/bash
# peer-ask.sh: send ONE prompt to a named tmux session and wait for its reply.
#
#   ~/.claude/scripts/peer-ask.sh <session> -m "prompt text" [--timeout 180] [--idle REGEX]
#   ~/.claude/scripts/peer-ask.sh <session> -f /path/prompt.txt [...]
#
# Does exactly the sanctioned peer-message protocol from ~/.claude/CLAUDE.md
# (literal text with `send-keys -l --`, then a separate `Enter`, then
# `capture-pane` polling) in one call, so a Claude session does not spend 6 to 8
# round trips and fixed sleeps on it. It never sends control keys: every control
# byte in the prompt (CR, tab, ESC, ^C, ...) is folded to a space before sending,
# and peer-ask.test.sh greps this file for forbidden verbs.
#
# Idle detection: the pane counts as "replied" when (1) it differs from the
# baseline captured before the prompt was sent (a turn actually started),
# (2) its last 6 non-empty lines match --idle (default covers the Codex TUI
# composer placeholder and the Claude Code prompt hint), and (3) it has not
# changed across two consecutive 2 s polls. Prints the pane tail and elapsed
# time; exit 0 replied, 3 timeout, 4 session ended, 2 usage error.
set -u
usage() { echo "usage: peer-ask.sh <session> -m TEXT | -f FILE [--timeout SECONDS] [--idle REGEX]" >&2; exit 2; }
SESSION="${1:-}"; [ -n "$SESSION" ] || usage
shift
TEXT=""; TIMEOUT=180; IDLE='Ask Codex to do anything|\? for shortcuts|^[›>] *$'
while [ $# -gt 0 ]; do
  case "$1" in
    -m|-f|--timeout|--idle) [ $# -ge 2 ] || { echo "peer-ask: $1 needs a value" >&2; exit 2; } ;;
  esac
  case "$1" in
    -m) TEXT="$2" ;;
    -f) [ -r "$2" ] || { echo "peer-ask: cannot read prompt file '$2'" >&2; exit 2; }; TEXT="$(cat "$2")" ;;
    --timeout) TIMEOUT="$2" ;;
    --idle) IDLE="$2" ;;
    *) echo "peer-ask: unknown arg '$1'" >&2; usage ;;
  esac
  shift 2
done
case "$TIMEOUT" in ''|*[!0-9]*) echo "peer-ask: --timeout must be a whole number of seconds" >&2; exit 2 ;; esac

# Fold every control byte to a space (CR would submit early, tab is a keypress,
# ^C is a signal), then collapse runs. Newlines fold too: one line per prompt.
TEXT="$(printf '%s' "$TEXT" | tr '\000-\037\177' ' ' | sed 's/  */ /g; s/^ //; s/ $//')"
[ -n "$TEXT" ] || { echo "peer-ask: empty prompt" >&2; exit 2; }

TMUX_BIN="$(command -v tmux || echo /usr/local/bin/tmux)"
# PEER_ASK_SOCKET is a test hook (private -L server). No arrays here: macOS
# bash 3.2 aborts on an empty array under set -u.
t() { "$TMUX_BIN" ${PEER_ASK_SOCKET:+-L "$PEER_ASK_SOCKET"} "$@"; }
t has-session -t "=$SESSION" 2>/dev/null || { echo "peer-ask: no tmux session named '$SESSION'" >&2; exit 2; }
capture() { t capture-pane -t "$SESSION:" -p -J -S -80 2>/dev/null; }

baseline="$(capture)"

# Type in chunks of 100 bytes with a short gap: one long single write failed on
# a live Codex pane (2026-09-04, unexplained, not reproducible offline). The
# `--` keeps a chunk that starts with "-" from being read as a flag.
i=0; n=${#TEXT}
while [ $i -lt $n ]; do
  t send-keys -t "$SESSION" -l -- "${TEXT:$i:100}" || { echo "peer-ask: send-keys failed at offset $i" >&2; exit 2; }
  i=$((i + 100)); sleep 0.15
done
sleep 0.4
t send-keys -t "$SESSION" Enter || exit 2

start=$(date +%s); prev=""; polls=0
sleep 2
while :; do
  if ! t has-session -t "=$SESSION" 2>/dev/null; then
    printf '%s\n' "$prev" | grep -v '^[[:space:]]*$' | tail -40
    echo "peer-ask: session '$SESSION' ended" >&2; exit 4
  fi
  now="$(capture)"
  tail6="$(printf '%s\n' "$now" | grep -v '^[[:space:]]*$' | tail -6)"
  if [ "$now" != "$baseline" ] && [ "$now" = "$prev" ] && printf '%s\n' "$tail6" | grep -qE "$IDLE"; then
    polls=$((polls + 1))
    if [ $polls -ge 2 ]; then
      printf '%s\n' "$now" | grep -v '^[[:space:]]*$' | tail -40
      echo "peer-ask: replied in $(( $(date +%s) - start )) s"; exit 0
    fi
  else
    polls=0
  fi
  prev="$now"
  if [ $(( $(date +%s) - start )) -ge "$TIMEOUT" ]; then
    printf '%s\n' "$now" | grep -v '^[[:space:]]*$' | tail -40
    echo "peer-ask: TIMEOUT after $TIMEOUT s (session may still be working)" >&2; exit 3
  fi
  sleep 2
done
