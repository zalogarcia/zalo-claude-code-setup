#!/usr/bin/env python3
"""Bridge inline budget: adds up the foreground Bash time of ONE turn in the
Telegram bridge CHAT lane and tells the model, twice at most, to hand the
remainder to a background worker.

Why (2026-09-17)
----------------
The chat lane (M) "collected" three finished background jobs inline: read the
diffs, ran three full test suites, dispatched QA audits, fixed findings, re-ran
gates, committed, pushed, ran Playwright rigs. About 40 minutes in one turn,
each step short, the owner unreachable the whole time. The prose rule in
~/dev/CLAUDE.md ("Stay reachable: hand long jobs to the background lane", more
than about 2 minutes goes to bg.mjs) did not fire because nobody was adding
the steps up. This hook adds them up.

Scope
-----
Fires ONLY when the environment says LEASH_LANE=chat (set by bridge.mjs on the
chat lane spawn; background workers get LEASH_LANE=bg, interactive sessions
have nothing) AND $TMUX is unset. Anything else: exit 0, no output, no state.
Hooks inherit the Claude process environment, so the marker set on the spawn
is visible here, in the main thread and inside subagents alike.

Accounting (payload fields relied on; Claude Code CLI 2.1.259, verified live
2026-09-17 with a capture hook, and per https://code.claude.com/docs/en/hooks)
--------------------------------------------------------------------------------
- PreToolUse/Bash: `tool_use_id` (per call), `prompt_id` (per user prompt,
  "UUID identifying the user prompt currently being processed"), `session_id`.
  The start clock is recorded under `tool_use_id`.
- PostToolUse/Bash fires only when the command SUCCEEDS; a failing command
  (`exit 3`, a red test run) fires PostToolUseFailure instead. Both carry the
  same `tool_use_id` and an optional `duration_ms` ("Tool execution time in
  milliseconds. Excludes time spent in permission prompts and PreToolUse
  hooks"). Elapsed = Post clock minus the recorded start (the wall time the
  owner could not reach the lane); `duration_ms` is the fallback when no start
  was recorded.
- Inside a subagent the payload carries the PARENT's `session_id` and
  `prompt_id` plus `agent_id` and `agent_type` (verified: an Explore subagent's
  Bash arrived with the main session id and prompt id). Those calls count
  toward the same turn; the lane is just as unreachable while a subagent runs.
- A turn is one `prompt_id`. The total resets when it changes (any payload,
  subagents included, since they carry the parent's), or, as a fallback for a
  payload without one, when a PreToolUse arrives more than IDLE_RESET_S after
  the last recorded activity.

Thresholds
----------
At FIRST_WARN_S cumulative seconds in one turn inject `additionalContext`
once; at SECOND_WARN_S inject once more, prefixed "SECOND WARNING". Never
blocks (never exit 2): this hook advises, the model decides. Only COMPLETED
calls count, and a warning needs at least two completed calls in the turn: a
single long call is the prose rule's business (a 5 minute test run is already
a violation), this hook's job is the sum nobody was keeping.

State: one small JSON per session under state/bridge-inline-budget/ (override
the dir with BRIDGE_INLINE_BUDGET_STATE_DIR, the clock with
BRIDGE_INLINE_BUDGET_NOW, both for tests); files older than 48h are deleted
opportunistically; a missing or corrupt file is a zero total.

Tests: python3 ~/.claude/hooks/bridge-inline-budget.test.py

Fail-open contract: any internal error, malformed stdin, unknown payload, or
signal (BaseException, incl. KeyboardInterrupt) => exit 0, no output.
"""

import json
import os
import re
import sys
import tempfile
import time

STATE_DIR = os.environ.get("BRIDGE_INLINE_BUDGET_STATE_DIR") or os.path.expanduser(
    "~/.claude/hooks/state/bridge-inline-budget"
)

LANE_ENV = "LEASH_LANE"
CHAT_LANE = "chat"
FIRST_WARN_S = 180  # cumulative foreground seconds in one turn before the first nudge
SECOND_WARN_S = 480  # ... before the second (and last) nudge
MIN_CALLS = 2  # a warning needs this many completed calls: sums, not single long calls
IDLE_RESET_S = 600  # fallback turn boundary when a payload has no prompt_id
PENDING_MAX = 50  # starts kept per turn; a Pre with no Post (killed turn) must not pile up
STATE_MAX_AGE_S = 48 * 3600
HANDOFF = "node ~/dev/claude-telegram-bridge/bg.mjs --file <brief>"

POST_EVENTS = ("PostToolUse", "PostToolUseFailure")


def _now():
    """Wall clock; BRIDGE_INLINE_BUDGET_NOW (epoch seconds) overrides it for tests."""
    raw = os.environ.get("BRIDGE_INLINE_BUDGET_NOW")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return time.time()


def in_scope(env=None):
    env = os.environ if env is None else env
    if env.get(LANE_ENV) != CHAT_LANE:
        return False
    if env.get("TMUX"):
        return False
    return True


# --- state ------------------------------------------------------------------


def _fresh_state():
    return {
        "schema": 1,
        "prompt_id": "",
        "total_s": 0.0,
        "calls": 0,
        "warned": 0,
        "last_seen": 0.0,
        "pending": {},
    }


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _load_state(path):
    """A missing, unreadable, or corrupt file is a zero total, never an error."""
    try:
        with open(path) as f:
            st = json.load(f)
        if not isinstance(st, dict) or st.get("schema") != 1:
            return _fresh_state()
        if not isinstance(st.get("prompt_id"), str):
            return _fresh_state()
        if not _is_num(st.get("total_s")) or not _is_num(st.get("last_seen")):
            return _fresh_state()
        if not isinstance(st.get("calls"), int) or st["calls"] < 0:
            return _fresh_state()
        if not isinstance(st.get("warned"), int) or not 0 <= st["warned"] <= 2:
            return _fresh_state()
        pending = st.get("pending")
        if not isinstance(pending, dict):
            return _fresh_state()
        st["pending"] = {
            k: v for k, v in pending.items() if isinstance(k, str) and _is_num(v)
        }
        st["total_s"] = float(st["total_s"])
        st["last_seen"] = float(st["last_seen"])
        return st
    except Exception:
        return _fresh_state()


def _save_state(path, st):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".bib-", suffix=".json")
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


# --- accounting -------------------------------------------------------------


def _reset_turn(st, prompt_id):
    st["prompt_id"] = prompt_id
    st["total_s"] = 0.0
    st["calls"] = 0
    st["warned"] = 0
    st["pending"] = {}


def _maybe_new_turn(st, payload, now, allow_idle_reset):
    prompt_id = payload.get("prompt_id")
    if isinstance(prompt_id, str) and prompt_id:
        if prompt_id != st["prompt_id"]:
            _reset_turn(st, prompt_id)
        return
    # No prompt_id (older CLI): a long gap with no Bash activity is the only
    # turn boundary we can see. Applied at the START of a call only, so a
    # single long call can never reset itself at its own Post.
    if allow_idle_reset and st["last_seen"] and now - st["last_seen"] > IDLE_RESET_S:
        _reset_turn(st, st["prompt_id"])


def _tool_use_id(payload):
    tuid = payload.get("tool_use_id")
    return tuid if isinstance(tuid, str) and tuid else ""


def _backgrounded(payload):
    return bool((payload.get("tool_input") or {}).get("run_in_background"))


def _warning(total_s, second):
    text = (
        f"Bridge chat lane: {int(round(total_s))} s of foreground Bash this turn. "
        "The owner cannot reach you while you work inline. Hand the remainder to "
        f"`{HANDOFF}` and reply with what you handed off."
    )
    return "SECOND WARNING: " + text if second else text


def on_pre(st, payload, now):
    if _backgrounded(payload):
        return None
    _maybe_new_turn(st, payload, now, allow_idle_reset=True)
    tuid = _tool_use_id(payload)
    if not tuid:
        tuid = f"seq-{st['calls']}-{len(st['pending'])}"
    st["pending"][tuid] = now
    if len(st["pending"]) > PENDING_MAX:
        for k in sorted(st["pending"], key=st["pending"].get)[: len(st["pending"]) - PENDING_MAX]:
            st["pending"].pop(k, None)
    st["last_seen"] = now
    return None


def on_post(st, payload, now):
    if _backgrounded(payload):
        return None
    _maybe_new_turn(st, payload, now, allow_idle_reset=False)
    tuid = _tool_use_id(payload)
    start = st["pending"].pop(tuid, None) if tuid else None
    if start is not None:
        elapsed = now - start
    else:
        # No recorded start (Pre hook lost, state cleaned, older payload):
        # the harness's own measurement is the next best thing.
        duration = payload.get("duration_ms")
        elapsed = duration / 1000.0 if _is_num(duration) else 0.0
    if elapsed < 0:
        elapsed = 0.0
    st["total_s"] += elapsed
    st["calls"] += 1
    st["last_seen"] = now
    if st["calls"] < MIN_CALLS:
        return None
    if st["total_s"] >= SECOND_WARN_S and st["warned"] < 2:
        st["warned"] = 2
        return _warning(st["total_s"], second=True)
    if st["total_s"] >= FIRST_WARN_S and st["warned"] < 1:
        st["warned"] = 1
        return _warning(st["total_s"], second=False)
    return None


def main(env=None, now=None):
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    if not in_scope(env):
        return 0
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name")
    if payload.get("tool_name") != "Bash":
        return 0
    if event == "PreToolUse":
        handler = on_pre
    elif event in POST_EVENTS:
        handler = on_post
    else:
        return 0

    now = _now() if now is None else now
    session_id = re.sub(r"[^A-Za-z0-9_-]", "", str(payload.get("session_id") or ""))
    if not session_id:
        session_id = "unknown"
    os.makedirs(STATE_DIR, exist_ok=True)
    _cleanup_old()
    state_path = os.path.join(STATE_DIR, session_id + ".json")
    st = _load_state(state_path)
    nudge = handler(st, payload, now)
    _save_state(state_path, st)
    if nudge:
        output = {"hookEventName": event, "additionalContext": nudge}
        print(json.dumps({"hookSpecificOutput": output}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
