#!/usr/bin/env python3
"""Behaviour suite for telegram-edit-guard.

Run: python3 ~/.claude/hooks/telegram-edit-guard.test.py
Must stay green: this is a PreToolUse hook on every Bash call, and a broken
one either blocks every call or lets an edit-to-check through again.

The suite tests the hook that sits NEXT TO it. TG_EDIT_GUARD_HOOK=<path>
points it at another file (an allow-everything stub must fail the BLOCK
cases). Fixtures only: nothing here talks to Telegram. Ids are neutral and
the one token literal is built at runtime, so no token-shaped string sits in
this file.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("TG_EDIT_GUARD_HOOK") or os.path.join(HERE, "telegram-edit-guard.py")
BLOCK, ALLOW = 2, 0
API = "https://api.telegram.org/bot$TOK"
FAKE_TOKEN = "1234567890:" + "A" * 35

passed = failed = 0


def run(payload):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    p = subprocess.run([sys.executable, HOOK], input=raw, capture_output=True, text=True)
    return p.returncode, p.stderr


def bash(cmd):
    return {"session_id": "tg-edit-test", "hook_event_name": "PreToolUse",
            "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp"}


def check(label, payload, want):
    global passed, failed
    rc, err = run(payload)
    if rc == want:
        passed += 1
        print(f"  PASS  {label} (exit {rc})")
    else:
        failed += 1
        print(f"  FAIL  {label}: exit {rc}, wanted {want}")
        if err:
            print("        stderr: " + err.splitlines()[0])


BLOCKED = [
    # --- the three real shapes of 2026-10-02 (ids neutralised) ---
    ("REAL bg64: curl editMessageCaption -F caption=<file, re-sent caption as a probe",
     f'TOKEN=$(jq -r .env.TELEGRAM_BOT_TOKEN ~/.claude/settings.local.json); cd /tmp/x; '
     f'curl -sS -X POST "https://api.telegram.org/bot${{TOKEN}}/editMessageCaption" -F chat_id=111 '
     f'-F message_id=21231 -F "caption=<caption.txt" > probe1.json; echo "EXIT=$?"; jq -c "{{ok}}" probe1.json'),
    ("REAL bg64 as briefed: curl editMessageCaption with --data-urlencode",
     f'curl -s "{API}/editMessageCaption" -d chat_id=$CID -d message_id=21231 '
     f'--data-urlencode "caption=Kickoff deck v3, same caption"'),
    ("REAL bg72 verifier: curl editMessageReplyMarkup in a loop over ids",
     f'for id in 21318 21319 21320 21321 21322; do curl -s -X POST "{API}/editMessageReplyMarkup" '
     f'-d chat_id=$CID -d message_id=$id; echo; done'),
    ("REAL bg72 verifier: probe script written as a .sh heredoc",
     "cat > /tmp/qa-thumbs/tg-probe.sh <<'EOF'\n#!/bin/bash\n"
     "TOK=$(python3 -c \"import json;print(json.load(open('/x/settings.local.json'))['env']['TELEGRAM_BOT_TOKEN'])\")\n"
     "API=\"https://api.telegram.org/bot$TOK\"\n"
     "probe() { curl -s -X POST \"$API/editMessageReplyMarkup\" -d chat_id=111 -d message_id=\"$1\"; echo; }\n"
     "for id in 21318 21319; do probe $id; done\nEOF\nchmod +x /tmp/qa-thumbs/tg-probe.sh"),
    ("REAL bg72 verifier: probe script written as a .py heredoc",
     "cat > /tmp/qa-thumbs/tg-probe.py <<'EOF'\nimport json, urllib.request, urllib.parse\n"
     "tok = json.load(open('/x/settings.local.json'))['env']['TELEGRAM_BOT_TOKEN']\n"
     "BASE = f\"https://api.telegram.org/bot{tok}/\"\n"
     "def call(m, **p):\n    return urllib.request.urlopen(BASE + m, urllib.parse.urlencode(p).encode()).read()\n"
     "for i in (21318, 21319):\n    print(call('editMessageReplyMarkup', chat_id=111, message_id=i))\nEOF"),
    ("REAL shape: node -e fetch to editMessageText",
     "node -e \"fetch('https://api.telegram.org/bot'+process.env.TELEGRAM_BOT_TOKEN+'/editMessageText',"
     "{method:'POST',headers:{'content-type':'application/json'},"
     "body:JSON.stringify({chat_id:111,message_id:21104,text:'x'})}).then(r=>r.json()).then(console.log)\""),
    ("REAL M 21104: editMessageText loop with --data-urlencode text@file piped to jq",
     f"TOK=$(jq -r .env.TELEGRAM_BOT_TOKEN ~/.claude/settings.local.json); C=111\n"
     f"for id in 21104 21105; do printf 'id %s: ' $id; curl -sS -X POST \"{API}/editMessageText\" "
     f"-d chat_id=$C -d message_id=$id --data-urlencode text@/tmp/intro.txt | jq -r '.description // .ok'; done"),
    ("REAL shape: editMessageMedia replacing a document",
     f'curl -s -F chat_id=$CID -F message_id=21092 -F media="$MEDIA" -F doc=@prev.mp4 "{API}/editMessageMedia"'),
    # --- the method somewhere other than the URL literal ---
    ("method in a shell variable", f'M=editMessageText; curl -s "{API}/$M" -d chat_id=$CID -d message_id=5'),
    ("method in an exported variable, used later", f'export METHOD=editMessageCaption && curl -s "{API}/$METHOD" -d message_id=5'),
    ("method in a -d data field", f'curl -s "{API}/" -d method=editMessageCaption -d message_id=5'),
    ("python3 -c urllib editMessageCaption",
     "python3 -c \"import os,urllib.request as u; u.urlopen('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']"
     "+'/editMessageCaption', data=b'chat_id=1&message_id=2&caption=x')\""),
    ("python heredoc (python3 - <<PY) with the method in a variable",
     "cd /tmp/x && python3 - <<'PY'\nimport json, urllib.request\nm = 'editMessageCaption'\n"
     "url = f\"https://api.telegram.org/bot{TOK}/{m}\"\nurllib.request.urlopen(url, b'{}')\nPY"),
    ("node heredoc", "node --input-type=module <<'EOF'\nawait fetch(`https://api.telegram.org/bot${process.env.T}/editMessageText`)\nEOF"),
    ("cat heredoc piped into node",
     "cat <<'EOF' | node\nfetch('https://api.telegram.org/bot'+t+'/editMessageReplyMarkup')\nEOF"),
    ("echo piped into bash", f"echo 'curl -s {API}/editMessageText -d message_id=5' | bash"),
    ("bash -c inline", f"bash -c 'curl -s \"{API}/editMessageCaption\" -d message_id=5'"),
    ("inside $( ) of an echo", f'echo "result: $(curl -s {API}/editMessageMedia -F message_id=5)"'),
    ("xargs over ids",
     f"printf '%s\\n' 21318 21319 | xargs -I{{}} curl -s \"{API}/editMessageReplyMarkup\" -d message_id={{}}"),
    ("lowercase method (the Bot API is case-insensitive)", f'curl -s "{API}/editmessagetext" -d message_id=5'),
    ("snake_case python-telegram-bot edit_message_caption",
     "python3 -c \"import os, telegram; b = telegram.Bot(os.environ['TELEGRAM_BOT_TOKEN']); "
     "b.edit_message_caption(chat_id=1, message_id=2, caption='x')\""),
    ("host in a variable, /bot$TOK/ path is the signal", 'curl -s "$TG_BASE/bot$TOK/editMessageLiveLocation" -d message_id=5'),
    ("bot token literal is the signal", f'curl -s "$BASE/bot{FAKE_TOKEN}/editMessageText" -d message_id=5'),
    ("echo > a .py file writes a probe script",
     "echo \"import urllib.request; urllib.request.urlopen('https://api.telegram.org/bot'+T+'/editMessageText')\" > /tmp/p.py"),
    ("heredoc through tee into a .mjs file",
     "cat <<'EOF' | tee /tmp/probe.mjs\nfetch('https://api.telegram.org/bot'+t+'/editMessageCaption')\nEOF"),
    ("extensionless script file with a #! body",
     "cat > /tmp/probe <<'EOF'\n#!/bin/bash\ncurl -s \"https://api.telegram.org/bot$T/editMessageText\" -d message_id=5\nEOF"),
    ("the skill's escaped-quote JSON body does not hide an edit method in the URL",
     "curl -s -X POST \"https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/editMessageText\" -H \"Content-Type: application/json\" "
     "-d \"{\\\"chat_id\\\": \\\"${TELEGRAM_CHAT_ID}\\\", \\\"message_id\\\": 21400, \\\"text\\\": \\\"new text\\\"}\""),
    ("an escaped-quote JSON method entry is still a method",
     "curl -s \"https://api.telegram.org/bot$TOK/\" -d \"{\\\"method\\\": \\\"editMessageCaption\\\", \\\"message_id\\\": 5}\""),
    ("a text field does not hide the method in the URL",
     f'curl -s "{API}/editMessageText" -d chat_id=$CID -d message_id=5 --data-urlencode "text=hello world"'),
    # --- the override, misused ---
    ("TG_EDIT_OK=1 with no reason comment",
     f'TG_EDIT_OK=1 curl -s "{API}/editMessageCaption" -d chat_id=$CID -d message_id=5 -F "caption=<c.txt"'),
    ("TG_EDIT_OK=1 with a one-word comment", f'TG_EDIT_OK=1 curl -s "{API}/editMessageText" -d message_id=5  # ok'),
    ("TG_EDIT_OK=1 not at the start",
     f'curl -s "{API}/editMessageText" -d message_id=5; TG_EDIT_OK=1  # fixing my own typo in message 21400'),
    ("TG_EDIT_OK=0", f'TG_EDIT_OK=0 curl -s "{API}/editMessageText" -d message_id=5  # fixing my own typo in 21400'),
]

ALLOWED = [
    # --- sends and reads ---
    ("sendMessage", f'curl -s "{API}/sendMessage" -d chat_id=$CID --data-urlencode text@/tmp/msg.txt'),
    ("sendPhoto", f'curl -s -X POST "{API}/sendPhoto" -F chat_id=$CID -F photo=@/tmp/a.png'),
    ("sendDocument with a caption",
     f'curl -s -X POST "{API}/sendDocument" -F chat_id=$CID -F document=@/tmp/a.mp4 '
     f'--form-string "caption=P2 v11" -F disable_content_type_detection=true -o send.json'),
    ("sendMediaGroup", f'curl -s "{API}/sendMediaGroup" -F chat_id=$CID -F media=@/tmp/m.json'),
    ("getUpdates", f'curl -s "{API}/getUpdates?offset=-1"'),
    ("getMe", f'curl -s "{API}/getMe"'),
    ("getUpdates filtered for edited_message", f"curl -s \"{API}/getUpdates\" | jq '.result[] | select(.edited_message)'"),
    # --- sends that only MENTION an edit method in their text or caption ---
    ("sendMessage whose text mentions edit methods",
     f'curl -s "{API}/sendMessage" -d chat_id=$CID '
     f'--data-urlencode "text=telegram-edit-guard now blocks editMessageCaption and editMessageReplyMarkup"'),
    ("sendDocument whose caption mentions editMessageCaption",
     f"curl -s \"{API}/sendDocument\" -F document=@r.pdf --form-string 'caption=editMessageCaption is blocked now'"),
    ("node -e sendMessage with text: mentioning editMessageText",
     "node -e \"fetch('https://api.telegram.org/bot'+process.env.TELEGRAM_BOT_TOKEN+'/sendMessage',"
     "{method:'POST',body:JSON.stringify({chat_id:1,text:'the editMessageText guard is live'})})\""),
    ("the telegram skill's JSON sendMessage (escaped quotes) whose text mentions a method",
     "curl -s -X POST \"https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage\" -H \"Content-Type: application/json\" "
     "-d \"{\\\"chat_id\\\": \\\"${TELEGRAM_CHAT_ID}\\\", \\\"text\\\": \\\"telegram-edit-guard is live: it blocks "
     "editMessageCaption probes\\\", \\\"parse_mode\\\": \\\"Markdown\\\"}\""),
    ("python urlencode sendMessage with a 'text' entry mentioning edit methods",
     "python3 -c \"import urllib.request as u, urllib.parse as p; u.urlopen('https://api.telegram.org/bot'+T+'/sendMessage', "
     "p.urlencode({'chat_id': 1, 'text': 'editMessageText is blocked now'}).encode())\""),
    # --- prose: searches, commits, briefs ---
    ("grep the bridge source for both", 'grep -rn "editMessageText" ~/dev/claude-telegram-bridge/bridge.mjs | grep "api.telegram.org"'),
    ("rg with a pattern holding both", "rg -n 'api\\.telegram\\.org/bot.*/editMessage' ~/dev/claude-telegram-bridge"),
    ("git commit heredoc mentioning both",
     "cd ~/.claude && git commit -m \"$(cat <<'EOF'\nfeat(hooks): telegram-edit-guard blocks editMessageCaption on api.telegram.org/bot\n\n"
     "Co-Authored-By: Claude <noreply@anthropic.com>\nEOF\n)\""),
    ("brief heredoc into a .md file held in a variable",
     "B=~/.claude/queued-briefs/telegram-edit-guard-1002.md; cat > $B <<'EOF'\n# brief\n"
     "BLOCK a command that calls api.telegram.org/bot with editMessageText or editMessageCaption.\nEOF"),
    ("echo prose with no redirect or pipe", 'echo "never call editMessageText on api.telegram.org to check a message"'),
    ("piping a probe payload into this hook",
     "echo '{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"curl https://api.telegram.org/bot1/editMessageCaption\"}}'"
     " | python3 ~/.claude/hooks/telegram-edit-guard.py; echo \"EXIT=$?\""),
    ("bg.mjs dispatch with --file", "node ~/dev/claude-telegram-bridge/bg.mjs --file /tmp/brief-tg-edit-guard.md"),
    # --- an edit method with no Telegram signal, or Telegram with no edit ---
    ("non-Telegram editMessage endpoint", "curl -s -X POST https://example.com/api/editMessage -d id=1"),
    ("sed over the bridge source", "sed -n '/editMessageText/p' ~/dev/claude-telegram-bridge/bridge.mjs"),
    ("node -e mentioning a method, no Telegram", "node -e \"console.log('editMessageText'.length)\""),
    ("LIMIT: an existing script is opaque (its write is the catch point)", "python3 /tmp/qa-thumbs/tg-probe.py"),
    # --- the override, used as documented ---
    ("TG_EDIT_OK=1 with a trailing reason comment",
     f'TG_EDIT_OK=1 curl -sS "{API}/editMessageCaption" -F chat_id="$CID" -F message_id=21400 '
     f'-F "caption=<cap.txt"  # fixing the typo in my own caption, sent earlier in this run'),
    ("TG_EDIT_OK=1 after a leading reason comment line",
     f'# replacing my own preview 21400 (sent in this run) with the v2 cut\nTG_EDIT_OK=1 curl -s "{API}/editMessageMedia" -F message_id=21400'),
    ("TG_EDIT_OK=1 loop with a reason comment",
     f'TG_EDIT_OK=1; for id in 21400 21401; do curl -s "{API}/editMessageReplyMarkup" -d message_id=$id; done  '
     f'# removing the buttons I added to my own two messages this run'),
]

# The -F trap: curl -F cuts a free-text value at its first ";" (message 21478).
REAL_21478 = "PR #166 merged as 0389cf8c (web live; probe passed)"
FORM_BLOCKED = [
    ("REAL 21478: sendPhoto with -F \"caption=... (web live; probe passed)\"",
     f'curl -s -X POST "https://api.telegram.org/bot${{TELEGRAM_BOT_TOKEN}}/sendPhoto" -F chat_id=$CID '
     f'-F photo=@/tmp/bell.png -F "caption={REAL_21478}" -o send.json'),
    ("-F caption with no ; today (the next one may have one)",
     f'curl -s -X POST "{API}/sendDocument" -F chat_id=$CID -F document=@/tmp/a.mp4 -F "caption=P2 v11"'),
    ("--form long flag on text=", f"curl -s \"{API}/sendMessage\" --form chat_id=$CID --form 'text=web live; probe passed'"),
    ("-F text= on sendMessage, single quotes", f"curl -s \"{API}/sendMessage\" -F chat_id=$CID -F 'text=done; next step'"),
    ("-F caption from a variable", f'CAP="web live; probe passed"; curl -s "{API}/sendPhoto" -F photo=@a.png -F caption="$CAP"'),
    ("-F caption from $(cat file) (the file's ; still cuts it)",
     f'curl -s "{API}/sendPhoto" -F photo=@a.png -F "caption=$(cat /tmp/cap.txt)"'),
    ("heredoc script written to a .sh file, then run",
     "cat > /tmp/send-bell.sh <<'EOF'\n#!/bin/bash\n"
     "curl -s -X POST \"https://api.telegram.org/bot$TOK/sendPhoto\" -F chat_id=111 -F photo=@/tmp/bell.png \\\n"
     f"  -F \"caption={REAL_21478}\"\nEOF\nbash /tmp/send-bell.sh"),
    ("heredoc fed straight into bash",
     f"bash <<'EOF'\ncurl -s \"{API}/sendMessage\" -F chat_id=111 -F \"text=web live; probe passed\"\nEOF"),
    ("multi-line send with \\ continuations (the skill's old shape)",
     "curl -s -X POST \"https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto\" \\\n"
     "  -F \"chat_id=${TELEGRAM_CHAT_ID}\" \\\n  -F \"photo=@/path/to/image.png\" \\\n  -F \"caption=Optional caption here\""),
    ("API base in a variable, the field in a later stage",
     'API="https://api.telegram.org/bot$TOK"; curl -s "$API/sendPhoto" -F photo=@a.png -F "caption=done; next"'),
    ("attached -Fcaption=", f'curl -s "{API}/sendPhoto" -F photo=@a.png -Fcaption=hi'),
    ("bundled -sSF", f'curl -sSF "caption=web live; probe passed" -F photo=@a.png "{API}/sendPhoto"'),
    ("question= on sendPoll", f'curl -s "{API}/sendPoll" -F chat_id=1 -F "question=Ship it; or wait?" -F options=\'["yes","no"]\''),
    ("explanation= on a quiz poll", f'curl -s "{API}/sendPoll" -F chat_id=1 -F "explanation=because; reasons"'),
    ("UNQUOTED -F caption=<cap.txt is a shell redirect (sends an empty caption)",
     f'curl -s "{API}/sendPhoto" -F photo=@a.png -F caption=<cap.txt'),
    ("-F caption=@file uploads a file part, not text", f'curl -s "{API}/sendPhoto" -F photo=@a.png -F "caption=@cap.txt"'),
    ("bash -c with -F text=", f"bash -c 'curl -s \"{API}/sendMessage\" -F chat_id=1 -F \"text=a; b\"'"),
    ("for loop over chats", f'for c in 1 2; do curl -s "{API}/sendMessage" -F chat_id=$c -F "text=hi; there"; done'),
    ("python subprocess list: '-F', 'text=...'",
     "python3 -c \"import subprocess; subprocess.run(['curl', '-s', 'https://api.telegram.org/bot'+T+'/sendMessage', "
     "'-F', 'chat_id=1', '-F', 'text=a; b'])\""),
    ("bot token literal as the only signal", f'curl -s "https://x/bot{FAKE_TOKEN}/sendMessage" -F chat_id=1 -F "text=a"'),
    ("inline helper function wrapping curl, the field in the call",
     "TOK=$(jq -r .env.TELEGRAM_BOT_TOKEN ~/.claude/settings.local.json)\n"
     "send() { curl -s -X POST \"https://api.telegram.org/bot$TOK/sendPhoto\" -F chat_id=111 \"$@\"; }\n"
     "send -F photo=@/tmp/board1.png -F \"caption=board 1; draw order 1-6\""),
    ("function keyword helper, called in a loop",
     f'function tg {{ curl -s "{API}/sendMessage" -F chat_id=1 "$@"; }}; for t in a b; do tg -F "text=$t; x"; done'),
    ("LIMIT: a non-Telegram -F text= in a command that also calls Telegram (split the calls)",
     'curl -s -F "text=a; b" https://hooks.example.com/upload && curl -s "https://api.telegram.org/bot$TOK/getMe"'),
    ("TG_EDIT_OK=1 with a reason does not cover the -F trap",
     f'TG_EDIT_OK=1 curl -s "{API}/editMessageCaption" -F chat_id=1 -F message_id=21400 '
     f'-F "caption=fixed; v2"  # fixing the typo in my own caption, sent earlier in this run'),
]

FORM_ALLOWED = [
    ("REAL 21478 shape on --form-string, single quotes",
     f"curl -s -X POST \"https://api.telegram.org/bot${{TELEGRAM_BOT_TOKEN}}/sendPhoto\" -F chat_id=$CID "
     f"-F photo=@/tmp/bell.png --form-string 'caption={REAL_21478}' -o send.json"),
    ("the telegram skill's --form-string \"caption=$(cat file)\"",
     f'curl -s -X POST "{API}/sendPhoto" -F "chat_id=$CID" -F "photo=@/p.png" --form-string "caption=$(cat /tmp/caption.txt)"'),
    ("--form-string text= on sendMessage", f"curl -s \"{API}/sendMessage\" -F chat_id=1 --form-string 'text=a; b'"),
    ("quoted -F \"caption=<cap.txt\" reads the file verbatim", f'curl -s "{API}/sendPhoto" -F photo=@a.png -F "caption=<cap.txt"'),
    ("-F caption=\"<cap.txt\" (quote after the =)", f'curl -s "{API}/sendPhoto" -F photo=@a.png -F caption="<cap.txt"'),
    ("-F caption=\\<cap.txt (escaped <)", f'curl -s "{API}/sendPhoto" -F photo=@a.png -F caption=\\<cap.txt'),
    ("-F \"text=<$MSG_FILE\"", f'curl -s "{API}/sendMessage" -F chat_id=1 -F "text=<$MSG_FILE"'),
    ("file fields on -F: photo, document, video, audio, thumbnail, media",
     f'curl -s "{API}/sendMediaGroup" -F chat_id=1 -F photo=@x.png -F document=@a.pdf -F video=@v.mp4 '
     f'-F audio=@a.mp3 -F thumbnail=@t.jpg -F media=@m.json'),
    ("chat_id, parse_mode and reply_markup JSON holding \"text\" on -F",
     f"curl -s \"{API}/sendPhoto\" -F chat_id=1 -F parse_mode=HTML -F photo=@x.png "
     f"-F 'reply_markup={{\"inline_keyboard\":[[{{\"text\":\"Open; now\",\"url\":\"https://x\"}}]]}}'"),
    ("caption_entities and show_caption_above_media are not text fields",
     f"curl -s \"{API}/sendPhoto\" -F photo=@x.png -F 'caption_entities=[]' -F show_caption_above_media=true "
     f"--form-string 'caption=hi'"),
    ("--data-urlencode caption@file", f'curl -s "{API}/sendPhoto" -d chat_id=1 --data-urlencode "caption@/tmp/caption.txt"'),
    ("-F text= to a non-Telegram endpoint", 'curl -s -F "text=a; b" https://hooks.example.com/upload'),
    ("grep -F for the bad shape in the bridge source",
     'grep -F "caption=" ~/dev/claude-telegram-bridge/bridge.mjs | grep -n "api.telegram.org"'),
    ("git commit message quoting the bad shape",
     "cd ~/.claude && git commit -m \"$(cat <<'EOF'\nhooks: block curl -F \"caption=a; b\" to api.telegram.org/bot$TOK/sendPhoto\n\n"
     "Co-Authored-By: Claude <noreply@anthropic.com>\nEOF\n)\""),
    ("echo prose quoting the bad shape", f'echo \'never: curl -F "caption=a; b" {API}/sendPhoto\''),
    ("brief heredoc into a .md file", f"cat > /tmp/brief.md <<'EOF'\nBLOCK curl -F \"caption=a; b\" \"{API}/sendPhoto\"\nEOF"),
    ("ls -F next to a Telegram call", f'ls -F /tmp && curl -s "{API}/getMe"'),
]


print("blocked")
for label, cmd in BLOCKED:
    check(label, bash(cmd), BLOCK)

print("\nallowed")
for label, cmd in ALLOWED:
    check(label, bash(cmd), ALLOW)

print("\n-F trap: blocked")
for label, cmd in FORM_BLOCKED:
    check(label, bash(cmd), BLOCK)

print("\n-F trap: allowed")
for label, cmd in FORM_ALLOWED:
    check(label, bash(cmd), ALLOW)

print("\nfail open and scope")
for label, payload in (
    ("a Write call is not this hook's business",
     {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.mjs",
                                           "content": "fetch('https://api.telegram.org/bot'+t+'/editMessageText')"}}),
    ("missing tool_input", {"tool_name": "Bash"}),
    ("non-string command", {"tool_name": "Bash", "tool_input": {"command": ["curl", "editMessageText"]}}),
    ("empty payload", {}),
    ("malformed stdin", "not json {{ editMessageText"),
):
    check(label, payload, ALLOW)

print("\nmessage hygiene")
rc, err = run(bash(BLOCKED[0][1]))
rc2, err2 = run(bash(f'TG_EDIT_OK=1 curl -s "{API}/editMessageText" -d message_id=5'))
_, err3 = run(bash(f'curl -s "{API}/editMessageText" -d message_id=5'))
example = next((l.strip() for l in err3.splitlines() if l.strip().startswith("TG_EDIT_OK=1 curl")), None)
for label, ok in (
    ("names the method it matched", rc == 2 and "editMessageCaption" in err),
    ("says Telegram has no read-by-id method", "no read-by-id method" in err),
    ("says the proof is ok:true and the message_id of the send response",
     '"ok":true' in err and "message_id" in err),
    ("says never edit a message to test that it exists", "Never edit a message to test that it exists" in err),
    ("documents the TG_EDIT_OK=1 override with a reason comment", "TG_EDIT_OK=1" in err and "comment" in err),
    ("override without a reason says so", rc2 == 2 and "no comment giving the reason" in err2),
    ("no em or en dashes in the message", rc == 2 and "\u2014" not in err and "\u2013" not in err),
    ("the override example printed in the message is itself allowed",
     example is not None and run(bash(example))[0] == 0),
):
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")

print("\n-F trap: message hygiene")
rc, err = run(bash(FORM_BLOCKED[0][1]))
_, err_redirect = run(bash(f'curl -s "{API}/sendPhoto" -F caption=<cap.txt'))
_, err_both = run(bash(f'curl -s "{API}/editMessageCaption" -F message_id=1 -F "caption=a; b"'))
_, err_token = run(bash(f'curl -s -F "text=a" "https://x/bot{FAKE_TOKEN}/sendMessage"'))
fixes = [l.strip() for l in err.splitlines() if l.strip().startswith(("--form-string 'caption=", '-F "caption=<'))]
fixes = [f.split("    ")[0] for f in fixes]
for label, ok in (
    ("blocks and quotes the offending field", rc == 2 and '-F "caption=PR #166 merged' in err),
    ("explains that ; starts a field parameter and the rest is dropped",
     'reads a ";" inside a value' in err and "silently drops everything after it" in err),
    ("cites message 21478", "21478" in err),
    ("names both fixes: --form-string and a quoted -F \"caption=<file\"", len(fixes) == 2),
    ("both fixes printed in the message are themselves allowed",
     len(fixes) == 2 and all(run(bash(f'curl -s "{API}/sendPhoto" -F photo=@a.png {f}'))[0] == 0 for f in fixes)),
    ("warns that double quotes lose $ to the shell", "double quotes" in err and "$5" in err),
    ("says an unquoted <file is a shell redirect, for that shape", "shell redirect" in err_redirect),
    ("an edit call with a -F caption gets both messages",
     "Bot API edit call" in err_both and "curl -F / --form on a Telegram text field" in err_both),
    ("a bot token literal is not echoed back", FAKE_TOKEN not in err_token and "<token>" in err_token),
    ("no em or en dashes in the message", rc == 2 and "—" not in err and "–" not in err),
):
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")

print("\nspeed (a hook on every Bash call)")
big_prose = "git commit -m \"" + ("editMessageText on api.telegram.org " * 30000) + "\""
big_code = "node -e \"" + ("x(1);" * 200000) + "fetch('https://api.telegram.org/bot'+t+'/editMessageText')\""
plain = "ls -la /tmp && " + ("echo hi; " * 50000)
big_form = f'curl -s "{API}/sendMediaGroup" ' + ("-F photo=@x.png " * 60000) + '-F "caption=a; b"'
for label, cmd, want in (
    ("1 MB commit message mentioning both: allowed, under 4 s", big_prose, ALLOW),
    ("1 MB inline node code with an edit call: blocked, under 4 s", big_code, BLOCK),
    ("400 KB ordinary command: allowed, under 4 s", plain, ALLOW),
    ("1 MB curl with 60000 -F file fields and one -F caption: blocked, under 4 s", big_form, BLOCK),
):
    t0 = time.time()
    rc, _ = run(bash(cmd))
    dt = time.time() - t0
    if rc == want and dt < 4.0:
        passed += 1
        print(f"  PASS  {label} ({dt:.2f}s, exit {rc})")
    else:
        failed += 1
        print(f"  FAIL  {label}: {dt:.2f}s, exit {rc}, wanted {want}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
