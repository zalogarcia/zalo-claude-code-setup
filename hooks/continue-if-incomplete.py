#!/usr/bin/env python3
"""
Stop hook: detect mid-task halts and nudge Claude to continue.

Conservative heuristics on the last assistant text message from the transcript.
Per-session counter capped at MAX_NUDGES, reset by reset-stop-counter.sh on
UserPromptSubmit.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

MAX_NUDGES = 2
MIN_TEXT_LEN = 20
STATE_DIR = Path.home() / ".claude" / "hooks" / ".stop-state"
STATE_TTL_SECONDS = 7 * 24 * 3600
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_ALLOWED_PREFIX = (
    r"(?:(?:and|then|so|now|next|also|first|finally|ok|okay|alright|"
    r"got it|sure|right)[\s,]+)*"
)

TRAILING_MID_ACTION = re.compile(
    r"^" + _ALLOWED_PREFIX +
    r"("
    r"next,?\s+i[''']?ll\b|"
    r"i will now\b|"
    r"now i[''']?ll\b|"
    r"let me (?:now |first |then |just |go (?:ahead )?and )?"
    r"(?:run|check|try|write|add|fix|update|create|build|test|verify|"
    r"look|investigate|explore|examine|read|inspect|trace|review|start|"
    r"begin|do|handle|tackle|take|work|kick|implement|apply|make|"
    r"patch|wire|set|install|configure)\b|"
    r"i[''']?ll (?:now |first |then |just |go ahead and )?"
    r"(?:run|write|add|fix|update|create|build|test|verify|check|look|"
    r"investigate|explore|examine|read|inspect|trace|review|start|begin|"
    r"proceed|continue|go|do|handle|tackle|take|work|kick|implement|"
    r"apply|make|patch|wire|set|install|configure)\b|"
    r"moving on to\b|"
    r"proceeding (?:to|with)\b|"
    r"kicking off\b|"
    r"starting (?:the|on|with|to)\b"
    r")",
    re.IGNORECASE,
)

COMPLETION_LEXICAL = re.compile(
    r"\b(done|complete|completed|finished|ready|all set|over to you|"
    r"let me know|anything else|no bugs found|no issues)\b",
    re.IGNORECASE,
)


def read_last_assistant_entry(transcript_path: str) -> tuple[str, str | None]:
    """Return (text, trailing_block_type) from the FINAL assistant entry only.

    trailing_block_type is the `type` of the last content block ("text",
    "tool_use", etc.) or None if unavailable. This lets callers detect turns
    that ended mid-action with a tool call and no summary text.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return "", None
    last_entry = None
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "assistant":
                    last_entry = entry
    except OSError:
        return "", None

    if not last_entry:
        return "", None
    msg = last_entry.get("message")
    if not isinstance(msg, dict):
        return "", None
    content = msg.get("content")
    if isinstance(content, str):
        return content, "text"
    if not isinstance(content, list):
        return "", None

    text_parts: list[str] = []
    trailing: str | None = None
    for c in content:
        if not isinstance(c, dict):
            continue
        t = c.get("type")
        if t:
            trailing = t
        if t == "text":
            text_parts.append(c.get("text", ""))
    return "".join(text_parts).strip(), trailing


def last_sentence(text: str) -> str:
    last_line = text.split("\n")[-1].strip()
    if not last_line:
        return ""
    sentences = re.split(r"(?<=[.!?])(?:\s+|$)", last_line)
    for s in reversed(sentences):
        cleaned = s.strip().rstrip(".!?,:;")
        if cleaned:
            return cleaned
    return ""


def is_incomplete(text: str, trailing_block: str | None) -> tuple[bool, str]:
    if trailing_block and trailing_block != "text":
        return True, f"turn ended on {trailing_block} block with no follow-up text"

    if not text:
        return False, ""
    stripped = text.rstrip()
    if len(stripped) < MIN_TEXT_LEN:
        return False, ""

    fence_lines = re.findall(r"(?m)^[ \t]{0,3}```(?!`)", stripped)
    if len(fence_lines) % 2 == 1:
        return True, "unclosed code fence"

    sentence = last_sentence(stripped)
    if sentence and TRAILING_MID_ACTION.search(sentence):
        if not COMPLETION_LEXICAL.search(sentence):
            return True, f"mid-action phrase: {sentence[-100:]!r}"

    return False, ""


def _state_file(session_id: str) -> Path:
    return STATE_DIR / f"{session_id}.count"


def get_counter(session_id: str) -> int:
    try:
        return int(_state_file(session_id).read_text().strip())
    except (OSError, ValueError):
        return 0


def bump_counter(session_id: str) -> int | None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    n = get_counter(session_id) + 1
    try:
        _state_file(session_id).write_text(str(n))
    except OSError:
        return None
    return n


def prune_stale_state() -> None:
    if not STATE_DIR.exists():
        return
    cutoff = time.time() - STATE_TTL_SECONDS
    try:
        for f in STATE_DIR.glob("*.count"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass
    except OSError:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    session_id = payload.get("session_id", "")
    if not session_id or not SESSION_ID_RE.match(session_id):
        return 0

    transcript_path = payload.get("transcript_path", "")

    if get_counter(session_id) >= MAX_NUDGES:
        return 0

    text, trailing = read_last_assistant_entry(transcript_path)
    # Transcript flush race guard: Claude Code writes each content block as its
    # own JSONL entry, and the final text block can land up to a few hundred
    # milliseconds after the Stop event. Retry a few times before trusting a
    # non-text trailing block.
    retries = 0
    while trailing and trailing != "text" and retries < 4:
        time.sleep(0.25)
        text, trailing = read_last_assistant_entry(transcript_path)
        retries += 1
    incomplete, why = is_incomplete(text, trailing)
    if not incomplete:
        return 0

    n = bump_counter(session_id)
    if n is None:
        return 0

    prune_stale_state()
    sys.stderr.write(
        f"Continue — previous turn appears incomplete ({why}). "
        f"Finish the task or explicitly state you are done. "
        f"(nudge {n}/{MAX_NUDGES})\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
