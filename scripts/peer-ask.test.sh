#!/bin/bash
# Tests for peer-ask.sh. Runs on a private tmux server (socket peer-ask-test) whose
# panes exit by themselves, so no kill verb is ever needed.
S=~/.claude/scripts/peer-ask.sh; pass=0; fail=0
ok() { pass=$((pass+1)); echo "ok   $1"; }; bad() { fail=$((fail+1)); echo "FAIL $1"; }
FORBID='kill-?(session|server|pane|window)|kill(p|w)\b|kill-ses|paste-buffer|pipe-pane|respawn|(send-keys|send)[^|]*(Escape|BSpace|Tab|C-|M-)'
# 1. the script never contains a control-key or destructive tmux verb, and the regex catches aliases
if grep -nE "$FORBID" "$S" >/dev/null; then bad "forbidden verb present"; else ok "only literal text + Enter + capture"; fi
for probe in 'x send-keys -t p C-c' 'x kill-session -t p' 'x killp -t p' 'x kill-ses -t p' 'x send -t p Escape' 'x send-keys -t p M-x'; do
  printf '%s\n' "$probe" | grep -qE "$FORBID" && ok "regex catches: $probe" || bad "regex misses: $probe"
done
# 2. usage errors: all exit 2, none hang
"$S" >/dev/null 2>&1; [ $? -eq 2 ] && ok "no session -> exit 2" || bad "no session exit code"
"$S" nope-session -m hi >/dev/null 2>&1; [ $? -eq 2 ] && ok "missing session -> exit 2" || bad "missing session exit code"
"$S" nope-session -m >/dev/null 2>&1; [ $? -eq 2 ] && ok "-m without value -> exit 2" || bad "-m without value"
( "$S" nope-session -f >/dev/null 2>&1 & pid=$!; sleep 2; if kill -0 $pid 2>/dev/null; then kill $pid; exit 9; fi; wait $pid ); rc=$?; [ $rc -eq 2 ] && ok "-f without path -> exit 2 (no spin)" || bad "-f without path rc=$rc"
"$S" nope-session -f /nonexistent/file >/dev/null 2>&1; [ $? -eq 2 ] && ok "-f unreadable -> exit 2" || bad "-f unreadable"
"$S" nope-session -m hi --timeout 3s >/dev/null 2>&1; [ $? -eq 2 ] && ok "--timeout 3s -> exit 2" || bad "--timeout 3s"
# 3. round trip on a private server: the pane reads one line, echoes it, prints an idle marker
pane() { tmux -L peer-ask-test new-session -d -s "$1" -x 160 -y 20 "$2"; }
SN=t$$; pane "$SN" 'IFS= read -r x; echo "GOT:$x"; echo "› "; sleep 90' || { bad "scratch server"; exit 1; }
LONG="-Second test (timing): open the Calculator app if it is not already visible, compute 987 x 654 by sending keystrokes to it, and reply with only the number shown in the Calculator window (no other words). Extra padding so this passes one hundred characters."
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN" -m "$LONG" --timeout 20 --idle '^› *$')"; rc=$?
[ $rc -eq 0 ] && ok "exit 0 on reply" || bad "exit $rc on reply"
printf '%s' "$out" | tr -d '\n' | grep -qF "GOT:$LONG" && ok "long prompt with leading dash and parentheses arrived intact (chunked)" || bad "prompt mangled: $(printf '%s' "$out" | grep GOT | cut -c1-80)"
printf '%s' "$out" | grep -qE 'replied in [0-9]+ s' && ok "reports elapsed time" || bad "no elapsed line"
# 4. CRLF prompt file is folded to one line and arrives whole
F=$(mktemp); printf 'first half of the prompt\r\nsecond half\tof the prompt\r\n' > "$F"
SN2=u$$; pane "$SN2" 'IFS= read -r x; echo "GOT:$x"; echo "› "; sleep 90'
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN2" -f "$F" --timeout 20 --idle '^› *$')"; rm -f "$F"
printf '%s' "$out" | tr -d '\n' | grep -qF "GOT:first half of the prompt second half of the prompt" && ok "CRLF + tab folded, whole prompt delivered" || bad "CRLF folding: $(printf '%s' "$out" | grep GOT | cut -c1-80)"
# 5. a pane that already shows the idle marker and never changes must NOT count as replied
SN3=v$$; pane "$SN3" 'stty -echo; echo "› "; sleep 90'
PEER_ASK_SOCKET=peer-ask-test "$S" "$SN3" -m "hello" --timeout 6 --idle '^› *$' >/dev/null 2>&1; rc=$?
[ $rc -eq 3 ] && ok "unchanged pane -> timeout (turn-start anchor)" || bad "unchanged pane rc=$rc (expected 3)"
echo "$pass/$((pass+fail)) passed"; [ $fail -eq 0 ]
