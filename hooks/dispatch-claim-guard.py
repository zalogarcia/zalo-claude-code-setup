#!/usr/bin/env python3
"""
Stop hook: catch a claim that work was handed to a background worker or
subagent when no such dispatch happened in this turn.

Born 2026-09-22: mid-conversation I wrote "I have dispatched a read only
investigation" and sent it without ever calling bg.mjs. Zalo caught it one
message later ("I dont see you sent any bg agent on to this"). The failure mode
is narrating the plan and the action in one breath, then ending the turn. Prose
cannot catch that; the transcript can.

Conservative by construction, because a false positive trains you to ignore it:
  * only PAST-TENSE, first-person, completed-action claims count,
  * a backreference word near the claim ("earlier", "already") suppresses it,
    since referring to a dispatch from a previous turn is legitimate,
  * any real dispatch in the same turn clears it.

Never blocks. Exits 2 with a nudge so the turn can correct itself, capped per
session so it cannot nag.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

MAX_NUDGES = 3
STATE_DIR = Path.home() / ".claude" / "hooks" / ".stop-state"
STATE_TTL_SECONDS = 7 * 24 * 3600
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# A claim that the handoff ALREADY happened. Present perfect or simple past,
# first person, naming a worker/agent/job. Future tense is deliberately absent:
# "I'll hand this off" promises nothing about this turn.
CLAIM_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bi(?:'ve| have)? dispatched\b",
        r"\bi(?:'ve| have) (?:just )?(?:sent|fired|launched|queued|spun up|kicked off)\b"
        r"[^.\n]{0,40}\b(?:workers?|agents?|jobs?|investigations?|briefs?|bg)\b",
        r"\bdispatched (?:a|an|the|one|two|three|four|\d+)\b"
        r"[^.\n]{0,40}\b(?:workers?|agents?|jobs?|investigations?|briefs?)\b",
        r"\bi(?:'ve| have) handed (?:it|this|that|them|the \w+)\b",
        r"\bhanded (?:it|this|that|them) (?:off|over)\b",
        r"\bi(?:'ve| have) (?:put|set) (?:a|an|two|three|\d+)\b"
        r"[^.\n]{0,30}\b(?:workers?|agents?|investigations?)\b[^.\n]{0,20}\bon\b",
        r"\bit(?:'s| is) (?:now )?(?:dispatched|queued|handed off)\b",
        r"\b(?:both|all three|all four|the) (?:briefs?|jobs?|workers?) (?:are|is) (?:now )?(?:queued|dispatched|running)\b",
    )
]

# Near one of these, a past-tense claim is about an EARLIER turn, not this one.
BACKREFERENCE = re.compile(
    r"\b(earlier|already|previously|before|this morning|last turn|a moment ago|"
    r"just now reported|from (?:the |my )?(?:previous|earlier|last))\b",
    re.IGNORECASE,
)
BACKREF_WINDOW = 90

# bg.mjs subcommands that READ state rather than dispatching work.
BG_READ_ONLY = re.compile(
    r"bg\.mjs\s+(?:ps|steer|btw|list|results|salvage|doctor)\b", re.IGNORECASE
)
BG_ANY = re.compile(r"\bbg\.mjs\b", re.IGNORECASE)
DISPATCH_TOOLS = {"Agent", "Task", "Workflow"}


def read_transcript(transcript_path: str) -> list:
    if not transcript_path or not os.path.exists(transcript_path):
        return []
    entries = []
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return entries


def _content_blocks(entry) -> list:
    msg = entry.get("message")
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [c for c in content if isinstance(c, dict)]
    return []


def is_real_user_turn(entry) -> bool:
    """A typed user message, not a tool_result envelope."""
    if entry.get("type") != "user":
        return False
    blocks = _content_blocks(entry)
    if not blocks:
        return False
    return not any(b.get("type") == "tool_result" for b in blocks)


def current_turn_slice(entries: list) -> list:
    """Entries produced since the last real user message."""
    start = 0
    for i, e in enumerate(entries):
        if is_real_user_turn(e):
            start = i
    return entries[start:]


def final_assistant_text(entries: list) -> str:
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        parts = [
            b.get("text", "")
            for b in _content_blocks(entry)
            if b.get("type") == "text"
        ]
        text = "".join(parts).strip()
        if text:
            return text
    return ""


def dispatched_this_turn(turn: list) -> bool:
    for entry in turn:
        if entry.get("type") != "assistant":
            continue
        for block in _content_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            name = block.get("name", "")
            if name in DISPATCH_TOOLS:
                return True
            if name != "Bash":
                continue
            cmd = (block.get("input") or {}).get("command", "")
            if not isinstance(cmd, str) or not BG_ANY.search(cmd):
                continue
            # A read-only bg.mjs call is not a dispatch, but a command can
            # chain both (`bg.mjs --file x && bg.mjs ps`), so strip the
            # read-only invocations and see if any bg.mjs call survives.
            residual = BG_READ_ONLY.sub("", cmd)
            if BG_ANY.search(residual):
                return True
    return False


def find_claim(text: str) -> str:
    for pat in CLAIM_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        lo = max(0, m.start() - BACKREF_WINDOW)
        hi = min(len(text), m.end() + BACKREF_WINDOW)
        if BACKREFERENCE.search(text[lo:hi]):
            continue
        return m.group(0)
    return ""


def _state_file(session_id: str) -> Path:
    return STATE_DIR / f"{session_id}.dispatch-claim"


def bump_counter(session_id: str):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        f = _state_file(session_id)
        try:
            n = int(f.read_text().strip())
        except (OSError, ValueError):
            n = 0
        if n >= MAX_NUDGES:
            return None
        n += 1
        f.write_text(str(n))
        return n
    except OSError:
        return None


def prune_stale_state() -> None:
    try:
        cutoff = time.time() - STATE_TTL_SECONDS
        for f in STATE_DIR.glob("*.dispatch-claim"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                continue
    except OSError:
        pass


def evaluate(entries: list) -> str:
    """Return the offending claim, or '' when the turn is clean."""
    turn = current_turn_slice(entries)
    if not turn:
        return ""
    text = final_assistant_text(turn)
    if not text:
        return ""
    claim = find_claim(text)
    if not claim:
        return ""
    if dispatched_this_turn(turn):
        return ""
    return claim


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    session_id = payload.get("session_id", "")
    if not session_id or not SESSION_ID_RE.match(session_id):
        return 0

    entries = read_transcript(payload.get("transcript_path", ""))
    claim = evaluate(entries)
    if not claim:
        return 0

    n = bump_counter(session_id)
    if n is None:
        return 0

    prune_stale_state()
    sys.stderr.write(
        f"Dispatch claim with no dispatch: you wrote {claim!r} but no bg.mjs "
        f"handoff or Agent call ran in this turn. Either make the dispatch now "
        f"and verify it landed, or correct the claim before sending. "
        f"(nudge {n}/{MAX_NUDGES})\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
