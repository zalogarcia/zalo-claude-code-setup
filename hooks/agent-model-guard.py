#!/usr/bin/env python3
"""PreToolUse guard for Agent/Task dispatches.

Mechanizes the CLAUDE.md subagent model-split policy that the 2026-07-19
weekly audit showed being skipped under momentum (12 usage-limit friction
instances across 11 sessions; Fable-bound fan-outs killed mid-wave): built-in
agent types have no definition file, so a model-less dispatch inherits the
session model — on a Fable session that silently lands the work on Fable.
Policy: built-in dispatches pass model:"opus" explicitly.

Blocks ONLY when ALL hold:
  - tool is Agent/Task and tool_input has no `model`
  - subagent_type is a built-in that inherits the session model
    (general-purpose, Explore, Plan, claude, claude-code-guide, or omitted)
  - the session model resolves to Fable (last assistant model in the
    transcript, falling back to settings.json "model"; unresolvable -> allow)

Custom agents pass (their frontmatter pin governs). "fork" passes (inherits
by design; model overrides are ignored for forks anyway). An explicit model
param always passes — including a deliberate model:"fable".

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import os
import sys

BUILTIN_INHERITING = {
    "general-purpose",
    "explore",
    "plan",
    "claude",
    "claude-code-guide",
    "",
}
PASS_TYPES = {"fork"}

TRANSCRIPT_TAIL_BYTES = 200_000


def session_model(data) -> str:
    """Best-effort session-model resolution; empty string means unknown."""
    tp = data.get("transcript_path") or ""
    try:
        if tp and os.path.isfile(tp):
            with open(tp, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
                tail = f.read().decode("utf-8", "replace")
            model = ""
            for line in tail.splitlines():
                if '"model"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "assistant":
                    continue
                m = (obj.get("message") or {}).get("model")
                if m:
                    model = m  # keep the LAST one seen
            if model:
                return model
    except Exception:
        pass
    try:
        with open(os.path.expanduser("~/.claude/settings.json")) as f:
            return json.load(f).get("model") or ""
    except Exception:
        return ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") not in ("Agent", "Task"):
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    if tool_input.get("model"):
        sys.exit(0)

    subagent = (tool_input.get("subagent_type") or "").strip().lower()
    if subagent in PASS_TYPES:
        sys.exit(0)
    if subagent not in BUILTIN_INHERITING:
        # Custom agent type: its definition frontmatter pins the model.
        sys.exit(0)

    model = session_model(data).lower()
    if not model or "fable" not in model:
        sys.exit(0)

    print(
        "BLOCKED (agent-model-guard): model-less dispatch of built-in agent type "
        f"'{subagent or 'general-purpose'}' on a Fable session would inherit Fable. "
        "CLAUDE.md split policy: built-in/high-volume dispatches pass model:'opus' "
        "explicitly (half-price tokens, protects the Fable session limit). "
        "Re-dispatch with model:'opus' — or model:'fable' explicitly if this single "
        "dispatch's verdict quality genuinely warrants it.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
