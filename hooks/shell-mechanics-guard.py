#!/usr/bin/env python3
"""PreToolUse (Bash) — WARN-ONLY guard for two shell mechanics that silently
destroy evidence in this setup.

Why this exists (14-day audit 2026-08-28, P8; ~30 instances)
-----------------------------------------------------------
Both shapes are already QUIRKS.md lines 1 and 3, front-loaded into every
session by session-start.sh. They were read at minute 0 and violated at minute
40 anyway — front-loading does not survive session momentum, only
point-of-use enforcement does.

A) LOST EXIT CODE (8 events: 1dd83797, c4707086, f2cd725e x2, 1f60501c,
   64f33e26, c350cf73 x2). Two sub-shapes:
     - `${PIPESTATUS[0]}` read after an `&&` chain. PIPESTATUS is rewritten by
       every pipeline, so by the time it is echoed it describes the LAST
       pipeline, not the one that mattered.
     - `$?` read after piping into a pager/filter (`| tail`, `| head`,
       `| grep`). `$?` is the FILTER's status; `tail` succeeds even when the
       build it is summarising failed.
   Each miss forced a full multi-minute gate re-run.

B) RELATIVE cd / relative paths (~22 events). The Bash tool resets cwd between
   calls, so `cd src && npm test` runs from wherever the harness put you, not
   from where the previous call ended.

What it does: exits 0 ALWAYS, injects a one-time-per-class-per-session nudge
carrying the canonical replacement. It never blocks — too many legitimate
shapes exist, and a false block on the Bash tool is a machine-wide outage.

Tests: python3 ~/.claude/hooks/shell-mechanics-guard.test.py
"""

import json
import os
import re
import sys
import tempfile

STATE_DIR = os.environ.get("SHELL_MECH_STATE_DIR") or os.path.join(
    tempfile.gettempdir(), "claude-shell-mech-%d" % os.getuid()
)

# Filters that swallow the status of what feeds them.
FILTERS = (
    "tail", "head", "grep", "egrep", "rg", "sed", "awk", "less", "more",
    "jq", "tee", "wc", "sort", "uniq", "cut", "column", "tr", "cat",
)
_FILTER_RE = re.compile(r"\|\s*(?:[\w./-]*/)?(%s)\b" % "|".join(FILTERS))
_PIPESTATUS_RE = re.compile(r"\$\{?PIPESTATUS")
_DOLLAR_Q_RE = re.compile(r"\$\?")
_LEADING_CD_RE = re.compile(r"^\s*cd\s+(?!-\s*$)([^\s;&|]+)")

EXIT_MSG = (
    "⚠ shell-mechanics-guard (warn only, once per session): this command reads "
    "an exit status that will not be the one you want.\n"
    "  • `${PIPESTATUS[...]}` describes the LAST pipeline run, so an `&&` chain "
    "before it overwrites it.\n"
    "  • `$?` after `| tail` / `| head` / `| grep` is the FILTER's status — "
    "`tail` exits 0 for a build that failed.\n"
    "Canonical shape that survives both (QUIRKS.md line 1):\n"
    "    <cmd> > /tmp/out.log 2>&1; echo EXIT=$?; tail -40 /tmp/out.log\n"
    "Run the command, capture EXIT immediately, THEN look at the log. "
    "(8 gate re-runs in the last 14 days were caused by this.)"
)

CD_MSG = (
    "⚠ shell-mechanics-guard (warn only, once per session): this command starts "
    "with a RELATIVE `cd`. The Bash tool resets the working directory between "
    "calls, so it does not start where your previous call ended — the same "
    "relative path resolved to a different repo ~22 times in the last 14 days "
    "(one of them made sql-guard reject real tables by loading the wrong "
    "repo's schema snapshot).\n"
    "Use an absolute path: `cd /Users/zalo/dev/<repo> && ...`, or pass the "
    "path to the tool directly (`git -C /abs/path status`, `npm --prefix "
    "/abs/path test`)."
)


def _strip_quoted(command):
    """Neutralise string literals so a `|` or `$?` inside one is not read as
    shell mechanics — while preserving what the shell would really expand.

    Single quotes suppress expansion entirely, so they are blanked whole.
    Double quotes DO expand `$?` and `${PIPESTATUS[0]}` (the single most common
    way the lost-exit-code shape is written: `echo "EXIT=${PIPESTATUS[0]}"`),
    so only the structural characters inside them are blanked.
    """

    def _sub(m):
        span = m.group(0)
        if span.startswith("'"):
            return " " * len(span)
        return re.sub(r"[|;&\n]", " ", span)

    return re.sub(r"'[^']*'|\"[^\"]*\"", _sub, command)


def classify(command):
    """Set of warning classes this command earns. Conservative by design:
    anything ambiguous returns nothing."""
    hits = set()
    if not command or not command.strip():
        return hits
    bare = _strip_quoted(command)
    low = bare.lower()

    # `set -o pipefail` / `set -eo pipefail` makes $?-after-pipe meaningful.
    pipefail = "pipefail" in low

    m = _PIPESTATUS_RE.search(bare)
    if m and "&&" in bare[: m.start()]:
        hits.add("exit")

    if not pipefail:
        for q in _DOLLAR_Q_RE.finditer(bare):
            before = bare[: q.start()]
            # $? must belong to a LATER statement than the pipeline, otherwise
            # it is just the (correct) status of a non-piped command.
            sep = max(before.rfind(";"), before.rfind("&&"), before.rfind("\n"))
            if sep == -1:
                continue
            if _FILTER_RE.search(before[:sep]):
                hits.add("exit")
                break

    cd = _LEADING_CD_RE.match(command)
    if cd:
        target = cd.group(1).strip("'\"")
        if target and target[0] not in "/~$" and not target.startswith("%("):
            hits.add("cd")

    return hits


def _state_path(session_id):
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or "")) or "unknown"
    return os.path.join(STATE_DIR, sid + ".json")


def _load(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return set(x for x in data if isinstance(x, str)) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save(path, fired):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".sm-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(sorted(fired), f)
        os.replace(tmp, path)
    except Exception:
        pass


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    payload = json.loads(raw)
    if payload.get("tool_name") != "Bash":
        return
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return

    hits = classify(command)
    if not hits:
        return

    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(payload.get("session_id"))
    fired = _load(path)
    new = [h for h in ("exit", "cd") if h in hits and h not in fired]
    if not new:
        return
    fired.update(new)
    _save(path, fired)

    msg = "\n\n".join(EXIT_MSG if h == "exit" else CD_MSG for h in new)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "additionalContext": msg,
                }
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    # Fail-open contract: this runs before EVERY Bash call on this machine.
    # Any error, malformed payload, or signal must still exit 0 and allow.
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
