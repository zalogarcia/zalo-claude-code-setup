#!/usr/bin/env python3
"""Tests for telegram-senddocument-guard.py. Run: python3 telegram-senddocument-guard.test.py"""

import json
import subprocess
import sys

HOOK = "/Users/zalo/.claude/hooks/telegram-senddocument-guard.py"

BLOCK, ALLOW = 2, 0

CASES = [
    # (name, payload, expected_exit)
    (
        "curl sendVideo is blocked",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -s -X POST "https://api.telegram.org/bot123:ABC/sendVideo" -F "chat_id=1" -F "video=@/tmp/a.mp4"'}},
        BLOCK,
    ),
    (
        "sendDocument is allowed",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -s -X POST "https://api.telegram.org/bot123:ABC/sendDocument" -F "document=@/tmp/a.mp4"'}},
        ALLOW,
    ),
    (
        "sendPhoto is allowed",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -X POST https://api.telegram.org/bot123:ABC/sendPhoto -F photo=@/tmp/a.png'}},
        ALLOW,
    ),
    (
        "sendMessage is allowed",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -X POST https://api.telegram.org/bot123:ABC/sendMessage -d text=hi'}},
        ALLOW,
    ),
    (
        "sendAudio is allowed",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -X POST https://api.telegram.org/bot1/sendAudio -F audio=@/tmp/a.mp3'}},
        ALLOW,
    ),
    (
        "python subprocess arg-list form is blocked",
        {"tool_name": "Bash", "tool_input": {"command": 'python3 -c \'subprocess.run(["curl","-X","POST","https://api.telegram.org/bot1/sendVideo"])\''}},
        BLOCK,
    ),
    (
        "running a script that posts sendVideo inline is blocked",
        {"tool_name": "Bash", "tool_input": {"command": "curl -F video=@x.mp4 'https://api.telegram.org/bot9/sendVideo'"}},
        BLOCK,
    ),
    (
        "non-telegram sendVideo (unrelated code) is allowed",
        {"tool_name": "Bash", "tool_input": {"command": "grep -rn 'sendVideo' src/bot.ts"}},
        ALLOW,
    ),
    (
        "telegram host without sendVideo is allowed",
        {"tool_name": "Bash", "tool_input": {"command": 'curl "https://api.telegram.org/bot1/getUpdates"'}},
        ALLOW,
    ),
    (
        "non-Bash tool is ignored",
        {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x", "content": "sendVideo api.telegram.org"}},
        ALLOW,
    ),
    (
        "missing tool_input fails open",
        {"tool_name": "Bash"},
        ALLOW,
    ),
    (
        "non-string command fails open",
        {"tool_name": "Bash", "tool_input": {"command": ["curl", "sendVideo"]}},
        ALLOW,
    ),
    (
        "empty payload fails open",
        {},
        ALLOW,
    ),
    (
        "lowercase sendvideo path variant is blocked",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -X POST https://api.telegram.org/bot1/sendvideo -F video=@a.mp4'}},
        BLOCK,
    ),
]


def run(payload):
    p = subprocess.run(
        ["python3", HOOK], input=json.dumps(payload), capture_output=True, text=True
    )
    return p.returncode


def main():
    passed = failed = 0
    for name, payload, expected in CASES:
        got = run(payload)
        if got == expected:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {name} — expected exit {expected}, got {got}")

    # Malformed stdin must not wedge the session.
    p = subprocess.run(["python3", HOOK], input="not json{{", capture_output=True, text=True)
    if p.returncode == 0:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: malformed stdin — expected exit 0, got {p.returncode}")

    total = passed + failed
    print(f"\n{passed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
