#!/bin/bash
# Tests for peer-ask.sh. Runs on a private tmux server (socket peer-ask-test) whose
# only pane exits by itself after one read, so no kill verb is ever needed.
S=~/.claude/scripts/peer-ask.sh; pass=0; fail=0
ok() { pass=$((pass+1)); echo "ok   $1"; }; bad() { fail=$((fail+1)); echo "FAIL $1"; }
# 1. the script never contains a control-key or destructive tmux verb
if grep -nE 'kill-(session|server|pane|window)|paste-buffer|pipe-pane|respawn|C-[a-z]|send-keys[^|]*(Escape|BSpace|Tab|C-c)' "$S" >/dev/null; then bad "forbidden verb present"; else ok "only literal text + Enter + capture"; fi
# 2. usage errors
"$S" >/dev/null 2>&1; [ $? -eq 2 ] && ok "no session -> exit 2" || bad "no session exit code"
"$S" nope-session -m hi >/dev/null 2>&1; [ $? -eq 2 ] && ok "missing session -> exit 2" || bad "missing session exit code"
# 3. round trip on a private server: the pane reads one line, echoes it, prints an idle marker
SN=t$$; tmux -L peer-ask-test new-session -d -s "$SN" -x 160 -y 20 'IFS= read -r x; echo "GOT:$x"; echo "› "; sleep 90' || { bad "scratch server"; exit 1; }
LONG="Second test (timing): open the Calculator app if it is not already visible, compute 987 x 654 by sending keystrokes to it, and reply with only the number shown in the Calculator window (no other words). Extra padding so this passes one hundred characters."
out="$(PEER_ASK_SOCKET=peer-ask-test "$S" "$SN" -m "$LONG" --timeout 20 --idle '^› *$')"; rc=$?
[ $rc -eq 0 ] && ok "exit 0 on reply" || bad "exit $rc on reply"
printf '%s' "$out" | tr -d '\n' | grep -qF "GOT:$LONG" && ok "long prompt with parentheses arrived intact (chunked)" || bad "prompt mangled: $(printf '%s' "$out" | grep GOT | cut -c1-80)"
printf '%s' "$out" | grep -qE 'replied in [0-9]+ s' && ok "reports elapsed time" || bad "no elapsed line"
echo "$pass/$((pass+fail)) passed"; [ $fail -eq 0 ]
