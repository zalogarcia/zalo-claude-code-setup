#!/usr/bin/env python3
"""Suite for background-lane-guard.py.

Run: python3 ~/.claude/hooks/background-lane-guard.test.py
Changing the guard means re-running this — same rule as tmux-peer-guard.

Exit 0 = all pass.
"""

import json
import os
import subprocess
import sys

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "background-lane-guard.py")

ALLOW, BLOCK = 0, 2


def run(payload, tmux=None):
    env = dict(os.environ)
    env.pop("TMUX", None)
    if tmux is not None:
        env["TMUX"] = tmux
    p = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps(payload) if isinstance(payload, dict) else payload,
        capture_output=True,
        text=True,
        env=env,
    )
    return p.returncode, p.stderr


def bash(command="echo hi", background=False):
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command, "run_in_background": background},
    }


CASES = []


def case(name, want, payload, tmux=None, expect_stderr=None):
    CASES.append((name, want, payload, tmux, expect_stderr))


# -- the core rule ------------------------------------------------------------
case("headless + background => BLOCK", BLOCK, bash("sleep 60", True), None, "background-lane-guard")
case("tmux + background => allow", ALLOW, bash("sleep 60", True), "/tmp/tmux-501/default,123,0")
case("headless + foreground => allow", ALLOW, bash("sleep 60", False))
case("tmux + foreground => allow", ALLOW, bash("sleep 60", False), "/tmp/tmux-501/default,123,0")

# -- the real-world regression this exists for --------------------------------
case(
    "the 2026-07-28 deploy poller => BLOCK",
    BLOCK,
    bash("until [ \"$(curl -s https://x | grep -o y)\" != 'z' ]; do sleep 15; done", True),
)

# -- durable lanes are exempt -------------------------------------------------
case(
    "bg.mjs handoff backgrounded => allow",
    ALLOW,
    bash('node ~/dev/claude-telegram-bridge/bg.mjs "do a thing"', True),
)
case(
    "schedule.mjs backgrounded => allow",
    ALLOW,
    bash('node ~/dev/claude-telegram-bridge/schedule.mjs add in 10m "ping" --run', True),
)

# -- scope: only Bash ---------------------------------------------------------
case(
    "non-Bash tool with run_in_background => allow",
    ALLOW,
    {"tool_name": "Agent", "tool_input": {"run_in_background": True}},
)
case("Bash with no tool_input => allow", ALLOW, {"tool_name": "Bash"})

# -- fail-open on junk --------------------------------------------------------
case("malformed json => allow", ALLOW, "not json at all")
case("empty payload => allow", ALLOW, {})
case(
    "run_in_background explicitly false => allow",
    ALLOW,
    {"tool_name": "Bash", "tool_input": {"command": "x", "run_in_background": False}},
)

# -- the block message must name the alternatives -----------------------------
case("block message names bg.mjs", BLOCK, bash("sleep 1", True), None, "bg.mjs")
case("block message names schedule.mjs", BLOCK, bash("sleep 1", True), None, "schedule.mjs")
case("block message names FOREGROUND", BLOCK, bash("sleep 1", True), None, "FOREGROUND")


def main():
    failed = 0
    for name, want, payload, tmux, expect_stderr in CASES:
        code, err = run(payload, tmux)
        ok = code == want
        if ok and expect_stderr:
            ok = expect_stderr in err
        if not ok:
            failed += 1
            print(f"FAIL  {name}: exit {code} (wanted {want})"
                  + (f", stderr missing {expect_stderr!r}" if expect_stderr else ""))
        else:
            print(f"ok    {name}")
    total = len(CASES)
    print()
    if failed:
        print(f"{total - failed}/{total} passed, {failed} FAILED")
        return 1
    print(f"{total}/{total} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
