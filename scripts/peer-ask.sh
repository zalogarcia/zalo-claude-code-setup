#!/bin/bash
# peer-ask.sh: send ONE prompt to a named tmux session and wait for its reply.
#
#   ~/.claude/scripts/peer-ask.sh <session> -m "prompt text" [--timeout 180] [--idle REGEX]
#   ~/.claude/scripts/peer-ask.sh <session> -f /path/prompt.txt [...]
#   ~/.claude/scripts/peer-ask.sh <session> --check     (types nothing, see below)
#
# Does exactly the sanctioned peer-message protocol from ~/.claude/CLAUDE.md
# (literal text with `send-keys -l --`, then a separate `Enter`, then
# `capture-pane` polling) in one call, so a Claude session does not spend 6 to 8
# round trips and fixed sleeps on it. It never sends control keys: every control
# byte in the prompt (CR, tab, ESC, ^C, ...) becomes a space before sending (NUL
# is dropped by the shell), prompts starting with "/" or "!" are refused (slash
# commands and shell escapes are not messages), and peer-ask.test.sh greps this
# file for forbidden verbs.
#
# Reply detection: a baseline is captured 1.5 s AFTER Enter, so the echoed prompt
# and the peer's first spinner are already in it. The pane counts as "replied"
# when it differs from that baseline (the peer rendered something new), its last
# 6 non-empty lines match --idle (default: the Codex composer placeholder, the
# Claude Code prompt glyph followed by the non-breaking space it prints, the
# Claude Code permissions footer; alternation, not a bracket class, because grep
# reads multibyte glyphs bytewise without a locale), and it has not
# changed across three consecutive 2 s polls. A peer that finishes inside the
# 1.5 s settle window is not detected (real agents never do); a peer that never
# reacts times out.
#
# Blocking prompts (2026-09-23): before typing anything, and again right before
# Enter, it reads the VISIBLE screen and refuses to type when a panel there is
# waiting for an answer, because whatever it types becomes that answer. That
# morning a probe's "ping" plus Enter went into the Codex hooks review panel,
# and another one picked "Update now" on the Codex update prompt, which quit
# Codex to run brew. Trusting hooks and taking an update are the owner's calls,
# so it exits 5 and names the prompt instead. The match is literal text, case
# insensitive, over the last 15 non empty lines of the visible screen, never the
# scrollback. Phrases ordinary prose also uses ("update now", "press enter to")
# only count on the lines UNDER the last composer line: replies are drawn above
# the composer and panels in its place, so a reply saying "apply the update now?"
# does not lock the peer out. The list is BLOCKING_PROMPTS below. --check runs
# only that test: exit 0 clear, 5 blocked, and it never types (the refresh
# script uses it before its own /new).
#
# Exit 0 replied, 2 usage error or no such session, 3 timeout, 4 session ended,
# 5 a blocking prompt is on screen (Enter never goes into it; the output names
# it, and its last line says whether any text had gone in first, which only
# happens when the panel opened while the text was being typed).
set -u
usage() { echo "usage: peer-ask.sh <session> -m TEXT | -f FILE [--timeout SECONDS] [--idle REGEX] | --check   (exit 0 replied, 2 usage, 3 timeout, 4 session ended, 5 blocking prompt on screen)" >&2; exit 2; }
SESSION="${1:-}"; [ -n "$SESSION" ] || usage
shift
TEXT=""; TIMEOUT=180; IDLE='Ask Codex to do anything|^(›|>|❯)( | )*$|bypass permissions on'; CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    -m|-f|--timeout|--idle) [ $# -ge 2 ] || { echo "peer-ask: $1 needs a value" >&2; exit 2; } ;;
  esac
  case "$1" in
    -m) TEXT="$2" ;;
    -f) [ -r "$2" ] || { echo "peer-ask: cannot read prompt file '$2'" >&2; exit 2; }; TEXT="$(cat "$2")" ;;
    --timeout) TIMEOUT="$2" ;;
    --idle) IDLE="$2" ;;
    --check) CHECK_ONLY=1; shift; continue ;;
    *) echo "peer-ask: unknown arg '$1'" >&2; usage ;;
  esac
  shift 2
done
case "$TIMEOUT" in ''|*[!0-9]*) echo "peer-ask: --timeout must be a whole number of seconds" >&2; exit 2 ;; esac

if [ "$CHECK_ONLY" -eq 0 ]; then
  # Fold every control byte to a space (CR would submit early, tab is a keypress,
  # ^C is a signal), collapse runs, trim. Newlines fold too: one line per prompt.
  TEXT="$(printf '%s' "$TEXT" | tr '\000-\037\177' ' ' | sed 's/  */ /g; s/^ //; s/ $//')"
  [ -n "$TEXT" ] || { echo "peer-ask: empty prompt" >&2; exit 2; }
  case "$TEXT" in
    /*|!*) echo "peer-ask: a prompt starting with '/' or '!' is a command to the peer, not a message; refused" >&2; exit 2 ;;
  esac
fi

TMUX_BIN="$(command -v tmux || echo /usr/local/bin/tmux)"
# PEER_ASK_SOCKET is a test hook (private -L server). No arrays here: macOS
# bash 3.2 aborts on an empty array under set -u.
t() { "$TMUX_BIN" ${PEER_ASK_SOCKET:+-L "$PEER_ASK_SOCKET"} "$@"; }
t has-session -t "=$SESSION" 2>/dev/null || { echo "peer-ask: no tmux session named '$SESSION'" >&2; exit 2; }
# Codex 0.154.0 (2026-09-11) animates braille dots (U+2800 to U+28FF) around the
# composer on every frame, so a raw capture never matches its previous poll and
# every ask timed out on an idle session. Strip that block and trailing blanks
# before comparing; nothing a peer types or replies uses those code points.
# The dots also sit INSIDE lines (between the composer glyph and its placeholder,
# and in otherwise blank lines), so once they are gone the leftover runs of
# spaces still differ from frame to frame; collapse every run to one space.
# And the blinking cursor sits right after the composer glyph, so that line
# alternates between "›Ask Codex" and "› Ask Codex": pin exactly one space there.
capture() { t capture-pane -t "$SESSION:" -p -J -S -80 2>/dev/null | perl -CSD -pe 's/[\x{2800}-\x{28FF}]//g; s/[ \t]+/ /g; s/ $//; s/^([\x{203A}>\x{276F}]) ?/$1 /'; }

# Panels that take the next keypress as an ANSWER. One per line, tab separated:
# the literal text, where it counts, the name printed when it matches.
#   any    anywhere in the window: phrases only the panel itself prints
#   below  only under the last composer line (a line starting with the Codex
#          glyph U+203A or the Claude Code glyph U+276F), or anywhere when no
#          composer is on screen, which is what a panel drawn in its place looks
#          like: phrases a reply can also contain
# Every "press enter to" string in the Codex 0.154.0 binary sits in a modal or
# picker (update, model migration, database recovery, plugins, apps). The update
# modal's selected option line starts with the composer glyph too, which is why
# its own option text is also listed as an "any" literal.
# "Update available" is deliberately NOT listed: the same "Update available!"
# literal also heads a passive banner Codex prints on every start while an update
# is dismissed but not installed (one string in the binary serves both), and
# matching it would refuse every ping until the upgrade.
BLOCKING_PROMPTS='hooks need review	any	the Codex hooks review prompt
Press t to trust	any	the Codex hooks review prompt
Update now (runs	any	the Codex update prompt
Skip until next version	any	the Codex update prompt
Update now	below	the Codex update prompt
Press enter to	below	a "Press enter to" prompt'
TAB="$(printf '\t')"
BLOCK_LIT=""; BLOCK_LABEL=""; BLOCK_LINE=""
# blocking_prompt [typed-text]: 0 and BLOCK_* set when a listed literal is on the
# visible screen. A literal that also occurs in typed-text is skipped, so the
# re-check before Enter does not trip on the message sitting in the composer.
# Braille animation dots become spaces, not nothing: they only ever fill blank
# cells, and deleting one that sits in a word gap would glue two words together.
blocking_prompt() {
  skip="${1:-}"
  screen="$(t capture-pane -t "$SESSION:" -p -J 2>/dev/null | perl -CSD -pe 's/[\x{2800}-\x{28FF}]/ /g; s/[ \t]+/ /g; s/^ //; s/ $//' | grep -v '^$' | tail -15)"
  [ -n "$screen" ] || return 1
  below="$screen"; i=0; last=0
  while IFS= read -r l; do
    i=$((i + 1))
    case "$l" in "›"*|"❯"*) last=$i ;; esac
  done <<EOF
$screen
EOF
  [ "$last" -gt 0 ] && below="$(printf '%s\n' "$screen" | sed -n "$((last + 1)),\$p")"
  while IFS="$TAB" read -r lit scope label; do
    [ -n "$lit" ] || continue
    if [ -n "$skip" ] && printf '%s\n' "$skip" | grep -qiF -- "$lit"; then continue; fi
    if [ "$scope" = below ]; then hay="$below"; else hay="$screen"; fi
    [ -n "$hay" ] || continue
    line="$(printf '%s\n' "$hay" | grep -iF -m1 -- "$lit")" || continue
    BLOCK_LIT="$lit"; BLOCK_LABEL="$label"; BLOCK_LINE="$line"
    return 0
  done <<EOF
$BLOCKING_PROMPTS
EOF
  return 1
}
refuse_blocked() {
  echo "peer-ask: BLOCKED by $BLOCK_LABEL (saw \"$BLOCK_LIT\")" >&2
  echo "peer-ask: on screen: $BLOCK_LINE" >&2
  echo "peer-ask: $1; answering that prompt is the owner's decision" >&2
  exit 5
}
if blocking_prompt; then refuse_blocked "nothing typed into '$SESSION'"; fi
if [ "$CHECK_ONLY" -eq 1 ]; then echo "peer-ask: no blocking prompt on '$SESSION'"; exit 0; fi

# Type in chunks of 100 bytes with a short gap: one long single write failed on
# a live Codex pane (2026-09-04, unexplained, not reproducible offline). The
# `--` keeps a chunk that starts with "-" from being read as a flag.
i=0; n=${#TEXT}
while [ $i -lt $n ]; do
  t send-keys -t "$SESSION" -l -- "${TEXT:$i:100}" || { echo "peer-ask: send-keys failed at offset $i" >&2; exit 2; }
  i=$((i + 100)); sleep 0.15
done
sleep 0.4
# Once more right before Enter: a panel that opened while the text was going in
# (a session still starting up) would take this Enter as its answer.
if blocking_prompt "$TEXT"; then refuse_blocked "the text is in the pane but Enter was NOT pressed"; fi
t send-keys -t "$SESSION" Enter || exit 2
start=$(date +%s)
sleep 1.5
baseline="$(capture)"

prev=""; polls=0
while :; do
  if ! t has-session -t "=$SESSION" 2>/dev/null; then
    printf '%s\n' "$prev" | grep -v '^[[:space:]]*$' | tail -40
    echo "peer-ask: session '$SESSION' ended" >&2; exit 4
  fi
  now="$(capture)"
  # PEER_ASK_DEBUG=<file>: append every normalized poll, to see what keeps a
  # pane from reading as stable (the Codex 0.154.0 animation was found this way).
  [ -n "${PEER_ASK_DEBUG:-}" ] && printf '=== poll %s\n%s\n' "$(date +%s)" "$now" >> "$PEER_ASK_DEBUG"
  tail6="$(printf '%s\n' "$now" | grep -v '^[[:space:]]*$' | tail -6)"
  if [ "$now" != "$baseline" ] && [ "$now" = "$prev" ] && printf '%s\n' "$tail6" | grep -qE "$IDLE"; then
    polls=$((polls + 1))
    if [ $polls -ge 3 ]; then
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
