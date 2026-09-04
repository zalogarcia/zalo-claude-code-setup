#!/bin/bash
# peer-ask.sh: send ONE prompt to a named tmux session and wait for its reply.
#
#   ~/.claude/scripts/peer-ask.sh <session> -m "prompt text" [--timeout 180] [--idle REGEX]
#   ~/.claude/scripts/peer-ask.sh <session> -f /path/prompt.txt [...]
#
# Does exactly the sanctioned peer-message protocol from ~/.claude/CLAUDE.md
# (literal text with `send-keys -l`, then a separate `Enter`, then `capture-pane`
# polling) in one call, so a Claude session does not spend 6 to 8 round trips and
# fixed sleeps on it. It NEVER sends control keys, never kills, never pastes:
# peer-ask.test.sh greps this file to keep that true.
#
# Idle detection: the pane counts as "replied" when its last 6 non-empty lines
# match --idle (default covers the Codex TUI composer placeholder and the Claude
# Code prompt hint) AND the pane has not changed between two consecutive polls.
# Prints the pane tail (the reply region) and exits 0; exit 3 on timeout with
# whatever is on screen; exit 4 if the session ends; exit 2 on bad usage.
set -u
SESSION="${1:-}"; shift || true
[ -z "$SESSION" ] && { echo "usage: peer-ask.sh <session> -m TEXT | -f FILE [--timeout N] [--idle REGEX]" >&2; exit 2; }
TEXT=""; TIMEOUT=180; IDLE='Ask Codex to do anything|\? for shortcuts|^[›>] *$'
while [ $# -gt 0 ]; do
  case "$1" in
    -m) TEXT="$2"; shift 2 ;;
    -f) TEXT="$(cat "$2")"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --idle) IDLE="$2"; shift 2 ;;
    *) echo "peer-ask: unknown arg $1" >&2; exit 2 ;;
  esac
done
[ -z "$TEXT" ] && { echo "peer-ask: empty prompt" >&2; exit 2; }
TMUX_BIN="$(command -v tmux || echo /usr/local/bin/tmux)"
# PEER_ASK_SOCKET is a test hook (private -L server). No arrays here: macOS
# bash 3.2 aborts on an empty array under set -u.
t() { "$TMUX_BIN" ${PEER_ASK_SOCKET:+-L "$PEER_ASK_SOCKET"} "$@"; }
t has-session -t "=$SESSION" 2>/dev/null || { echo "peer-ask: no tmux session named '$SESSION'" >&2; exit 2; }

# Newlines would submit early in most TUIs; fold the prompt onto one line.
TEXT="$(printf '%s' "$TEXT" | tr '\n' ' ' | sed 's/  */ /g')"

# Type in chunks of 100 chars with a short gap: one long single write failed on
# a live Codex pane (2026-09-04, unexplained, not reproducible offline).
i=0; n=${#TEXT}
while [ $i -lt $n ]; do
  t send-keys -t "$SESSION" -l "${TEXT:$i:100}" || { echo "peer-ask: send-keys failed at offset $i" >&2; exit 2; }
  i=$((i + 100)); sleep 0.15
done
sleep 0.4
t send-keys -t "$SESSION" Enter || exit 2

capture() { t capture-pane -t "$SESSION:" -p -J -S -80 2>/dev/null; }
start=$(date +%s); prev=""; polls=0
sleep 2
while :; do
  if ! t has-session -t "=$SESSION" 2>/dev/null; then
    printf '%s\n' "$prev" | grep -v '^[[:space:]]*$' | tail -40
    echo "peer-ask: session '$SESSION' ended" >&2; exit 4
  fi
  now="$(capture)"
  tail6="$(printf '%s\n' "$now" | grep -v '^[[:space:]]*$' | tail -6)"
  if [ "$now" = "$prev" ] && printf '%s\n' "$tail6" | grep -qE "$IDLE"; then
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
