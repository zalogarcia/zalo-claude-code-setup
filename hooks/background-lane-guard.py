#!/usr/bin/env python3
"""PreToolUse guard: block `run_in_background` in headless (non-tmux) runs.

Why this exists
---------------
In a headless Claude Code run — the Telegram bridge lane, cwd ~/dev, no
terminal — anything backgrounded dies when the turn that spawned it ends.
`nohup … &`, `launchctl submit`, and the harness's own `run_in_background`
lane all fail the same way: the process is killed with the turn, the output
file stays 0 bytes, and NO completion notification is ever delivered.

That fact was already written in ~/dev/CLAUDE.md — it had cost three runs
(a 49MB render discarded, a mux killed at 561KB) — and was broken again on
2026-07-28: a poller was armed to watch a Vercel deploy, the turn ended, the
process died silently, and Zalo had to prompt "Check" because the promised
wake-up could never arrive. Prose did not hold under momentum. This does.

What it blocks
--------------
Bash calls with `run_in_background: true` when `$TMUX` is unset.

What it allows
--------------
- Everything when running inside tmux (an interactive session survives).
- Foreground Bash of any kind.
- Bash whose command is itself a handoff to a durable lane (bg.mjs,
  schedule.mjs) — those are the sanctioned ways to outlive a turn.

The two lanes that DO survive a headless turn end
-------------------------------------------------
1. `node ~/dev/claude-telegram-bridge/bg.mjs "<self-contained task>"`
   — a separate worker session; its report is delivered back to you.
2. `node ~/dev/claude-telegram-bridge/schedule.mjs add in 10m "<prompt>" --run`
   — file-based, survives daemon restarts; the durable way to poll.
Otherwise: run it in the FOREGROUND and wait for the exit code in-turn.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import os
import sys

# Commands that are themselves durable-lane handoffs — backgrounding these is
# pointless but harmless, and blocking them would be confusing. Substring match
# against the command text.
DURABLE_LANE_MARKERS = (
    "claude-telegram-bridge/bg.mjs",
    "claude-telegram-bridge/schedule.mjs",
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on a malformed payload

    if payload.get("tool_name") != "Bash":
        return 0

    tool_input = payload.get("tool_input") or {}
    if not tool_input.get("run_in_background"):
        return 0

    # Interactive tmux sessions persist across turns — backgrounding is fine.
    if os.environ.get("TMUX"):
        return 0

    command = str(tool_input.get("command") or "")
    if any(marker in command for marker in DURABLE_LANE_MARKERS):
        return 0

    preview = command.strip().splitlines()[0][:160] if command.strip() else "(empty)"
    sys.stderr.write(
        "BLOCKED (background-lane-guard): run_in_background in a headless run.\n"
        "\n"
        f"  command: {preview}\n"
        "\n"
        "$TMUX is unset, so this is a headless/bridge run. A backgrounded process\n"
        "is killed when THIS TURN ENDS: its output file stays empty and you will\n"
        "never receive a completion notification. Telling the user you are\n"
        "'watching' or 'will report back' would be a promise the runtime cannot\n"
        "keep — that exact failure already cost three runs and one silent stall.\n"
        "\n"
        "Use one of these instead:\n"
        "  1. FOREGROUND — drop run_in_background and wait for the exit code in\n"
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
    return 2


if __name__ == "__main__":
    sys.exit(main())
