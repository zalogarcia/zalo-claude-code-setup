#!/usr/bin/env python3
"""Tests for tiktok-draft-nudge.py. Run: python3 tiktok-draft-nudge.test.py"""

import json
import subprocess
import sys

HOOK = "/Users/zalo/.claude/hooks/tiktok-draft-nudge.py"

FIRES, QUIET = True, False


def run(payload):
    p = subprocess.run(
        ["python3", HOOK], input=json.dumps(payload), capture_output=True, text=True
    )
    assert p.returncode == 0, f"hook must always exit 0, got {p.returncode}"
    fired = "TIKTOK DRAFT PUSHED" in p.stdout
    return fired


CASES = [
    (
        "publish call carrying tiktokDraft fires",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -X POST http://localhost:1974/api/publish -d \'{"tiktokDraft": true}\''}},
        FIRES,
    ),
    (
        "TikTok's own 'Saved as draft' confirmation fires",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "curl -s http://localhost:1974/api/publish/status?id=sp_x"},
            "tool_response": {"stdout": '{"status":"processed","results":[{"success":true,"details":{"status":"Saved as draft"}}]}'},
        },
        FIRES,
    ),
    (
        "inbox-notification wording fires",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 /tmp/poll.py"},
            "tool_response": {"stdout": "Content saved as draft in TikTok. Check your TikTok inbox notifications to continue editing and publish."},
        },
        FIRES,
    ),
    (
        "is_draft in a publish payload fires",
        {"tool_name": "Bash", "tool_input": {"command": "curl -X POST localhost:1974/api/publish -d '{\"platformConfig\":{\"tiktok\":{\"is_draft\":true}}}'"}},
        FIRES,
    ),
    (
        "ordinary publish WITHOUT a tiktok draft stays quiet",
        {"tool_name": "Bash", "tool_input": {"command": 'curl -X POST http://localhost:1974/api/publish -d \'{"platforms":["instagram"]}\''}},
        QUIET,
    ),
    (
        "unrelated bash stays quiet",
        {"tool_name": "Bash", "tool_input": {"command": "ls -la ~/Documents"}},
        QUIET,
    ),
    (
        "reading about drafts without pushing stays quiet",
        {"tool_name": "Bash", "tool_input": {"command": "grep -rn 'is_draft' ~/dev/zalo-os/src"}},
        QUIET,
    ),
    (
        "non-Bash tool is ignored",
        {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x", "content": "api/publish tiktokDraft"}},
        QUIET,
    ),
    (
        "missing tool_input fails open quietly",
        {"tool_name": "Bash"},
        QUIET,
    ),
    (
        "non-string command fails open quietly",
        {"tool_name": "Bash", "tool_input": {"command": ["curl", "tiktokDraft"]}},
        QUIET,
    ),
    (
        "empty payload stays quiet",
        {},
        QUIET,
    ),
    (
        "string tool_response is handled",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "curl -s http://localhost:1974/api/publish/status?id=abc"},
            "tool_response": "Saved as draft in TikTok",
        },
        FIRES,
    ),
    # --- regression: reading a file that DOCUMENTS the rail is not a push.
    # 2026-08-02: `grep tiktokDraft pipeline.md` echoed the spec's verbatim copy
    # of TikTok's "Content saved as draft..." confirmation, and the hook nudged
    # Zalo about a draft nobody had pushed, mid-build.
    (
        "grep of a spec file quoting the confirmation does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {"command": 'grep -n "tiktokDraft" pipeline.md'},
            "tool_response": {
                "stdout": 'tiktokDraft: true ... "Content saved as draft. Check your TikTok inbox notifications."',
                "stderr": "",
            },
        },
        QUIET,
    ),
    (
        "cat of the rail research doc does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "cat tiktok-rail-research.md"},
            "tool_response": {"stdout": "route default is is_draft / tiktokDraft", "stderr": ""},
        },
        QUIET,
    ),
    (
        "editing a publish route file does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "sed -n '1,40p' src/app/api/publish/route.ts"},
            "tool_response": {"stdout": "tiktokDraft ?? true", "stderr": ""},
        },
        QUIET,
    ),
    # 2026-08-02, second false alarm: a compound read whose glue token was `echo`
    # was not recognised as read-only, so the hook fired on grep output that
    # merely quoted TikTok's confirmation wording out of pipeline.md.
    (
        "compound read with echo glue does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'ls -t /tmp/x.py && echo "--- table ---" && grep -n -A6 "STAGGER LAW" pipeline.md | head -20'
            },
            "tool_response": {
                "stdout": 'tiktokDraft: true ... TikTok returns "Content saved as draft. Check your TikTok inbox notifications"',
                "stderr": "",
            },
        },
        QUIET,
    ),
    (
        "read piped through sort/uniq/tr does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "cat rail.md | tr -s ' ' | sort | uniq | head"},
            "tool_response": {"stdout": "saved as draft", "stderr": ""},
        },
        QUIET,
    ),
    # 2026-08-02, third false alarm: WRITING a scheduler script (heredoc) whose
    # source contains tiktokDraft + api/publish, then DRY-RUNNING it. Command
    # text is indistinguishable from a real push; only the output differs.
    (
        "writing a scheduler script does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'cat > tools/schedule_day.py <<\'PY\'\np["tiktokDraft"] = True\n"http://localhost:1974/api/publish"\nPY\nchmod +x tools/schedule_day.py'
            },
            "tool_response": {"stdout": "", "stderr": ""},
        },
        QUIET,
    ),
    (
        "DRY RUN of the scheduler does NOT fire (no receipt in output)",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 tools/schedule_day.py batch-03 2026-08-08 --reels-only"},
            "tool_response": {
                "stdout": "DRY RUN — 2026-08-08\n  tiktok R2 @09:00  2026-08-08T09:00:00-04:00  cap=498ch\n\n25 ok, 0 failed",
                "stderr": "",
            },
        },
        QUIET,
    ),
    (
        "REAL scheduler run WITH post ids fires",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 tools/schedule_day.py batch-03 2026-08-08 --go"},
            "tool_response": {
                "stdout": "SCHEDULING — 2026-08-08\n  OK   tiktok R2 @09:00  id=sp_0Z7v0IfW14hz13W2DZ6Qc\n",
                "stderr": "",
            },
        },
        FIRES,
    ),
    # 2026-08-16, false alarms 4 and 5 — both during a READ-ONLY memory sync,
    # one of them on the very grep used to document this hook. The whole-command
    # network test could not tell a reader's search PATTERN from a call.
    (
        "grep whose pattern contains a network word does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {"command": 'grep -n "curl" ~/.claude/hooks/tiktok-draft-nudge.py'},
            "tool_response": {
                "stdout": 'NETWORK_MARKERS = ("curl", ...)  # "check your tiktok inbox"',
                "stderr": "",
            },
        },
        QUIET,
    ),
    (
        "python3 -c reading a transcript does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'python3 -c "[print(l) for l in open(t)]" session.jsonl | grep -a tiktok'
            },
            "tool_response": {
                "stdout": '{"id":"msg_01abc","text":"pushed the tiktok draft — Content saved as draft. Check your TikTok inbox notifications."}',
                "stderr": "",
            },
        },
        QUIET,
    ),
    (
        "python3 -c whose inline code contains a semicolon does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'python3 -c "import json,sys; [print(l) for l in open(t)]" session.jsonl | grep -a tiktok'
            },
            "tool_response": {
                "stdout": '{"id":"msg_01abc","text":"Content saved as draft. Check your TikTok inbox notifications."}',
                "stderr": "",
            },
        },
        QUIET,
    ),
    # 2026-08-17, false alarm 6: a heredoc-to-stdin transcript scan. The body's
    # prose split on its own `;`/`|` into fake segments. Found by pulling the
    # triggering command out of the firing session's transcript.
    (
        "python3 heredoc reading transcripts does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "cd ~/.claude/projects && python3 - <<'PY'\nimport json, glob\nfor p in glob.glob('*/*.jsonl'):\n    for line in open(p):\n        r = json.loads(line); print(r.get('id'))\nPY"
            },
            "tool_response": {
                "stdout": 'pushed the tiktok draft: Content saved as draft. Check your TikTok inbox notifications. {"id":"msg_01abc"}',
                "stderr": "",
            },
        },
        QUIET,
    ),
    (
        "bare python3 heredoc (no dash) does NOT fire",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 <<'PY'\nprint(open('rail.md').read())\nPY"},
            "tool_response": {"stdout": "saved as draft; check your tiktok inbox", "stderr": ""},
        },
        QUIET,
    ),
    (
        "heredoc whose body DOES hit the network still fires",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 - <<'PY'\nimport requests\nrequests.post(url, json={'tiktokDraft': True})\nPY"
            },
            "tool_response": {"stdout": "Saved as draft", "stderr": ""},
        },
        FIRES,
    ),
    (
        "python3 -c that DOES hit the network still fires",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": 'python3 -c "import requests; requests.post(u, json={\'tiktokDraft\': True})"'
            },
            "tool_response": {"stdout": "Saved as draft", "stderr": ""},
        },
        FIRES,
    ),
    (
        "real curl push with the draft flag still fires",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "curl -X POST http://localhost:1974/api/publish -d '{\"tiktokDraft\":true,\"draft\":false}'"
            },
            "tool_response": {"stdout": '{"id":"abc"}', "stderr": ""},
        },
        FIRES,
    ),
    # --- P13 regression (audit 2026-08-28): meta-analysis is not a push ---
    (
        "transcript scan hunting past firings stays quiet (the P13 shape)",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": "cd ~/.claude/projects && python3 - <<'PY'\nimport json, glob\nfor p in glob.glob('*/*.jsonl'):\n    pass\nPY"
            },
            "tool_response": {
                "stdout": "TRIGGERING COMMAND:\nContent saved as draft. Check your TikTok inbox notifications.\n"
            },
        },
        QUIET,
    ),
    (
        "opaque script scanning transcripts stays quiet even with confirmation wording",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 /tmp/scan.py ~/.claude/projects/abc.jsonl"},
            "tool_response": {"stdout": "match: Content saved as draft. Check your TikTok inbox notifications."},
        },
        QUIET,
    ),
    (
        "reading bg-results for an old tiktok job stays quiet",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 -m json.tool < ~/dev/claude-telegram-bridge/bg-results.jsonl"},
            "tool_response": {"stdout": '{"id":"x","result":"pushed the tiktok draft, saved as draft"}'},
        },
        QUIET,
    ),
    (
        "editing the hook's own source stays quiet",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "ruff check /Users/zalo/.claude/hooks/tiktok-draft-nudge.py"},
            "tool_response": {"stdout": "saved as draft"},
        },
        QUIET,
    ),
    (
        "bare JSON id + the word tiktok is not a receipt",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 /tmp/list_assets.py --platform tiktok"},
            "tool_response": {"stdout": '[{"id":"asset_1"},{"id":"asset_2"}]'},
        },
        QUIET,
    ),
    (
        "wrapper-script poller with a real receipt still fires",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python3 /tmp/scheduler.py --go"},
            "tool_response": {"stdout": '{"id":"sp_9fA2kd81","platform":"tiktok","status":"Saved as draft"}'},
        },
        FIRES,
    ),
]


def main():
    passed = failed = 0
    for name, payload, expected in CASES:
        try:
            got = run(payload)
        except AssertionError as e:
            print(f"FAIL: {name} — {e}")
            failed += 1
            continue
        if got == expected:
            passed += 1
        else:
            failed += 1
            print(f"FAIL: {name} — expected fired={expected}, got fired={got}")

    p = subprocess.run(["python3", HOOK], input="not json{{", capture_output=True, text=True)
    if p.returncode == 0 and "TIKTOK DRAFT PUSHED" not in p.stdout:
        passed += 1
    else:
        failed += 1
        print("FAIL: malformed stdin must exit 0 and stay quiet")

    total = passed + failed
    print(f"\n{passed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
