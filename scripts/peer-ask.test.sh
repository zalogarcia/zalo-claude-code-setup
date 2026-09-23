#!/bin/bash
# Tests for peer-ask.sh. Runs on a private tmux server (socket peer-ask-test) whose
# panes exit by themselves, so no kill verb is ever needed. Reply panes wait 3 s
# before answering, like a real agent, so the post-submit baseline sees no reply.
S=~/.claude/scripts/peer-ask.sh; pass=0; fail=0
ok() { pass=$((pass+1)); echo "ok   $1"; }; bad() { fail=$((fail+1)); echo "FAIL $1"; }
FORBID='kill-?(s|p|w)[a-z-]*|paste-buffer|pipe-pane|respawn|send-prefix|(send-keys|send)[^|]*(-H|-X|Escape|BSpace|Tab|C-|M-|Up|Down|Left|Right|Home|End|PPage|NPage|IC|DC|F[0-9])'
# 1. the script never contains a control-key or destructive tmux verb, and the regex catches aliases
if grep -nE "$FORBID" "$S" >/dev/null; then bad "forbidden verb present"; else ok "only literal text + Enter + capture"; fi
for probe in 'x send-keys -t p C-c' 'x kill-session -t p' 'x killp -t p' 'x kill-ses -t p' 'x kill-serv' 'x kill-w -t p' 'x send -t p Escape' 'x send-keys -t p M-x' 'x send-keys -t p -H 03' 'x send-keys -t p Up' 'x send-prefix -t p' 'x send-keys -t p -X cancel'; do
  printf '%s\n' "$probe" | grep -qE "$FORBID" && ok "regex catches: $probe" || bad "regex misses: $probe"
done
printf '%s\n' 'x send-keys -t p -l -- "hello world"' | grep -qE "$FORBID" && bad "regex false positive on literal send" || ok "regex allows the literal send"
# 2. usage errors: all exit 2, none hang
"$S" >/dev/null 2>&1; [ $? -eq 2 ] && ok "no session -> exit 2" || bad "no session exit code"
"$S" nope-session -m hi >/dev/null 2>&1; [ $? -eq 2 ] && ok "missing session -> exit 2" || bad "missing session exit code"
"$S" nope-session -m >/dev/null 2>&1; [ $? -eq 2 ] && ok "-m without value -> exit 2" || bad "-m without value"
( "$S" nope-session -f >/dev/null 2>&1 & pid=$!; sleep 2; if kill -0 $pid 2>/dev/null; then kill $pid; exit 9; fi; wait $pid ); rc=$?; [ $rc -eq 2 ] && ok "-f without path -> exit 2 (no spin)" || bad "-f without path rc=$rc"
"$S" nope-session -f /nonexistent/file >/dev/null 2>&1; [ $? -eq 2 ] && ok "-f unreadable -> exit 2" || bad "-f unreadable"
"$S" nope-session -m hi --timeout 3s >/dev/null 2>&1; [ $? -eq 2 ] && ok "--timeout 3s -> exit 2" || bad "--timeout 3s"
"$S" nope-session -m '/clear' >/dev/null 2>&1; [ $? -eq 2 ] && ok "/command refused" || bad "/command not refused"
"$S" nope-session -m '!rm -rf x' >/dev/null 2>&1; [ $? -eq 2 ] && ok "!shell refused" || bad "!shell not refused"
# 3. round trip: the pane reads one line, waits like an agent, echoes it, prints a Codex-style idle marker
pane() { tmux -L peer-ask-test new-session -d -s "$1" -x 160 -y 20 "$2"; }
SN=t$$; pane "$SN" 'IFS= read -r x; sleep 3; echo "GOT:$x"; echo "› "; sleep 90' || { bad "scratch server"; exit 1; }
LONG="-Second test (timing): open the Calculator app if it is not already visible, compute 987 x 654 by sending keystrokes to it, and reply with only the number shown in the Calculator window (no other words). Extra padding so this passes one hundred characters."
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN" -m "$LONG" --timeout 25)"; rc=$?
[ $rc -eq 0 ] && ok "exit 0 on reply (default idle regex, Codex-style glyph)" || bad "exit $rc on reply"
printf '%s' "$out" | tr -d '\n' | grep -qF "GOT:$LONG" && ok "long prompt with leading dash and parentheses arrived intact (chunked)" || bad "prompt mangled: $(printf '%s' "$out" | grep GOT | cut -c1-80)"
printf '%s' "$out" | grep -qE 'replied in [0-9]+ s' && ok "reports elapsed time" || bad "no elapsed line"
# 4. Claude Code style peer: answer line then the ❯ prompt glyph, no --idle given
SN4=c$$; pane "$SN4" 'IFS= read -r x; sleep 3; echo "● The answer is 4"; echo "❯ "; sleep 90'
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN4" -m "what is 2+2" --timeout 25)"; rc=$?
[ $rc -eq 0 ] && printf '%s' "$out" | grep -qF "The answer is 4" && ok "Claude-style ❯ prompt detected with the default idle regex" || bad "Claude-style pane rc=$rc"
# 5. CRLF prompt file is folded to one line and arrives whole
F=$(mktemp); printf 'first half of the prompt\r\nsecond half\tof the prompt\r\n' > "$F"
SN2=u$$; pane "$SN2" 'IFS= read -r x; sleep 3; echo "GOT:$x"; echo "› "; sleep 90'
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN2" -f "$F" --timeout 25)"; rm -f "$F"
printf '%s' "$out" | tr -d '\n' | grep -qF "GOT:first half of the prompt second half of the prompt" && ok "CRLF + tab folded, whole prompt delivered" || bad "CRLF folding: $(printf '%s' "$out" | grep GOT | cut -c1-80)"
# 6. a pane that echoes the typed prompt, shows an idle marker, and never replies must NOT count as replied.
#    The stale marker is the Codex placeholder, which every version of the default regex matches, so the
#    post-submit baseline is the only thing standing between this test and a false reply.
SN3=v$$; pane "$SN3" 'echo "• old answer from the previous turn"; echo "› Ask Codex to do anything"; sleep 120'
PEER_ASK_SOCKET=peer-ask-test "$S" "$SN3" -m "what is the capital of France" --timeout 10 >/dev/null 2>&1; rc=$?
[ $rc -eq 3 ] && ok "echoed prompt + stale idle screen -> timeout, not a false reply" || bad "stale screen rc=$rc (expected 3)"
# 7. the real Claude Code composer line is the glyph followed by a NON-BREAKING space, then spaces
SN5=n$$; pane "$SN5" 'IFS= read -r x; sleep 3; echo "● Real answer: Paris"; printf "\xe2\x9d\xaf\xc2\xa0   \n"; sleep 90'
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN5" -m "capital of France" --timeout 25)"; rc=$?
[ $rc -eq 0 ] && printf '%s' "$out" | grep -qF "Real answer: Paris" && ok "Claude glyph + NBSP composer line detected" || bad "NBSP composer rc=$rc"
# 8. blocking prompts (2026-09-23): a fake tmux first on PATH records every call
#    and shows a fixed visible screen, so "nothing was typed" is asserted on the
#    recorded calls. Session names here do not exist on the real server, so even
#    a fall through to the real tmux would stop at has-session with exit 2.
SROOT="$(mktemp -d /tmp/peer-ask-shim.XXXXXX)"; SBIN="$SROOT/bin"; mkdir -p "$SBIN"
cat > "$SBIN/tmux" <<'SHIM'
#!/bin/bash
# fake tmux: $SHIM_STATE/screen is the visible screen, $SHIM_STATE/scroll the
# history above it (only printed when -S is passed, like the real capture-pane).
S="$SHIM_STATE"; printf '%s\n' "$*" >> "$S/calls.log"
cmd="$1"; shift
case "$cmd" in
  has-session) exit 0 ;;
  send-keys)
    last=""; for a in "$@"; do last="$a"; done
    if [ "$last" = "Enter" ]; then touch "$S/entered"; echo 0 > "$S/caps"; exit 0; fi
    printf '%s' "$last" >> "$S/typed"
    # a panel that opens while the text is going in
    [ -f "$S/panel_on_type" ] && cp "$S/panel_on_type" "$S/screen"
    exit 0 ;;
  capture-pane)
    case " $* " in *" -S "*) cat "$S/scroll" 2>/dev/null ;; esac
    cat "$S/screen"
    if [ -f "$S/entered" ]; then
      n=$(cat "$S/caps"); n=$((n+1)); echo $n > "$S/caps"
      if [ "$n" -lt 2 ]; then echo "• Working"; else echo "• pong"; echo "› Ask Codex to do anything"; fi
    elif [ -f "$S/typed" ]; then
      echo "› $(cat "$S/typed")"
    fi
    exit 0 ;;
  *) exit 0 ;;
esac
SHIM
chmod +x "$SBIN/tmux"
# sa <case> <screen text> <peer-ask args...>; SCROLL and PANEL_ON_TYPE from the
# caller's environment. Leaves RC, OUT and CALLS set.
sa() {
  name="$1"; screen="$2"; shift 2
  [ "$(PATH="$SBIN:$PATH" bash -c 'command -v tmux')" = "$SBIN/tmux" ] || { echo "sa $name: fake tmux is not first on PATH, refusing to run" >&2; exit 1; }
  ST="$SROOT/$name"; mkdir -p "$ST"; printf '%s\n' "$screen" > "$ST/screen"; : > "$ST/calls.log"
  [ -n "${SCROLL:-}" ] && printf '%s\n' "$SCROLL" > "$ST/scroll"
  [ -n "${PANEL_ON_TYPE:-}" ] && printf '%s\n' "$PANEL_ON_TYPE" > "$ST/panel_on_type"
  OUT="$(SHIM_STATE="$ST" PATH="$SBIN:$PATH" "$S" shim-peer-$$ "$@" 2>&1)"; RC=$?
  CALLS="$(cat "$ST/calls.log")"
}
sends() { printf '%s\n' "$CALLS" | grep -c '^send-keys'; }
COMPOSER='› Ask Codex to do anything
  gpt-6-astra default · ~ · Main [default]'
HOOKS='› Ask Codex to do anything
Hooks need review
5 hooks need review before they can run.
Press t to trust all; enter to review hooks; esc to close'
UPDATE='✨ Update available! 0.154.0 -> 0.156.1
Release notes: https://github.com/openai/codex/releases/latest
› 1. Update now (runs brew upgrade --cask codex)
  2. Skip
  3. Skip until next version
Press enter to continue'
# one case per listed literal, plus the two full panels as Codex draws them
blk() { # blk <case> <expected label> <screen>
  sa "$1" "$3" -m ping --timeout 10
  [ $RC -eq 5 ] && [ "$(sends)" -eq 0 ] && printf '%s' "$OUT" | grep -qF "BLOCKED by $2" \
    && ok "blocked, zero send-keys, named: $1" || bad "$1: rc=$RC sends=$(sends) out=$OUT"
}
blk hooks-panel 'the Codex hooks review prompt (saw "hooks need review")' "$HOOKS"
blk hooks-line 'the Codex hooks review prompt (saw "hooks need review")' "$COMPOSER
3 hooks need review before they can run."
blk press-t 'the Codex hooks review prompt (saw "Press t to trust")' "Press t to trust all; enter to review hooks; esc to close"
blk update-modal 'the Codex update prompt (saw "Update now (runs")' "$UPDATE"
blk update-option 'the Codex update prompt (saw "Update now (runs")' "› 1. Update now (runs brew upgrade --cask codex)"
# the plain phrase counts where a panel is: no composer on screen
blk update-now-bare 'the Codex update prompt (saw "Update now")' "A new version of Codex is ready.
Update now"
blk skip-until 'the Codex update prompt (saw "Skip until next version")' "  3. Skip until next version"
blk press-enter 'a "Press enter to" prompt (saw "Press enter to")' "Choose how you'd like Codex to proceed.
› Try new model
  Use existing model
Press enter to continue"
blk press-enter-caps 'a "Press enter to" prompt (saw "Press enter to")' "Continuing startup with a fresh local database...
Press Enter to continue."
# Codex animates braille dots into blank cells; they must not hide a prompt,
# not even a dot sitting in a one space word gap
blk braille-dots 'the Codex update prompt (saw "Update now (runs")' "› 1. Update ⠂ now (runs brew upgrade --cask codex)"
blk braille-glued 'the Codex update prompt (saw "Update now (runs")' "› 1. Update⠂now (runs brew upgrade --cask codex)"
blk braille-hooks 'the Codex hooks review prompt (saw "hooks need review")' "5 hooks⠂need review before they can run."
# a picker opened under the last reply: its footer is below the composer glyph line
blk picker 'a "Press enter to" prompt (saw "Press enter to")' "• I opened the model picker.
Select a model
› gpt-6-astra
  gpt-5
Press enter to confirm or esc to go back"
sa hooks-lines "$HOOKS" -m ping --timeout 10
printf '%s' "$OUT" | grep -qF 'on screen: Hooks need review' && ok "refusal prints the pane line it matched" || bad "no pane line: $OUT"
printf '%s' "$OUT" | grep -qF "nothing typed into 'shim-peer-$$'" && ok "refusal says nothing was typed" || bad "refusal text: $OUT"
# --check: the same test, never types
sa check-blocked "$UPDATE" --check
[ $RC -eq 5 ] && [ "$(sends)" -eq 0 ] && ok "--check on the update prompt -> exit 5, zero send-keys" || bad "--check blocked rc=$RC sends=$(sends)"
sa check-clear "$COMPOSER" --check
[ $RC -eq 0 ] && [ "$(sends)" -eq 0 ] && ok "--check on an idle composer -> exit 0, zero send-keys" || bad "--check clear rc=$RC sends=$(sends) out=$OUT"
# not a prompt: the passive banner Codex prints on every start while an update
# is dismissed shares the "Update available!" literal with the modal
sa passive "✨ Update available! 0.154.0 -> 0.156.1
Run brew upgrade --cask codex to update.
See full release notes: https://github.com/openai/codex/releases/latest
$COMPOSER" -m ping --timeout 20
[ $RC -eq 0 ] && printf '%s\n' "$CALLS" | grep -q -- '-l -- ping$' && printf '%s\n' "$CALLS" | grep -q ' Enter$' && ok "passive Update available banner: ping typed and sent, exit 0" || bad "passive banner rc=$RC out=$OUT"
# not a prompt: the words only in the scrollback, above the visible screen
SCROLL="$UPDATE" sa scrollback "$COMPOSER" -m ping --timeout 20
[ $RC -eq 0 ] && [ "$(sends)" -ge 2 ] && ok "prompt text only in the scrollback: ping sent, exit 0" || bad "scrollback rc=$RC sends=$(sends) out=$OUT"
# not a prompt: an old answer quoting the words, more than 15 lines above the bottom
sa far-above "• Earlier I saw the Update now option and a hooks need review line.
$(for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16; do echo "  report line $i"; done)
$COMPOSER" -m ping --timeout 20
[ $RC -eq 0 ] && [ "$(sends)" -ge 2 ] && ok "words more than 15 lines above the bottom: ping sent, exit 0" || bad "far above rc=$RC sends=$(sends) out=$OUT"
# not a prompt: a reply ABOVE the idle composer using the everyday phrases (the
# QA reproduction: this used to lock the peer out with exit 5)
sa prose-update "• Want me to apply the update now, or wait until tonight?
  Press enter to confirm is what the dialog said, so I stopped there.
$COMPOSER" -m ping --timeout 20
[ $RC -eq 0 ] && [ "$(sends)" -ge 2 ] && ok "a reply saying \"update now\" and \"press enter to\" above the composer: ping sent, exit 0" || bad "prose above composer rc=$RC sends=$(sends) out=$OUT"
sa prose-check "• Want me to apply the update now?
$COMPOSER" --check
[ $RC -eq 0 ] && ok "--check does not flag a reply above the composer" || bad "--check prose rc=$RC out=$OUT"
# the message itself carries a listed literal: it sits in the composer before
# Enter, and the re-check must not refuse on it
sa self-quote "$COMPOSER" -m "what does Update now do" --timeout 20
[ $RC -eq 0 ] && printf '%s\n' "$CALLS" | grep -q ' Enter$' && ok "a message quoting \"Update now\" is still sent" || bad "self quote rc=$RC out=$OUT"
# a panel that opens while the text is going in: typed, but Enter NOT pressed
PANEL_ON_TYPE="$HOOKS" sa late-panel "$COMPOSER" -m ping --timeout 10
[ $RC -eq 5 ] && ! printf '%s\n' "$CALLS" | grep -q ' Enter$' && printf '%s' "$OUT" | grep -qF 'Enter was NOT pressed' && ok "panel opens mid typing -> exit 5, Enter never pressed" || bad "late panel rc=$RC calls=$CALLS out=$OUT"
# the usage text documents the new exit code
"$S" 2>&1 | grep -qF '5 blocking prompt on screen' && ok "usage text documents exit 5" || bad "usage text lacks exit 5"
# "Update available" stays off the list on purpose (the passive banner)
sed -n "/^BLOCKING_PROMPTS=/,/prompt'\$/p" "$S" | grep -qi 'update available' && bad "Update available is a listed literal" || ok "Update available is not a listed literal"
rm -rf "$SROOT"
echo "$pass/$((pass+fail)) passed"; [ $fail -eq 0 ]
