#!/usr/bin/env python3
"""Behaviour suite for shell-mechanics-guard.

Run: python3 ~/.claude/hooks/shell-mechanics-guard.test.py
Must be green before the hook is wired into ~/.claude/settings.json — this is a
PreToolUse Bash hook, and a broken one blocks every Bash call on the machine.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.path.expanduser("~/.claude/hooks/shell-mechanics-guard.py")
WARN, QUIET = True, False


def run(command, state_dir, session="s1", payload=None, raw=None):
    if raw is None:
        pl = payload if payload is not None else {
            "session_id": session,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": "/tmp",
        }
        raw = json.dumps(pl)
    p = subprocess.run(
        ["python3", HOOK],
        input=raw,
        capture_output=True,
        text=True,
        env=dict(os.environ, SHELL_MECH_STATE_DIR=state_dir),
    )
    assert p.returncode == 0, f"hook must always exit 0, got {p.returncode}: {p.stderr}"
    if not p.stdout.strip():
        return None
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


# (label, command, expect, marker-substring or None)
CASES = [
    # --- WARN: lost exit code -------------------------------------------------
    ("PIPESTATUS after an && chain",
     'npm run typecheck && npm run build; echo "EXIT=${PIPESTATUS[0]}"', WARN, "PIPESTATUS"),
    ("$? read after | tail",
     "npm run build 2>&1 | tail -40; echo EXIT=$?", WARN, "PIPESTATUS"),
    ("$? read after | grep in an && chain",
     "cargo test | grep -c FAILED && echo done; EXIT=$?", WARN, "PIPESTATUS"),
    # --- WARN: relative cd ----------------------------------------------------
    ("leading relative cd",
     "cd delta-agents && npm test", WARN, "relative"),
    ("leading cd ..",
     "cd ../packages && ls", WARN, "relative"),
    # --- QUIET: correct shapes ------------------------------------------------
    ("canonical capture shape",
     "npm run build > /tmp/b.log 2>&1; echo EXIT=$?; tail -40 /tmp/b.log", QUIET, None),
    ("PIPESTATUS with no && before it",
     "npm run build 2>&1 | tail -5; echo ${PIPESTATUS[0]}", QUIET, None),
    ("absolute cd",
     "cd /Users/zalo/dev/delta-agents && npm test", QUIET, None),
    ("tilde cd",
     "cd ~/dev/zalo-os && ls", QUIET, None),
    ("variable cd",
     "cd $HOME/dev && ls", QUIET, None),
    ("command substitution cd",
     'cd "$(git rev-parse --show-toplevel)" && ls', QUIET, None),
    ("plain command",
     "ls -la /tmp", QUIET, None),
    ("$? straight after a non-piped command",
     "npm run build; echo EXIT=$?", QUIET, None),
    ("git -C absolute (the recommended alternative)",
     "git -C /Users/zalo/dev/zalo-os status", QUIET, None),
    # --- EXEMPTIONS -----------------------------------------------------------
    ("pipefail makes $?-after-pipe meaningful",
     "set -o pipefail; npm run build 2>&1 | tail -40; echo EXIT=$?", QUIET, None),
    ("$? inside a quoted string is not shell mechanics",
     "grep -n 'echo EXIT=$?' ~/.claude/QUIRKS.md", QUIET, None),
    ("a pipe inside a quoted pattern is not a pipeline",
     'rg "a \\| tail" /tmp/x.txt; echo hi', QUIET, None),
    ("cd - (return to previous dir) is not a relative path guess",
     "cd -", QUIET, None),
]


def main():
    passed = failed = 0
    dirs = []

    for label, cmd, expect, marker in CASES:
        d = tempfile.mkdtemp(prefix="shellmech-")
        dirs.append(d)
        try:
            got = run(cmd, d)
        except AssertionError as e:
            print(f"FAIL | {label} — {e}")
            failed += 1
            continue
        ok = (got is not None) == expect
        if ok and expect and marker:
            ok = marker in got
        if ok:
            passed += 1
            print(f"PASS | {label}")
        else:
            failed += 1
            print(f"FAIL | {label} — expected warn={expect}, got {got!r}")

    # once per class per session
    d = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d)
    first = run("cd delta-agents && npm test", d)
    second = run("cd other-repo && npm test", d)
    third = run("npm run build 2>&1 | tail -5; echo EXIT=$?", d)
    for label, cond in (
        ("first relative cd warns", first is not None),
        ("second relative cd is silent (once per session)", second is None),
        ("a DIFFERENT class still warns in the same session", third is not None),
    ):
        (globals(), None)
        if cond:
            passed += 1
            print(f"PASS | {label}")
        else:
            failed += 1
            print(f"FAIL | {label}")

    # a different session gets its own budget
    d2 = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d2)
    run("cd delta-agents && npm test", d2, session="s1")
    other = run("cd delta-agents && npm test", d2, session="s2")
    if other is not None:
        passed += 1
        print("PASS | a different session warns independently")
    else:
        failed += 1
        print("FAIL | a different session warns independently")

    # --- MALFORMED input: must exit 0 and stay silent -------------------------
    d3 = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d3)
    malformed = [
        ("unparseable JSON", None, '{"broken":'),
        ("empty stdin", None, ""),
        ("missing tool_input", {"tool_name": "Bash", "session_id": "s"}, None),
        ("tool_input is null", {"tool_name": "Bash", "tool_input": None}, None),
        ("command is a dict", {"tool_name": "Bash", "tool_input": {"command": {"a": 1}}}, None),
        ("command is a list", {"tool_name": "Bash", "tool_input": {"command": ["cd x"]}}, None),
        ("no tool_name", {"tool_input": {"command": "cd x && ls"}}, None),
        ("wrong tool", {"tool_name": "Read", "tool_input": {"file_path": "/x"}}, None),
        ("top-level list", None, "[1,2,3]"),
        ("session_id is a dict", {"session_id": {"a": 1}, "tool_name": "Bash",
                                  "tool_input": {"command": "cd rel && ls"}}, None),
    ]
    for label, pl, raw in malformed:
        try:
            got = run(None, d3, payload=pl, raw=raw)
        except AssertionError as e:
            print(f"FAIL | malformed: {label} — {e}")
            failed += 1
            continue
        # session_id-is-a-dict is a real command and MAY warn; it must not crash.
        if label == "session_id is a dict":
            passed += 1
            print(f"PASS | malformed: {label} (exit 0, no crash)")
        elif got is None:
            passed += 1
            print(f"PASS | malformed: {label}")
        else:
            failed += 1
            print(f"FAIL | malformed: {label} — expected silence, got {got!r}")

    # unwritable state dir must not crash or block
    try:
        got = run("cd rel && ls", "/proc/nonexistent-nope")
        passed += 1
        print("PASS | unwritable state dir still exits 0")
    except AssertionError as e:
        failed += 1
        print(f"FAIL | unwritable state dir — {e}")

    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)

    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
