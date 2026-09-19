#!/usr/bin/env python3
"""PostToolUse (Write|Edit|MultiEdit) — catch em/en dashes AT WRITE TIME in
sessions whose brief bans them.

Why this exists (14-day audit 2026-08-28, P7; 14 events across 14 sessions)
--------------------------------------------------------------------------
Zalo's copy bans em and en dashes on every channel. Briefs say so explicitly
and usually ship the grep command to check with. Claude authored them anyway
in 14 sessions and paid a late cleanup pass plus gate re-runs each time
(c4707086: 21 hits, e330fa79: 29, 86ab213d: 18 ...), and in 1e7aa4c7 **21 em
dashes shipped in the delivered report, uncaught** — that surface had no lint.

Detection is trivially mechanical; the TIMING is the whole problem. A grep at
the end of a run finds what a hook at the moment of writing could have
prevented. Generation-time compliance decays over a long session; a hook does
not.

Scope, deliberately narrow
--------------------------
- Fires ONLY when the session's own brief bans the dashes (first user messages
  matched against BAN_RE). A session without the ban is untouched — this hook
  has zero effect on ordinary work.
- Fires ONLY on copy/deliverable file types (COPY_EXTS). Source code
  legitimately contains dashes in comments and strings, and blocking those
  would make the hook a nuisance that gets unwired.
- Judges only the text being ADDED (Write.content, Edit.new_string,
  MultiEdit.edits[].new_string), never pre-existing file content, so it never
  re-flags a dash somebody else wrote.

Exit 2 + stderr on a violation (the write has already happened; stderr is the
channel that reaches the model so it fixes the text immediately). Exit 0 in
every other case, including every error.

Tests: python3 ~/.claude/hooks/emdash-guard.test.py
"""

import json
import os
import re
import sys
import tempfile

# U+2012 figure dash, U+2013 en dash, U+2014 em dash, U+2015 horizontal bar.
DASHES = "‒–—―"
DASH_RE = re.compile("[" + DASHES + "]")
DASH_NAMES = {
    "‒": "figure dash U+2012",
    "–": "en dash U+2013",
    "—": "em dash U+2014",
    "―": "horizontal bar U+2015",
}

# The standard brief phrasing, plus the variants seen in real briefs.
BAN_RE = re.compile(
    r"no\s+em[\s\-]?\s?dash"
    r"|no\s+em\s+or\s+en[\s\-]?\s?dash"
    r"|zero\s+em[\s\-]?\s?dash"
    r"|without\s+em[\s\-]?\s?dash"
    r"|em[\s\-]?\s?dashes?\s+(?:are\s+)?(?:banned|forbidden|prohibited|not\s+allowed)"
    r"|(?:ban|avoid|remove|strip)\s+(?:all\s+)?em[\s\-]?\s?dash",
    re.I,
)

COPY_EXTS = (
    ".md", ".markdown", ".mdx", ".txt", ".srt", ".vtt", ".csv", ".tsv",
    ".html", ".htm", ".json", ".yaml", ".yml", ".rtf",
)

# The brief always sits in the first few user turns; never read a whole
# multi-megabyte transcript for this.
TRANSCRIPT_HEAD_BYTES = 512 * 1024
MAX_USER_TURNS = 6
MAX_REPORTED_LINES = 12

STATE_DIR = os.environ.get("EMDASH_GUARD_STATE_DIR") or os.path.join(
    tempfile.gettempdir(), "claude-emdash-guard-%d" % os.getuid()
)


def _text_of(content):
    """Flatten a transcript message's content to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                out.append(block["text"])
        return "\n".join(out)
    return ""


def brief_bans_dashes(transcript_path):
    """True when this session's opening user turns ban em/en dashes."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return False
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            head = f.read(TRANSCRIPT_HEAD_BYTES)
    except OSError:
        return False
    seen = 0
    for line in head.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # a truncated final line is expected; keep going
        if not isinstance(rec, dict) or rec.get("type") != "user":
            continue
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        text = _text_of(msg.get("content"))
        if not text.strip():
            continue
        seen += 1
        if BAN_RE.search(text):
            return True
        if seen >= MAX_USER_TURNS:
            break
    return False


def added_text(tool_name, tool_input):
    """Only the text this call ADDS — never the file's prior content."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Write":
        c = tool_input.get("content")
        return c if isinstance(c, str) else ""
    if tool_name == "Edit":
        c = tool_input.get("new_string")
        return c if isinstance(c, str) else ""
    if tool_name == "MultiEdit":
        parts = []
        for e in tool_input.get("edits") or []:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                parts.append(e["new_string"])
        return "\n".join(parts)
    return ""


def offending_lines(text):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if DASH_RE.search(line):
            found = sorted({DASH_NAMES.get(ch, ch) for ch in line if ch in DASHES})
            hits.append((i, line.strip()[:160], ", ".join(found)))
    return hits


def _cached_verdict(session_id, transcript_path):
    """Parse the transcript once per session, not once per Edit."""
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or "")) or "unknown"
    path = os.path.join(STATE_DIR, sid + ".json")
    try:
        with open(path) as f:
            cached = json.load(f)
        if isinstance(cached, dict) and isinstance(cached.get("banned"), bool):
            return cached["banned"]
    except Exception:
        pass
    banned = brief_bans_dashes(transcript_path)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=STATE_DIR, prefix=".eg-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"banned": banned}, f)
        os.replace(tmp, path)
    except Exception:
        pass
    return banned


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    payload = json.loads(raw)
    tool = payload.get("tool_name")
    if tool not in ("Write", "Edit", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input")
    file_path = ""
    if isinstance(tool_input, dict):
        fp = tool_input.get("file_path")
        file_path = fp if isinstance(fp, str) else ""
    if not file_path.lower().endswith(COPY_EXTS):
        return 0

    text = added_text(tool, tool_input)
    if not text or not DASH_RE.search(text):
        return 0

    if not _cached_verdict(payload.get("session_id"), payload.get("transcript_path")):
        return 0

    hits = offending_lines(text)
    shown = hits[:MAX_REPORTED_LINES]
    more = len(hits) - len(shown)
    lines = "\n".join(f"  line {n} [{kinds}]: {body}" for n, body, kinds in shown)
    if more > 0:
        lines += f"\n  ... and {more} more line(s)"
    print(
        "EM-DASH GATE (emdash-guard): this session's brief bans em/en dashes, "
        f"and the text just written to {file_path} contains "
        f"{len(hits)} offending line(s):\n{lines}\n"
        "Rewrite them NOW, in this turn, before moving on. Use a comma, a "
        "colon, a period, or parentheses. Do not defer this to a cleanup grep "
        "at the end of the run: that is exactly the pattern that shipped 21 "
        "uncaught em dashes in a delivered report (audit 2026-08-28, P7).",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    # Fail-open on anything unexpected: a formatting lint must never wedge a
    # session.
    try:
        code = main()
    except BaseException:
        code = 0
    sys.exit(code if code in (0, 2) else 0)
