#!/usr/bin/env python3
"""PreToolUse guard for the memory INDEX file (MEMORY.md).

Why this exists
---------------
`~/.claude/projects/<slug>/memory/MEMORY.md` is the memory INDEX. It is loaded
into every session in that project, and the loader has a read ceiling of
roughly 24.4 KB. Past that, every future session silently loses the TAIL of the
index and never knows it happened: no error, no warning, just memories that
stop being recalled.

`-Users-zalo-dev/memory/MEMORY.md` crossed that ceiling on 2026-09-21 at 24,790
bytes, and a worker spent a run compacting it back down to 17,140. It did not
get there in one bad commit. It got there one line at a time, each session
saving a memory at the end of a long run and dumping shas, dates, criterion
numbers and multi clause findings into what is supposed to be a one line
POINTER.

The prose rule already existed in ~/.claude/CLAUDE.md ("one line per memory, no
frontmatter, never put memory content there") and it did not hold, because
prose compliance decays under momentum. That is the whole case for a mechanism:
per the Self-Learning Protocol, a class of mistake a hook can catch
deterministically gets a hook, not another sentence.

What it BLOCKS
--------------
1. A write whose RESULTING file would exceed 20,000 BYTES (UTF-8).
2. A write whose RESULTING file would contain an index line (one starting
   "- [") longer than 140 CHARACTERS.

Note which unit is which: the file budget is measured in bytes because the read
ceiling is a byte ceiling, and the line budget is measured in characters
because it is a readability budget. Mixing the two is the easy bug here.

The check is always on the RESULT, never on the current state on disk. That is
deliberate and load bearing: when the file is already 24 KB and a session
writes a compacted 17 KB version, that write is exactly the fix we want and
must be allowed. A naive "is MEMORY.md over budget" check would block the fix
and trap the file over the ceiling permanently.

What it ALLOWS
--------------
Every file that is not a memory index (the glob is
`*/.claude/projects/*/memory/MEMORY.md`, so a MEMORY.md anywhere else and any
other file inside a memory directory both pass straight through), every write
whose result is within both budgets, and anything at all whose result this hook
cannot compute with certainty.

That last one matters. This is a hygiene guard, not a security guard. The cost
of a false block is a session losing the memory it was trying to save; the cost
of a missed oversized line is one long line in an index. So it fails OPEN on
every internal error: a malformed payload, a file it cannot read, an
`old_string` it cannot locate, an ambiguous match, a unicode surprise. It
allows and says nothing.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import fnmatch
import glob
import json
import os
import sys
import time

# The file budget, in BYTES of UTF-8, because the read ceiling (~24.4 KB) that
# this exists to stay under is a byte ceiling. 20,000 leaves ~4.4 KB of margin.
MAX_INDEX_BYTES = 20000

# The per line budget, in CHARACTERS, because this one is about readability of
# a pointer. Deliberately generous: after the 2026-09-21 compaction the longest
# real hook line in the index was 55 characters.
MAX_INDEX_LINE_CHARS = 140

# Memory index files, wherever they live. There is more than one project memory
# directory on this Mac, so this globs rather than naming one.
GUARDED_GLOB = "*/.claude/projects/*/memory/MEMORY.md"

# An index entry is a markdown bullet with a link: "- [Title](file.md) - hook".
INDEX_LINE_PREFIX = "- ["

# How many of the longest index lines to name when the file is over budget.
LONGEST_SHOWN = 10

NEVER_DELETE = (
    "Do NOT delete entries and do NOT merge two memories into one line to get "
    "under the limit. An index that shrank by losing entries is worse than an "
    "oversized one: the oversized file at least still names every memory, and "
    "a dropped pointer is a memory nothing will ever recall again. Shorten the "
    "hooks of existing lines instead."
)

POINTER_RULE = (
    "The text after the dash on an index line is a POINTER, not a summary. It "
    "exists so a future session can decide whether to open the linked file. "
    "Shas, dates, byte counts, criterion numbers, file paths and multi clause "
    "findings belong in the linked memory file, not here."
)


def guarded_path(raw_path, cwd):
    """Absolute path if this write targets a memory index, else None."""
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = os.path.expanduser(raw_path)
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    path = os.path.normpath(path)
    if os.path.basename(path) != "MEMORY.md":
        return None
    if not fnmatch.fnmatch(path, GUARDED_GLOB):
        return None
    return path


def apply_replacement(text, old, new, replace_all):
    """The Edit harness's own semantics. None means "cannot compute" -> allow."""
    if not isinstance(old, str) or not isinstance(new, str):
        return None
    if old == "":
        # Empty old_string is create/prepend semantics; do not guess at it.
        return None
    count = text.count(old)
    if count == 0:
        return None  # old_string not present: the harness will reject this anyway
    if count > 1 and not replace_all:
        return None  # ambiguous match: the harness will reject this anyway
    if replace_all:
        return text.replace(old, new)
    return text.replace(old, new, 1)


def resulting_text(tool_name, tool_input, path):
    """The file's content AFTER this call, or None if it cannot be computed.

    A Write carries the whole new content, so the result is just that string.
    An Edit carries only old_string/new_string, so the current file has to be
    read from disk and the replacement applied here to know the result.
    """
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None

    if tool_name not in ("Edit", "MultiEdit"):
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return None  # missing or unreadable file: fail open

    if tool_name == "Edit":
        return apply_replacement(
            text,
            tool_input.get("old_string"),
            tool_input.get("new_string"),
            bool(tool_input.get("replace_all")),
        )

    edits = tool_input.get("edits")
    if not isinstance(edits, list) or not edits:
        return None
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        text = apply_replacement(
            text,
            edit.get("old_string"),
            edit.get("new_string"),
            bool(edit.get("replace_all")),
        )
        if text is None:
            return None
    return text


def index_lines(text):
    """(line number, character length, line) for every index entry."""
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith(INDEX_LINE_PREFIX):
            out.append((number, len(line), line))
    return out


def current_size_bytes(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return None


def size_block(path, result_bytes, entries):
    over = result_bytes - MAX_INDEX_BYTES
    lines = [
        f"RULE 1, total size: the resulting {os.path.basename(path)} would be "
        f"{result_bytes:,} bytes, which is {over:,} over the "
        f"{MAX_INDEX_BYTES:,} byte budget.",
        "",
        f"  file:  {path}",
    ]
    now = current_size_bytes(path)
    if now is not None:
        lines.append(f"  on disk now: {now:,} bytes")
    lines += [
        "",
        "This index is loaded into every session in this project. Past roughly",
        "24.4 KB the loader truncates it and every future session silently loses",
        "the TAIL of the index, with no error and no warning. 20,000 bytes is",
        "that ceiling with margin.",
        "",
    ]

    if entries:
        longest = sorted(entries, key=lambda e: e[1], reverse=True)[:LONGEST_SHOWN]
        lines.append(f"The {len(longest)} longest index lines, shorten these first:")
        for number, chars, line in longest:
            lines.append(f"  {chars:>4} chars  line {number:>4}  {line}")
        lines.append("")
    else:
        lines.append("No index lines ('- [') were found, so the bulk is elsewhere in the file.")
        lines.append("")

    lines += [POINTER_RULE, "", NEVER_DELETE]

    if now is not None and now > MAX_INDEX_BYTES:
        lines += [
            "",
            f"Note: this file is ALREADY over budget at {now:,} bytes, so there is",
            "no incremental path down. The write that unblocks it has to land under",
            f"{MAX_INDEX_BYTES:,} bytes in one pass. Read the whole file, shorten every",
            "hook to a few words, and Write the whole compacted index back.",
        ]
    return "\n".join(lines)


def line_block(long_lines):
    lines = [
        f"RULE 2, line length: {len(long_lines)} index line(s) in the resulting "
        f"file exceed the {MAX_INDEX_LINE_CHARS} character budget.",
        "",
    ]
    for number, chars, line in long_lines:
        lines.append(f"  line {number}, {chars} chars:")
        lines.append(f"    {line}")
    lines += [
        "",
        "An index line is one line: '- [Title](file.md) - hook'.",
        "",
        POINTER_RULE,
        "",
        NEVER_DELETE,
    ]
    return "\n".join(lines)


# Where the audit half looks. Overridable ONLY so the suite can point it at a
# temp tree; there is no reason to set it in a real session.
AUDIT_GLOB = "~/.claude/projects/*/memory/MEMORY.md"

TOUCHED_WINDOW_SEC = 90


def audit_indexes_on_disk(now=None):
    """Every memory index on disk that is over budget AND was just written.

    The PreToolUse half of this guard only sees Write/Edit/MultiEdit. Every
    session here runs in bypass-permissions mode, where the harness tells the
    model to prefer Bash for file changes (cat, sed, heredocs), so the tool
    that actually causes index bloat is the one tool the guard could not see.
    Measured 2026-09-22: `-Users-zalo/memory/MEMORY.md` reached 41,550 bytes
    with all 79 pointer lines over the limit, roughly the bottom 40% of the
    index silently unread in every home-rooted session, while the guard sat
    registered and blind.

    The mtime window is what keeps this from nagging. A file that is over
    budget but was not touched by the command that just ran is somebody else's
    problem to fix, and repeating it on every Bash call would train the reader
    to skip it. Firing at the moment of the bloat is the whole point.
    """
    now = time.time() if now is None else now
    pattern = os.environ.get("MEMORY_INDEX_GUARD_AUDIT_GLOB") or AUDIT_GLOB
    findings = []
    for path in sorted(glob.glob(os.path.expanduser(pattern))):
        try:
            if now - os.path.getmtime(path) > TOUCHED_WINDOW_SEC:
                continue
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        entries = index_lines(text)
        size = len(text.encode("utf-8"))
        long_lines = [e for e in entries if e[1] > MAX_INDEX_LINE_CHARS]
        if size > MAX_INDEX_BYTES or long_lines:
            findings.append((path, size, entries, long_lines))
    return findings


def audit_nudge(findings):
    blocks = [
        "memory-index-guard: a command just left a memory INDEX over budget. "
        "This is the PostToolUse half of the guard, so the write has already "
        "landed and nothing was blocked. Compact it now, in this turn.",
    ]
    for path, size, entries, long_lines in findings:
        blocks.append("")
        if size > MAX_INDEX_BYTES:
            blocks.append(size_block(path, size, entries))
        if long_lines:
            blocks.append(line_block(long_lines))
    blocks += [
        "",
        "The index is loaded whole into every session in that project and the "
        "loader truncates silently, so an over-budget index is memories that "
        "stop being recalled with no error. One line per memory, pointing at "
        "the file, never carrying its content.",
    ]
    return "\n".join(blocks)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # never block on a payload we cannot read

    # Valid JSON that is not an object (a bare string/list/null) must allow,
    # not crash: .get() on a str raises and would exit non-zero.
    if not isinstance(payload, dict):
        return 0

    # PostToolUse: the write already happened, so this half never blocks. It
    # reads what is on disk and nudges. Routed by EVENT, not by tool name, so
    # registering it on any matcher behaves the same way.
    if payload.get("hook_event_name") == "PostToolUse":
        findings = audit_indexes_on_disk()
        if findings:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": audit_nudge(findings),
            }}))
        return 0

    tool_name = payload.get("tool_name")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    path = guarded_path(tool_input.get("file_path"), payload.get("cwd"))
    if path is None:
        return 0  # not a memory index: pass straight through

    result = resulting_text(tool_name, tool_input, path)
    if result is None:
        return 0  # could not compute the result: fail open

    # BYTES for the file budget, CHARACTERS for the line budget.
    result_bytes = len(result.encode("utf-8"))
    entries = index_lines(result)
    long_lines = [e for e in entries if e[1] > MAX_INDEX_LINE_CHARS]

    over_size = result_bytes > MAX_INDEX_BYTES
    if not over_size and not long_lines:
        return 0

    blocks = ["BLOCKED (memory-index-guard): this write would leave the memory index over budget.", ""]
    if over_size:
        blocks.append(size_block(path, result_bytes, entries))
    if long_lines:
        if over_size:
            blocks.append("")
        blocks.append(line_block(long_lines))
    blocks += [
        "",
        "Fix the index content and write it again. There is no in-band override; "
        "do not route around this guard by writing the file some other way.",
    ]
    print("\n".join(blocks), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
