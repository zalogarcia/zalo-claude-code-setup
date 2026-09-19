#!/usr/bin/env python3
"""Loop detector — mechanizes the 3+ Fixes Rule and the 2-Strike Probe Rule
from ~/.claude/rules/problem-solving.md (prose rules measured skipped under
momentum; hooks fired 4/4 in the 2026-07 audits).

What it detects
---------------
A) Repeated same-shape Bash failures. Commands are normalized to a "shape":
   head (basename of first non-wrapper token; +subcommand for
   git/npm/npx/gh/supabase/docker/cargo, +script for `npm run`) plus the
   sorted set of path-looking tokens. Rewritten flags/args with the same
   head+paths are the SAME shape — the measured incident was ~6 slightly
   rewritten n8n expressions, not identical retries. When a command has no
   subcommand and no path tokens (`python3 -c ...`, `curl "$VAR"`), the
   first two non-flag args are appended as a discriminator so unrelated
   one-liners don't collapse into one shape (QA finding 2026-08-01) —
   trade-off: rewritten pathless variants regroup only if their leading
   args match.
   - >=3 consecutive failures of one shape -> 3+ Fixes nudge
   - >=2 consecutive failures of an API-shaped command (curl/wget/http* or a
     URL in the command) -> 2-Strike Probe nudge
B) Edit spiral: >=4 Edit/Write/MultiEdit calls to the same file since the
   last PASSING verification-class Bash command (npm/npx/node/python3/pytest/
   vitest/tsc/deno/cargo/go/make/vercel/supabase — also recognized behind
   wrappers like `timeout 120 npm test` and inside `bash -c '...'`). A pass
   resets ALL edit counters. *.md/*.markdown/*.mdx files are exempt.

Empirical basis (Claude Code CLI 2.1.220, captured 2026-08-01; samples kept
at state/loop-detector/payload-samples.jsonl — PostToolUse and PreToolUse
payloads captured live)
---------------------------------------------------------------------------
- PostToolUse fires ONLY when a tool call succeeds. A failing Bash command
  (sh -c 'exit 3', curl exit 7) produces NO PostToolUse event at all, and
  the success payload carries no exit-code field. Informational non-zero
  exits (grep no-match, diff differing) DO fire, with
  tool_response.returnCodeInterpretation set.
- Therefore failures are counted on PreToolUse: each attempt of a shape
  increments its counter; a PostToolUse success of that shape resets it.
  N prior attempts with no success in between = N failures, known at the
  Pre of attempt N+1 — which is exactly when the nudge is injected.
- Feedback rail: hookSpecificOutput.additionalContext reaches the model on
  BOTH PreToolUse (with permissionDecision "allow" — non-blocking) and
  PostToolUse (verified live with marker hooks on both events). exit 2 +
  stderr also works on both but blocks/errors the call; we deliberately
  nudge instead of block.
- tool_response.interrupted=True (when a Post fires at all) un-counts the
  attempt; interrupted commands never count as failures.

Anti-nag: each key fires once at its threshold, re-arms after REARM more
failures (escalated wording), resets fully on success; global cap of
CAP_MAX nudges per CAP_WINDOW tracked tool calls per session.

Tuning: the constants right below. State: one small JSON per session under
state/loop-detector/ (override dir with LOOP_DETECTOR_STATE_DIR for tests);
files older than 48h are opportunistically deleted; corrupt or
foreign-written state entries are dropped on load (self-heal).

Tests: python3 ~/.claude/hooks/loop-detector.test.py  (must stay green
before touching ~/.claude/settings.json wiring).

Fail-open contract: this hook runs on every Bash/Edit/Write/MultiEdit call
in EVERY session on this machine. Any internal error, malformed stdin,
unknown payload, or signal (BaseException, incl. KeyboardInterrupt) =>
exit 0, no output. It must never exit non-zero.
"""

import json
import os
import re
import sys
import tempfile
import time

STATE_DIR = os.environ.get("LOOP_DETECTOR_STATE_DIR") or os.path.expanduser(
    "~/.claude/hooks/state/loop-detector"
)

GENERIC_THRESHOLD = 3  # failures of one shape before the 3+ Fixes nudge
API_THRESHOLD = 2  # failures of an API-shaped command before the 2-Strike nudge
EDIT_THRESHOLD = 4  # same-file edits with no passing verification between
REARM = 3  # additional failures/edits before an escalated re-fire
CAP_MAX = 2  # max nudges ...
CAP_WINDOW = 20  # ... per this many tracked tool calls, per session
STATE_MAX_AGE_S = 48 * 3600

# exit-code-1-is-informational heads: a "failure" here is exploration, not a
# failed fix. Never counted.
EXCLUDED_HEADS = {
    "grep",
    "rg",
    "test",
    "[",
    "[[",
    "diff",
    "cmp",
    "which",
    "command",
    "ls",
    "find",
    "pgrep",
}
MULTIPART_HEADS = {"git", "npm", "npx", "gh", "supabase", "docker", "cargo"}
API_HEADS = {"curl", "wget", "http", "https"}
VERIFY_HEADS = {
    "npm",
    "npx",
    "node",
    "python3",
    "pytest",
    "vitest",
    "tsc",
    "deno",
    "cargo",
    "go",
    "make",
    "vercel",
    "supabase",
}
WRAPPER_HEADS = {"time", "sudo", "nohup", "caffeinate", "env", "stdbuf", "timeout", "xargs"}
SHELL_C_HEADS = {"bash", "sh", "zsh", "dash"}
# flags whose following token is a value, not a subcommand (git -C <dir> etc.)
VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--prefix", "--project"}
DOC_EXTS = (".md", ".markdown", ".mdx")

# C) Python "ghost edit" detector (audit 2026-08-28, P10). A PostToolUse
# formatter (prettier-format.sh for ts/js/css/json, ruff for py) rewrites a
# file right after Claude Edits/Writes it. A later python one-liner that does
# `s = s.replace(OLD, NEW)` against an anchor copied from BEFORE that rewrite
# silently matches nothing, writes the file back unchanged, and reports
# success — the miss surfaces only at build/assembly time (5 events in the
# window: a build failure, a ghost video frame that survived four verification
# stills, and two dead-anchor Edits). Unlike the Edit tool, a python-scripted
# edit bypasses the stale-read protection entirely, so nothing else catches it.
# Warn-only: `assert OLD in s` before the replace turns the silent no-op into a
# loud failure, and that is all this nudge asks for.
FORMATTED_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".json")
FORMATTED_MAX = 200  # cap the tracked set; oldest entries drop first
_PY_INTERP_RE = re.compile(r"\bpython3?\b")
_REPLACE_RE = re.compile(r"\.replace\s*\(")
_WRITEBACK_RE = re.compile(
    r"""open\s*\([^)]*['"][rar+]*w[b+t]*['"]|\.write_text\s*\(|\.writelines\s*\(|\.write\s*\(""",
)
# Any of these means the edit is already guarded — an unmatched anchor will
# raise instead of vanishing, which is exactly the ask.
_GUARDED_RE = re.compile(r"\bassert\b|\braise\b|\bsys\.exit\b|\bcount\s*=|\bre\.subn\b")

ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECT_PREFIX = re.compile(r"^[0-9]*>>?")
EXT_TOKEN = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,7}$")
NUMERIC_TOKEN = re.compile(r"^[0-9]+(\.[0-9]+)?[smhd]?$")


def _tokens(text):
    try:
        import shlex

        return shlex.split(text, posix=True)
    except Exception:
        return text.split()


def _segments(command):
    return [s.strip() for s in re.split(r"\|\||&&|;|\n|\|", command) if s.strip()]


def _head_of(tokens):
    for tok in tokens:
        if ENV_ASSIGN.match(tok):
            continue
        tok = REDIRECT_PREFIX.sub("", tok)
        if not tok or tok.startswith("-"):
            continue
        head = os.path.basename(tok)
        if head in WRAPPER_HEADS or NUMERIC_TOKEN.match(head):
            continue
        return head
    return ""


def _shell_c_script(tokens):
    """For `bash -c '<script>'` style tokens, return the inner script."""
    for i, tok in enumerate(tokens[:-1]):
        if tok == "-c":
            return tokens[i + 1]
    return None


def _segment_heads(command, depth=0):
    heads = []
    for seg in _segments(command):
        toks = _tokens(seg)
        head = _head_of(toks)
        if not head:
            continue
        heads.append(head)
        if head in SHELL_C_HEADS and depth < 2:
            inner = _shell_c_script(toks)
            if inner:
                heads.extend(_segment_heads(inner, depth + 1))
    return heads


def _path_tokens(tokens):
    paths = set()
    for tok in tokens:
        tok = REDIRECT_PREFIX.sub("", tok)
        if ENV_ASSIGN.match(tok):
            tok = tok.split("=", 1)[1]
        if not tok or tok.startswith("-"):
            continue
        if "/" in tok or EXT_TOKEN.search(tok):
            paths.add(tok)
    return paths


def analyze(command):
    """Return (head, shape_key, api_shaped) for a Bash command string."""
    primary_head, primary_tokens = "", []
    for seg in _segments(command):
        toks = _tokens(seg)
        head = _head_of(toks)
        if head and head != "cd":
            primary_head, primary_tokens = head, toks
            break
        if head and not primary_head:
            primary_head, primary_tokens = head, toks
    if not primary_head:
        return "", "", False

    # args after the head, with flags, flag-values, and env assignments
    # removed. Flag-value skipping (git -C <dir>) only applies to subcommand
    # heads — for python3/sh/curl the value after -c IS the discriminator.
    args = []
    seen_head = False
    skip_next = False
    for tok in primary_tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in VALUE_FLAGS and primary_head in MULTIPART_HEADS:
            skip_next = True
            continue
        if tok.startswith("-") or ENV_ASSIGN.match(tok):
            continue
        if not seen_head:
            if os.path.basename(REDIRECT_PREFIX.sub("", tok)) == primary_head:
                seen_head = True
            continue
        args.append(tok)

    sub = ""
    if primary_head in MULTIPART_HEADS:
        candidates = [a for a in args if "/" not in a]
        if candidates:
            sub = candidates[0]
            if primary_head == "npm" and sub == "run" and len(candidates) > 1:
                sub = "run " + candidates[1]

    paths = _path_tokens(_tokens(command))
    api = primary_head in API_HEADS or "http://" in command or "https://" in command
    parts = [primary_head]
    if sub:
        parts.append(sub)
    if not sub and not paths:
        # pathless one-liners (`python3 -c ...`, `curl "$VAR"`): discriminate
        # by leading args so unrelated commands don't share a shape
        parts.extend(a[:24] for a in args[:2])
    parts.extend(sorted(paths))
    return primary_head, " ".join(parts), api


# --- state ------------------------------------------------------------------


def _fresh_state():
    return {"schema": 1, "calls": 0, "nudges": [], "shapes": {}, "edits": {}, "formatted": {}}


def _sane_rec(value, fields):
    return isinstance(value, dict) and all(
        isinstance(value.get(f), int) and value.get(f) >= 0 for f in fields
    )


def _load_state(path):
    try:
        with open(path) as f:
            st = json.load(f)
        if not isinstance(st, dict) or st.get("schema") != 1:
            return _fresh_state()
        for field, typ in (
            ("calls", int),
            ("nudges", list),
            ("shapes", dict),
            ("edits", dict),
        ):
            if not isinstance(st.get(field), typ):
                return _fresh_state()
        # deep-validate: drop entries a foreign writer corrupted (self-heal)
        st["shapes"] = {
            k: v
            for k, v in st["shapes"].items()
            if _sane_rec(v, ("attempts", "last_fired"))
        }
        st["edits"] = {
            k: v
            for k, v in st["edits"].items()
            if _sane_rec(v, ("count", "last_fired"))
        }
        st["nudges"] = [c for c in st["nudges"] if isinstance(c, int)]
        # "formatted" was added after schema 1 shipped; a state file without it
        # is valid, not corrupt — default it rather than discarding the session.
        fmt = st.get("formatted")
        st["formatted"] = (
            {k: v for k, v in fmt.items() if isinstance(k, str) and isinstance(v, int)}
            if isinstance(fmt, dict)
            else {}
        )
        return st
    except Exception:
        return _fresh_state()


def _save_state(path, st):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".ld-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(st, f)
    os.replace(tmp, path)


def _cleanup_old():
    try:
        now = time.time()
        for name in os.listdir(STATE_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(STATE_DIR, name)
            try:
                if now - os.path.getmtime(path) > STATE_MAX_AGE_S:
                    os.unlink(path)
            except OSError:
                pass
    except OSError:
        pass


# --- nudges -----------------------------------------------------------------


def _cap_ok(st):
    st["nudges"] = [c for c in st["nudges"] if st["calls"] - c < CAP_WINDOW]
    return len(st["nudges"]) < CAP_MAX


def _shape_nudge(shape, n, api, escalated):
    shape = shape[:100]
    if api:
        if escalated:
            return (
                f"⚠ Loop detector: STILL failing against `{shape}` — {n} "
                "consecutive failures. No more rewritten guesses: capture the "
                "endpoint's real response/payload first (2-Strike Probe Rule, "
                "~/.claude/rules/problem-solving.md)."
            )
        return (
            f"⚠ Loop detector: {n} failed calls against the same external "
            f"endpoint (`{shape}`). Per the 2-Strike Probe Rule "
            "(~/.claude/rules/problem-solving.md): the next action MUST be a "
            "ground-truth probe — a validate_only/dry-run flag, GET the live "
            "resource, capture the real payload — never another rewritten guess."
        )
    if escalated:
        return (
            f"⚠ Loop detector: STILL looping — `{shape}` is at {n} "
            "consecutive failures. The 3+ Fixes Rule already fired for this "
            "command. Stop patching; state the assumption all attempts shared, "
            "verify it with a direct check, or question the architecture."
        )
    return (
        f"⚠ Loop detector: `{shape}` has now failed {n} consecutive times "
        "(rewritten variants included). Per the 3+ Fixes Rule "
        "(~/.claude/rules/problem-solving.md): STOP fixing. Question the "
        "architecture — the bug is probably not where you've been looking. "
        f"Name the assumption all {n} attempts shared, and test THAT instead of "
        f"writing attempt {n + 1}."
    )


def _edit_nudge(file_path, n, escalated):
    if escalated:
        return (
            f"⚠ Loop detector: `{file_path}` is now at {n} edits with still "
            "no passing verification. Run the build/test NOW; if it fails, the "
            "design — not the next patch — is the problem (3+ Fixes Rule, "
            "~/.claude/rules/problem-solving.md)."
        )
    return (
        f"⚠ Loop detector: `{file_path}` has been edited {n} times with no "
        "passing verification in between. Per the 3+ Fixes Rule "
        "(~/.claude/rules/problem-solving.md): stop editing, run the "
        "verification (build/typecheck/test), and if it still fails, question "
        "the design rather than patching again."
    )


def _ghost_edit_target(command, formatted):
    """Path of a formatter-touched file this command is about to python-replace
    without a guard, or None. Deliberately conservative: every condition must
    hold, and anything unparseable simply returns None."""
    if not formatted:
        return None
    if not _PY_INTERP_RE.search(command):
        return None
    if not _REPLACE_RE.search(command):
        return None
    if not _WRITEBACK_RE.search(command):
        return None
    if _GUARDED_RE.search(command):
        return None
    for path, warned in formatted.items():
        if warned:
            continue
        base = os.path.basename(path)
        if path in command or (base and base in command):
            return path
    return None


def _ghost_nudge(file_path):
    return (
        f"⚠ Loop detector: this python edit rewrites `{file_path}`, which a "
        "PostToolUse formatter (prettier/ruff) reformatted after your last "
        "Edit/Write — so an anchor string copied from before that rewrite may "
        "no longer exist on disk. `str.replace` returns the string UNCHANGED "
        "when it matches nothing, so the edit would silently no-op and still "
        "report success (5 such ghosts in the 14-day audit, found only at "
        "build time). Re-Read the file, and guard the edit: "
        "`assert OLD in s, 'anchor missing'` before replacing, or use "
        "`s, n = re.subn(...)` and check n."
    )


# --- event handlers ---------------------------------------------------------


def _on_pre_bash(st, payload):
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return None
    st["calls"] += 1
    ghost = _ghost_edit_target(command, st.get("formatted") or {})
    if ghost and _cap_ok(st):
        st["formatted"][ghost] = 1  # once per file per session
        st["nudges"].append(st["calls"])
        return _ghost_nudge(ghost)
    head, key, api = analyze(command)
    if not head or head in EXCLUDED_HEADS:
        return None
    rec = st["shapes"].setdefault(key, {"attempts": 0, "last_fired": 0, "api": api})
    prior_failures = rec["attempts"]
    rec["attempts"] = prior_failures + 1
    threshold = API_THRESHOLD if api else GENERIC_THRESHOLD
    due = prior_failures >= threshold and (
        rec["last_fired"] == 0 or prior_failures >= rec["last_fired"] + REARM
    )
    if due and _cap_ok(st):
        escalated = rec["last_fired"] > 0
        rec["last_fired"] = prior_failures
        st["nudges"].append(st["calls"])
        return _shape_nudge(key, prior_failures, api, escalated)
    return None


def _on_post_bash(st, payload):
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return
    head, key, api = analyze(command)
    response = payload.get("tool_response")
    if isinstance(response, dict) and response.get("interrupted"):
        rec = st["shapes"].get(key)
        if rec and rec["attempts"] > 0:
            rec["attempts"] -= 1
        return
    # PostToolUse only fires on success (empirical, CLI 2.1.220): reset shape.
    st["shapes"].pop(key, None)
    if any(h in VERIFY_HEADS for h in _segment_heads(command)):
        st["edits"] = {}


def _on_post_edit(st, payload):
    file_path = str((payload.get("tool_input") or {}).get("file_path") or "")
    if not file_path or file_path.lower().endswith(DOC_EXTS):
        return None
    # A formatter runs on this file right after this event; remember it so a
    # later python-scripted replace can be warned about (P10).
    if file_path.lower().endswith(FORMATTED_EXTS):
        fmt = st.setdefault("formatted", {})
        fmt[file_path] = 0
        if len(fmt) > FORMATTED_MAX:
            for k in list(fmt)[: len(fmt) - FORMATTED_MAX]:
                fmt.pop(k, None)
    st["calls"] += 1
    rec = st["edits"].setdefault(file_path, {"count": 0, "last_fired": 0})
    rec["count"] += 1
    n = rec["count"]
    due = n >= EDIT_THRESHOLD and (
        rec["last_fired"] == 0 or n >= rec["last_fired"] + REARM
    )
    if due and _cap_ok(st):
        escalated = rec["last_fired"] > 0
        rec["last_fired"] = n
        st["nudges"].append(st["calls"])
        return _edit_nudge(file_path, n, escalated)
    return None


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    payload = json.loads(raw)
    event = payload.get("hook_event_name")
    tool = payload.get("tool_name")
    if event == "PreToolUse":
        handler = _on_pre_bash if tool == "Bash" else None
    elif event == "PostToolUse":
        if tool == "Bash":
            handler = _on_post_bash
        elif tool in ("Edit", "Write", "MultiEdit"):
            handler = _on_post_edit
        else:
            handler = None
    else:
        handler = None
    if handler is None:
        return 0

    session_id = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or ""))
    if not session_id:
        session_id = "unknown"
    os.makedirs(STATE_DIR, exist_ok=True)
    _cleanup_old()
    state_path = os.path.join(STATE_DIR, session_id + ".json")
    st = _load_state(state_path)
    nudge = handler(st, payload)
    _save_state(state_path, st)
    if nudge:
        output = {"hookEventName": event, "additionalContext": nudge}
        if event == "PreToolUse":
            output["permissionDecision"] = "allow"
        print(json.dumps({"hookSpecificOutput": output}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
