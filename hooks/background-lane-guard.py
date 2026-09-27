#!/usr/bin/env python3
"""PreToolUse guard: work that cannot survive the end of a headless turn.

Wired on two matchers: `Bash`, and `Agent|Task` (plus a `SendMessage` entry).
Three rules live here, evaluated independently.

1. Bash (the original half, unchanged)
--------------------------------------
In a headless Claude Code run (the Telegram bridge lanes, cwd ~/dev, no
terminal) anything backgrounded dies when the turn that spawned it ends.
`nohup ... &`, `launchctl submit`, and the harness's own `run_in_background`
lane all fail the same way: the process is killed with the turn, the output
file stays 0 bytes, and NO completion notification is ever delivered.

That fact was already written in ~/dev/CLAUDE.md (it had cost three runs: a
49MB render discarded, a mux killed at 561KB) and was broken again on
2026-07-28: a poller was armed to watch a Vercel deploy, the turn ended, the
process died silently, and Zalo had to prompt "Check" because the promised
wake-up could never arrive. Prose did not hold under momentum. This does.

Blocks: Bash calls with `run_in_background: true` when `$TMUX` is unset.
Allows: everything inside tmux, foreground Bash of any kind, and Bash whose
command is itself a handoff to a durable lane (bg.mjs, schedule.mjs).

2. Agent/Task in a headless run (self-audit 2026-09-27, P2)
----------------------------------------------------------
The Agent tool runs a subagent in the BACKGROUND unless `run_in_background:
false` is passed, and a headless run kills that subagent when the turn ends
(memory `headless-subagents-die-on-turn-end.md`). Lane rule 1 in bg.mjs has
said so since 2026-08-31 and prose did not hold: 11 sessions of 80 in one
week launched async anyway and then polled for hours for a result that could
not arrive. Until this rule existed the hook returned 0 for every non-Bash
tool, so its `Agent|Task` wiring did nothing.

  headless = $TMUX unset AND ($LEASH_LANE non-empty OR
             $CLAUDE_CODE_ENTRYPOINT starts with "sdk")

When headless, an Agent/Task call is BLOCKED unless tool_input.run_in_background
is exactly JSON false. Omitted is the common failure shape; true, "false",
0 and null all block too. Never blocks in tmux, or in an interactive `cli`
run outside tmux.

`SendMessage` (resumes an existing agent) in a headless run: WARN only. A
resumed agent runs async and dies at turn end in this lane, so a re-verify is
a fresh foreground Agent with the prior verdict pasted.

3. Verifier needs the draft report on disk (self-audit 2026-09-27, P3)
----------------------------------------------------------------------
17 of 80 workers ended without their final report after a usage wall, 12 of
them during the verifier dispatch, the most token heavy step, which the brief
template placed between the work and its only record. The bridge exports
$BG_REPORT_DRAFT (the worker's draft report path) and $BG_RUN_STARTED_AT
(epoch ms). When $BG_REPORT_DRAFT is set, $TMUX is unset (a tmux server's
global environment can carry a dead worker's path into every pane), and
subagent_type is qa-agent, live-test or outcomes-grader, the dispatch is
BLOCKED unless that file exists,
is non-empty, and was modified during this run (1 s of slack; with no
parsable start time, exists and non-empty is enough). Skipped inside a
subagent (payload carries agent_id): the draft is the worker's own report and
a subagent cannot write it. Any metadata error other than "does not exist"
fails open.

When rules 2 and 3 both block one call, both reasons are printed, rule 3
first.

The durable lanes that DO survive a headless turn end
-----------------------------------------------------
1. `node ~/dev/claude-telegram-bridge/bg.mjs --file <brief>`: a separate
   worker session; its report is delivered back to you.
2. `node ~/dev/claude-telegram-bridge/schedule.mjs add in 10m "<prompt>" --run`:
   file based, survives daemon restarts; the durable way to poll.
Otherwise: run it in the FOREGROUND and wait for the result in turn.

Pure core: `decide(payload, env)` returns (exit_code, stderr_text,
stdout_text) and is imported by the replay harness. Exit 0 = allow (stdout may
carry a warning), exit 2 = block (stderr is shown to Claude).

Tests: python3 ~/.claude/hooks/background-lane-guard.test.py
"""

import json
import math
import os
import stat
import sys

# Commands that are themselves durable-lane handoffs: backgrounding these is
# pointless but harmless, and blocking them would be confusing. Substring match
# against the command text.
DURABLE_LANE_MARKERS = (
    "claude-telegram-bridge/bg.mjs",
    "claude-telegram-bridge/schedule.mjs",
)

AGENT_TOOLS = ("Agent", "Task")
VERIFIER_TYPES = ("qa-agent", "live-test", "outcomes-grader")
DRAFT_SLACK_S = 1.0
HANDOFF = "node ~/dev/claude-telegram-bridge/bg.mjs --file <brief>"

SEND_MESSAGE_WARNING = (
    "background-lane-guard (warn only): this is a headless lane. If the agent "
    "you are messaging has already finished, SendMessage RESUMES it, and a "
    "resumed agent runs async and dies at turn end in this lane; its answer "
    "never reaches you. For a re-verify, dispatch a fresh foreground Agent "
    "(run_in_background: false) with the prior verdict pasted into its "
    "prompt. Steering an agent that is still running is fine."
)


def is_headless(env):
    """$TMUX unset AND (a bridge lane OR a Claude Code SDK entrypoint)."""
    if env.get("TMUX"):
        return False
    if env.get("LEASH_LANE"):
        return True
    return str(env.get("CLAUDE_CODE_ENTRYPOINT") or "").startswith("sdk")


# ---------------------------------------------------------------------------
# rule 1: Bash
# ---------------------------------------------------------------------------
def _bash_rule(tool_input, env):
    if not tool_input.get("run_in_background"):
        return None
    # Interactive tmux sessions persist across turns: backgrounding is fine.
    if env.get("TMUX"):
        return None
    command = str(tool_input.get("command") or "")
    if any(marker in command for marker in DURABLE_LANE_MARKERS):
        return None
    preview = command.strip().splitlines()[0][:160] if command.strip() else "(empty)"
    return (
        "BLOCKED (background-lane-guard): run_in_background in a headless run.\n"
        "\n"
        f"  command: {preview}\n"
        "\n"
        "$TMUX is unset, so this is a headless/bridge run. A backgrounded process\n"
        "is killed when THIS TURN ENDS: its output file stays empty and you will\n"
        "never receive a completion notification. Telling the user you are\n"
        "'watching' or 'will report back' would be a promise the runtime cannot\n"
        "keep: that exact failure already cost three runs and one silent stall.\n"
        "\n"
        "Use one of these instead:\n"
        "  1. FOREGROUND: drop run_in_background and wait for the exit code in\n"
        "     this turn. Bash caps at 600s, so bound the work (an `until` loop\n"
        "     with a retry ceiling, -preset veryfast, chunked renders).\n"
        "  2. HAND OFF to a worker that gets its own session, if it is long:\n"
        "       node ~/dev/claude-telegram-bridge/bg.mjs \"<self-contained task>\"\n"
        "  3. SCHEDULE a durable follow-up if you must wait on external state:\n"
        "       node ~/dev/claude-telegram-bridge/schedule.mjs add in 10m \"<prompt>\" --run\n"
        "\n"
        "Also check the WAIT CONDITION before re-arming anything: on 2026-07-28\n"
        "the poll watched an index bundle hash that never changes for a\n"
        "lazily-loaded chunk, so it could not have fired even in a lane that\n"
        "survived.\n"
    )


# ---------------------------------------------------------------------------
# rule 2: Agent/Task must run in the foreground in a headless lane
# ---------------------------------------------------------------------------
def _agent_foreground_rule(tool_input, env):
    if not is_headless(env):
        return None
    rib = tool_input.get("run_in_background", None)
    if rib is False:
        return None
    shown = "omitted" if "run_in_background" not in tool_input else json.dumps(rib)
    return (
        "BLOCKED (background-lane-guard): Agent dispatch without "
        "run_in_background: false in a headless lane.\n"
        "\n"
        f"  run_in_background: {shown}\n"
        "\n"
        "The Agent tool runs a subagent in the BACKGROUND unless you pass\n"
        "run_in_background: false, and this lane ($TMUX unset, a bridge or SDK\n"
        "run) kills background work at turn end. The subagent dies with the turn\n"
        "and its result will never arrive; polling for it only burns the turn.\n"
        "\n"
        "Fix: re-issue this same call, unchanged, with run_in_background: false.\n"
        "Several foreground Agent calls in ONE message still run in parallel.\n"
        "\n"
        "If the work is genuinely long, hand it to a worker with its own session:\n"
        f"  {HANDOFF}\n"
    )


# ---------------------------------------------------------------------------
# rule 3: the verifier waits for the draft report
# ---------------------------------------------------------------------------
def _parse_started_s(raw):
    """$BG_RUN_STARTED_AT (epoch ms) as epoch seconds, or None."""
    if raw is None:
        return None
    try:
        ms = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(ms) or ms <= 0:
        return None
    return ms / 1000.0


def _draft_rule(payload, tool_input, env, stat_fn=os.stat):
    draft = env.get("BG_REPORT_DRAFT")
    if not draft:
        return None
    if env.get("TMUX"):
        # Bridge workers never run in tmux, but the tmux server's global
        # environment keeps whatever the process that started it had (on this
        # Mac it carries LEASH_LANE from a worker), so a draft path seen here
        # is a dead worker's, not this session's (QA 2026-09-27).
        return None
    sub = tool_input.get("subagent_type")
    if not isinstance(sub, str) or sub.strip().lower() not in VERIFIER_TYPES:
        return None
    if payload.get("agent_id"):
        # Inside a subagent: the draft is the worker's own report.
        return None

    problem = None
    try:
        st = stat_fn(draft)
    except FileNotFoundError:
        problem = "does not exist"
    except Exception:
        return None  # fail open on any other metadata error
    if problem is None:
        if not stat.S_ISREG(st.st_mode):
            return None  # not a file we could ask anyone to fix: fail open
        if st.st_size == 0:
            problem = "is empty"
        else:
            started = _parse_started_s(env.get("BG_RUN_STARTED_AT"))
            if started is not None and st.st_mtime < started - DRAFT_SLACK_S:
                problem = "was last written before this run started"
    if problem is None:
        return None
    return (
        f"BLOCKED (background-lane-guard): {sub.strip()} dispatch before the "
        "draft report is on disk.\n"
        "\n"
        f"  draft report: {draft}\n"
        f"  state: {problem}\n"
        "\n"
        "Write your report as it stands to that file with the Write tool (the\n"
        "full text, not a summary), then re-issue this dispatch. The verifier is\n"
        "the most token heavy step of a run: a usage limit inside it otherwise\n"
        "erases the deliverable, because the report you have not written yet is\n"
        "its only record. The draft is what the bridge and bg-salvage.py hand\n"
        "back if this worker dies before its final message.\n"
    )


# ---------------------------------------------------------------------------
# pure core
# ---------------------------------------------------------------------------
def decide(payload, env):
    """(exit_code, stderr_text, stdout_text) for one PreToolUse payload."""
    if not isinstance(payload, dict):
        return 0, "", ""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")

    if tool == "Bash":
        if not isinstance(tool_input, dict):
            return 0, "", ""
        msg = _bash_rule(tool_input, env)
        return (2, msg, "") if msg else (0, "", "")

    if tool in AGENT_TOOLS:
        if not isinstance(tool_input, dict):
            return 0, "", ""  # never block on a malformed payload
        reasons = []
        draft_msg = _draft_rule(payload, tool_input, env)
        if draft_msg:
            reasons.append(draft_msg)
        fg_msg = _agent_foreground_rule(tool_input, env)
        if fg_msg:
            reasons.append(fg_msg)
        if reasons:
            return 2, "\n".join(reasons), ""
        return 0, "", ""

    if tool == "SendMessage":
        if not is_headless(env):
            return 0, "", ""
        out = json.dumps(
            {
                "hookSpecificOutput": {
                    # No permissionDecision: a warn-only hook must not
                    # approve the call on the permission system's behalf.
                    "hookEventName": "PreToolUse",
                    "additionalContext": SEND_MESSAGE_WARNING,
                }
            }
        )
        return 0, "", out

    return 0, "", ""


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except Exception:
        return 0  # never block on a malformed payload
    code, err, out = decide(payload, os.environ)
    if out:
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    # Fail open: an internal error must never block a tool call.
    try:
        rc = main()
    except BaseException:
        rc = 0
    sys.exit(rc)
