#!/usr/bin/env python3
"""Tests for dispatch-claim-guard.py. Run: python3 dispatch-claim-guard.test.py"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "guard", Path(__file__).parent / "dispatch-claim-guard.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")


def user(text):
    return {"type": "user", "message": {"content": text}}


def tool_result():
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "ok"}]},
    }


def assistant_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def assistant_bash(cmd):
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}
            ]
        },
    }


def assistant_tool(name):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": {}}]},
    }


DISPATCH = "cd ~/dev/claude-telegram-bridge && node bg.mjs --file /tmp/brief-x.md"

# --- the incident this hook exists for -------------------------------------
check(
    "incident: claim with no dispatch fires",
    bool(
        guard.evaluate(
            [user("look into it"), assistant_text("I have dispatched a read only investigation to answer the open parts.")]
        )
    ),
    True,
)
check(
    "same claim WITH a real dispatch is clean",
    guard.evaluate(
        [
            user("look into it"),
            assistant_bash(DISPATCH),
            tool_result(),
            assistant_text("I have dispatched a read only investigation to answer the open parts."),
        ]
    ),
    "",
)

# --- claim shapes that must fire -------------------------------------------
for phrase in (
    "I've dispatched a worker to handle the migration.",
    "Dispatched two workers for the audit.",
    "I have handed it off to a background worker.",
    "Handed this off to a worker, will report back.",
    "I've put an agent on the edge case matrix.",
    "It is now queued for the background lane.",
    "Both briefs are queued and running.",
    "I've just sent a worker to trace the bug.",
):
    check(
        f"claims: {phrase[:38]!r}",
        bool(guard.evaluate([user("go"), assistant_text(phrase)])),
        True,
    )

# --- shapes that must NOT fire ---------------------------------------------
for phrase in (
    "I'll dispatch a worker once the current one lands.",
    "I am going to hand this off to a background worker.",
    "Want me to dispatch a worker for this?",
    "The worker I dispatched earlier just reported back.",
    "That job was already dispatched this morning.",
    "I dispatched a worker previously and it is still going.",
    "Next I'll hand this off.",
    "The plan is to dispatch two workers.",
    "No dispatch needed, this is a one line fix.",
):
    check(
        f"no-fire: {phrase[:38]!r}",
        guard.evaluate([user("go"), assistant_text(phrase)]),
        "",
    )

# --- dispatch detection ----------------------------------------------------
check(
    "bg.mjs ps alone is NOT a dispatch",
    bool(
        guard.evaluate(
            [
                user("go"),
                assistant_bash("node bg.mjs ps"),
                tool_result(),
                assistant_text("I have dispatched a worker."),
            ]
        )
    ),
    True,
)
check(
    "bg.mjs steer alone is NOT a dispatch",
    bool(
        guard.evaluate(
            [
                user("go"),
                assistant_bash("node bg.mjs steer bg-123 --file /tmp/s.md"),
                tool_result(),
                assistant_text("I have dispatched a worker."),
            ]
        )
    ),
    True,
)
check(
    "chained dispatch + ps still counts as a dispatch",
    guard.evaluate(
        [
            user("go"),
            assistant_bash(f"{DISPATCH} && node bg.mjs ps"),
            tool_result(),
            assistant_text("I have dispatched a worker."),
        ]
    ),
    "",
)
check(
    "Agent tool call counts as a dispatch",
    guard.evaluate(
        [
            user("go"),
            assistant_tool("Agent"),
            tool_result(),
            assistant_text("I've handed it off to a subagent."),
        ]
    ),
    "",
)
check(
    "Workflow counts as a dispatch",
    guard.evaluate(
        [user("go"), assistant_tool("Workflow"), tool_result(), assistant_text("Dispatched a worker for it.")]
    ),
    "",
)

# --- turn boundary ---------------------------------------------------------
check(
    "a dispatch in a PREVIOUS turn does not excuse this turn's claim",
    bool(
        guard.evaluate(
            [
                user("first task"),
                assistant_bash(DISPATCH),
                tool_result(),
                assistant_text("Sent."),
                user("second task"),
                assistant_text("I have dispatched a worker for that too."),
            ]
        )
    ),
    True,
)
check(
    "tool_result envelopes do not split the turn",
    guard.evaluate(
        [
            user("go"),
            assistant_bash(DISPATCH),
            tool_result(),
            assistant_text("checking"),
            assistant_bash("node bg.mjs ps"),
            tool_result(),
            assistant_text("I have dispatched a worker and verified it."),
        ]
    ),
    "",
)

# --- robustness ------------------------------------------------------------
check("empty transcript", guard.evaluate([]), "")
check("no assistant text", guard.evaluate([user("go")]), "")
check("string-content assistant", guard.evaluate([user("go"), {"type": "assistant", "message": {"content": "I have dispatched a worker."}}]) != "", True)
check("malformed entry is survivable", guard.evaluate([user("go"), {"type": "assistant"}]), "")
check(
    "malformed bash input is survivable",
    bool(
        guard.evaluate(
            [
                user("go"),
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": None}]}},
                assistant_text("I have dispatched a worker."),
            ]
        )
    ),
    True,
)
check(
    "later empty text falls back to the last non-empty assistant text",
    bool(guard.evaluate([user("go"), assistant_text("I have dispatched a worker."), assistant_text("   ")])),
    True,
)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
