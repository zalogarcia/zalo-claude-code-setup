#!/usr/bin/env python3
"""Tests for memory-index-guard.py. Run: python3 memory-index-guard.test.py"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory-index-guard.py")

ALLOW, BLOCK = 0, 2
passed = failed = 0

# The two real memory index directories on this Mac. Used ONLY as path strings
# in Write payloads, which the hook never reads from disk, so the real files
# are never opened for writing and never modified by this suite.
REAL_DEV = "/Users/zalo/.claude/projects/-Users-zalo-dev/memory/MEMORY.md"
REAL_HOME = "/Users/zalo/.claude/projects/-Users-zalo/memory/MEMORY.md"


def run(payload, raw=False) -> tuple:
    p = subprocess.run(
        [sys.executable, HOOK],
        input=payload if raw else json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stderr


def check(label, payload, expected, expect_in_stderr=None, expect_not_in_stderr=None):
    global passed, failed
    code, err = run(payload)
    ok = code == expected
    why = ""
    if ok and expect_in_stderr and expect_in_stderr not in err:
        ok, why = False, f"stderr missing {expect_in_stderr!r}"
    if ok and expect_not_in_stderr and expect_not_in_stderr in err:
        ok, why = False, f"stderr unexpectedly contains {expect_not_in_stderr!r}"
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}: exit {code} (wanted {expected}) {why}")
        if err:
            print(f"        stderr was: {err[:500]}")


# --------------------------------------------------------------------------
# payload builders (mirror the real harness tool_input shapes)
# --------------------------------------------------------------------------


def write_payload(path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


def edit_payload(path, old, new, replace_all=None):
    ti = {"file_path": path, "old_string": old, "new_string": new}
    if replace_all is not None:
        ti["replace_all"] = replace_all
    return {"tool_name": "Edit", "tool_input": ti}


def multiedit_payload(path, edits):
    return {"tool_name": "MultiEdit", "tool_input": {"file_path": path, "edits": edits}}


# --------------------------------------------------------------------------
# index fixtures
# --------------------------------------------------------------------------

HEADER = "# Memory Index\n\n"


def entry(i, hook="what this memory holds"):
    return f"- [Memory number {i:04d}](memory-{i:04d}.md) - {hook}"


def index_of(n, hook="what this memory holds"):
    """A well formed index with n one line pointers."""
    return HEADER + "\n".join(entry(i, hook) for i in range(n)) + "\n"


def index_of_at_least(target_bytes):
    """Smallest well formed index whose UTF-8 length is >= target_bytes."""
    n = 1
    while len(index_of(n).encode("utf-8")) < target_bytes:
        n += 64
    while n > 1 and len(index_of(n - 1).encode("utf-8")) >= target_bytes:
        n -= 1
    return index_of(n)


def index_of_exactly(target_bytes):
    """A well formed ASCII index of exactly target_bytes, padded on a comment line."""
    per_entry = len(entry(0)) + 1
    n = max(1, (target_bytes - len(HEADER.encode("utf-8")) - 64) // per_entry)
    base = index_of(n)
    pad_needed = target_bytes - len(base.encode("utf-8")) - len("<!-- -->\n")
    assert pad_needed >= 0, "target too small to pad"
    return base + "<!-- " + ("x" * pad_needed) + "-->\n"


# --------------------------------------------------------------------------
# scratch memory dirs that match the guarded glob
# --------------------------------------------------------------------------

TMP = tempfile.mkdtemp(prefix="memory-index-guard-test-")


def guarded_file(slug="-Users-zalo-dev", name="MEMORY.md", content=None):
    d = os.path.join(TMP, "home", ".claude", "projects", slug, "memory")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    if content is not None:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
    return p


def unguarded_file(rel, content=None):
    p = os.path.join(TMP, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if content is not None:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
    return p


print("memory-index-guard tests\n")

SMALL = index_of(20)
OVER = index_of_at_least(21000)
UNDER = index_of_at_least(17000)

print(f"fixtures: small={len(SMALL.encode()):,}B  under={len(UNDER.encode()):,}B  over={len(OVER.encode()):,}B\n")

# --------------------------------------------------------------------------
print("rule 1: total size, measured in BYTES of the RESULT")

p_small = guarded_file(content=SMALL)
check("oversized Write is blocked", write_payload(p_small, OVER), BLOCK, "RULE 1, total size")
check("normal small Write is allowed", write_payload(p_small, SMALL), ALLOW)
check(
    "a small addition to an in-budget index is allowed",
    write_payload(p_small, SMALL + entry(999) + "\n"),
    ALLOW,
)
check(
    "exactly 20,000 bytes is allowed (the budget is 'exceed', not 'reach')",
    write_payload(p_small, index_of_exactly(20000)),
    ALLOW,
)
check(
    "20,001 bytes is blocked",
    write_payload(p_small, index_of_exactly(20001)),
    BLOCK,
    "20,001 bytes",
)

# --------------------------------------------------------------------------
print("\nTHE COMPACTION CASE: an over-budget file being fixed must pass")

# The real 2026-09-21 incident: 24,790 bytes on disk, compacted to 17,140.
fat = index_of_exactly(24790)
lean = index_of_exactly(17140)
p_fat = guarded_file(slug="-Users-zalo-compaction", content=fat)
print(f"  (on disk {len(fat.encode()):,}B, writing {len(lean.encode()):,}B)")
check(
    "24,790B file + 17,140B compacted Write is ALLOWED",
    write_payload(p_fat, lean),
    ALLOW,
)
check(
    "the same over-budget file still blocks a write that stays over",
    write_payload(p_fat, fat),
    BLOCK,
    "ALREADY over budget",
)
# The guard must not have touched the file it was asked about.
assert os.path.getsize(p_fat) == len(fat.encode("utf-8")), "guard modified the file it inspected"
print("  PASS  the guard did not modify the file it inspected")
passed += 1

# --------------------------------------------------------------------------
print("\nrule 2: index line length, measured in CHARACTERS")

long_hook = "x" * 200
long_line_index = HEADER + entry(0, long_hook) + "\n"
check(
    "an index line over 140 chars is blocked",
    write_payload(p_small, long_line_index),
    BLOCK,
    "RULE 2, line length",
)
check(
    "the block names the offending line number and its char count",
    write_payload(p_small, long_line_index),
    BLOCK,
    "line 3,",
)


def line_of_chars(n):
    """An index line of exactly n characters."""
    stem = "- [T](f.md) - "
    return stem + "x" * (n - len(stem))


assert len(line_of_chars(140)) == 140
check(
    "an index line of exactly 140 chars is allowed",
    write_payload(p_small, HEADER + line_of_chars(140) + "\n"),
    ALLOW,
)
check(
    "an index line of 141 chars is blocked",
    write_payload(p_small, HEADER + line_of_chars(141) + "\n"),
    BLOCK,
    "141 chars",
)
check(
    "a long line that is NOT an index line ('- [') is allowed",
    write_payload(p_small, HEADER + "Some prose paragraph " + "y" * 300 + "\n"),
    ALLOW,
)
check(
    "multiple offenders are all named",
    write_payload(p_small, HEADER + line_of_chars(150) + "\n" + line_of_chars(160) + "\n"),
    BLOCK,
    "2 index line(s)",
)

# --------------------------------------------------------------------------
print("\nBYTES vs CHARACTERS are measured separately")

# 6,900 multibyte characters. Under 20,000 CHARACTERS, over 20,000 BYTES.
emoji_body = "\U0001F4AC" * 6900
emoji_index = HEADER + "<!-- " + emoji_body + " -->\n"
assert len(emoji_index) < 20000 < len(emoji_index.encode("utf-8"))
check(
    "a file under 20,000 chars but over 20,000 BYTES is blocked",
    write_payload(p_small, emoji_index),
    BLOCK,
    "RULE 1, total size",
)

# An index line of 100 multibyte characters: over 140 bytes, under 140 chars.
wide_line = "- [T](f.md) - " + "é" * 100
assert len(wide_line) < 140 < len(wide_line.encode("utf-8"))
check(
    "an index line over 140 bytes but under 140 CHARS is allowed",
    write_payload(p_small, HEADER + wide_line + "\n"),
    ALLOW,
)

# --------------------------------------------------------------------------
print("\nEdit computes the RESULT from disk, not from the payload")

p_edit = guarded_file(slug="-Users-zalo-edit", content=UNDER)
check(
    "an Edit whose result is over budget is blocked",
    edit_payload(p_edit, entry(0), entry(0) + "\n" + ("- [pad](p.md) - pad\n" * 200)),
    BLOCK,
    "RULE 1, total size",
)
check(
    "an Edit whose result is under budget is allowed",
    edit_payload(p_edit, entry(0), entry(0, "shorter")),
    ALLOW,
)
check(
    "an Edit that introduces an over-140-char line is blocked",
    edit_payload(p_edit, entry(0), entry(0, "z" * 200)),
    BLOCK,
    "RULE 2, line length",
)
check(
    "an Edit that SHRINKS an already in-budget file is allowed",
    edit_payload(p_edit, HEADER, HEADER),
    ALLOW,
)

# replace_all: every copy is replaced, so the size math must use every copy.
rep_src = HEADER + "\n".join("- [Dup](dup.md) - short" for _ in range(600)) + "\n"
p_rep = guarded_file(slug="-Users-zalo-replaceall", content=rep_src)
check(
    "replace_all that inflates every line is blocked",
    edit_payload(p_rep, "- [Dup](dup.md) - short", "- [Dup](dup.md) - " + "w" * 40, replace_all=True),
    BLOCK,
    "RULE 1, total size",
)
check(
    "replace_all that shortens every line is allowed",
    edit_payload(p_rep, "- [Dup](dup.md) - short", "- [Dup](dup.md) - s", replace_all=True),
    ALLOW,
)
check(
    "without replace_all, an ambiguous multi-match fails OPEN",
    edit_payload(p_rep, "- [Dup](dup.md) - short", "- [Dup](dup.md) - " + "w" * 400),
    ALLOW,
)

print("\nMultiEdit applies its edits in sequence")
p_multi = guarded_file(slug="-Users-zalo-multi", content=UNDER)
check(
    "MultiEdit whose cumulative result is over budget is blocked",
    multiedit_payload(
        p_multi,
        [
            {"old_string": entry(0), "new_string": entry(0) + "\n" + ("- [a](a.md) - a\n" * 150)},
            {"old_string": entry(1), "new_string": entry(1) + "\n" + ("- [b](b.md) - b\n" * 150)},
        ],
    ),
    BLOCK,
    "RULE 1, total size",
)
check(
    "MultiEdit whose result stays under budget is allowed",
    multiedit_payload(
        p_multi,
        [
            {"old_string": entry(0), "new_string": entry(0, "s")},
            {"old_string": entry(1), "new_string": entry(1, "s")},
        ],
    ),
    ALLOW,
)
check(
    "MultiEdit fails OPEN when any one edit cannot be applied",
    multiedit_payload(
        p_multi,
        [
            {"old_string": entry(0), "new_string": entry(0) + "\n" + ("- [a](a.md) - a\n" * 400)},
            {"old_string": "this text is not in the file", "new_string": "x"},
        ],
    ),
    ALLOW,
)

# --------------------------------------------------------------------------
print("\nscope: only */.claude/projects/*/memory/MEMORY.md is guarded")

check(
    "a MEMORY.md OUTSIDE a memory directory is untouched",
    write_payload(unguarded_file("someproject/docs/MEMORY.md"), OVER),
    ALLOW,
)
check(
    "a MEMORY.md in a .claude dir but not under projects/*/memory is untouched",
    write_payload(unguarded_file("home/.claude/MEMORY.md"), OVER),
    ALLOW,
)
check(
    "a NON-MEMORY.md file inside a memory directory is untouched",
    write_payload(guarded_file(name="delta-agents-notes.md"), OVER),
    ALLOW,
)
check(
    "a lowercase memory.md inside a memory directory is untouched",
    write_payload(guarded_file(name="memory.md"), OVER),
    ALLOW,
)
check(
    "an unrelated file entirely is untouched",
    write_payload(unguarded_file("src/index.ts"), OVER),
    ALLOW,
)
check(
    "a relative file_path is resolved against cwd and still guarded",
    {
        "tool_name": "Write",
        "cwd": os.path.join(TMP, "home", ".claude", "projects", "-Users-zalo-dev", "memory"),
        "tool_input": {"file_path": "MEMORY.md", "content": OVER},
    },
    BLOCK,
    "RULE 1, total size",
)

print("\nboth real memory directories on this Mac are recognised")
# Write payloads only: the hook never opens these for writing, so the real
# files are not modified. Content is synthetic and never reaches disk.
check(
    "-Users-zalo-dev is recognised",
    write_payload(REAL_DEV, OVER),
    BLOCK,
    "-Users-zalo-dev/memory/MEMORY.md",
)
check(
    "-Users-zalo is recognised",
    write_payload(REAL_HOME, OVER),
    BLOCK,
    "-Users-zalo/memory/MEMORY.md",
)
check(
    "a tilde path into a real memory dir is expanded and recognised",
    write_payload("~/.claude/projects/-Users-zalo-dev/memory/MEMORY.md", OVER),
    BLOCK,
    "RULE 1, total size",
)

# --------------------------------------------------------------------------
print("\nthe block message is actionable")

check("rule 1 names the budget", write_payload(p_small, OVER), BLOCK, "20,000 byte budget")
check("rule 1 lists the longest lines", write_payload(p_small, OVER), BLOCK, "longest index lines")
check("rule 1 names the file path", write_payload(p_small, OVER), BLOCK, p_small)
check("rule 1 forbids deleting entries", write_payload(p_small, OVER), BLOCK, "Do NOT delete entries")
check("rule 1 explains the pointer rule", write_payload(p_small, OVER), BLOCK, "is a POINTER, not a summary")
check(
    "rule 2 forbids deleting entries",
    write_payload(p_small, HEADER + line_of_chars(200) + "\n"),
    BLOCK,
    "Do NOT delete entries",
)
check(
    "rule 2 quotes the offending line",
    write_payload(p_small, HEADER + line_of_chars(200) + "\n"),
    BLOCK,
    line_of_chars(200),
)
check("the guard names itself", write_payload(p_small, OVER), BLOCK, "BLOCKED (memory-index-guard)")
check(
    "both rules are reported in one message when both trip",
    write_payload(p_small, OVER + line_of_chars(200) + "\n"),
    BLOCK,
    "RULE 2, line length",
    expect_not_in_stderr=None,
)
code, err = run(write_payload(p_small, OVER + line_of_chars(200) + "\n"))
if "RULE 1, total size" in err and "RULE 2, line length" in err:
    passed += 1
    print("  PASS  a doubly-bad write reports rule 1 AND rule 2 together")
else:
    failed += 1
    print("  FAIL  a doubly-bad write did not report both rules")

# --------------------------------------------------------------------------
print("\nfail OPEN on anything this guard cannot compute")

p_missing = os.path.join(TMP, "home", ".claude", "projects", "-Users-zalo-gone", "memory", "MEMORY.md")
check("an Edit against a MISSING file fails open", edit_payload(p_missing, "a", "b" * 40000), ALLOW)
check(
    "an Edit whose old_string is NOT FOUND fails open",
    edit_payload(p_edit, "this string is nowhere in the file", "b" * 40000),
    ALLOW,
)
check(
    "an Edit with an empty old_string fails open",
    edit_payload(p_edit, "", "b" * 40000),
    ALLOW,
)
check(
    "an Edit with a non-string new_string fails open",
    {"tool_name": "Edit", "tool_input": {"file_path": p_edit, "old_string": entry(0), "new_string": 5}},
    ALLOW,
)
check("a Write with non-string content fails open", write_payload(p_small, 12345), ALLOW)
check("a Write with no content key fails open", {"tool_name": "Write", "tool_input": {"file_path": p_small}}, ALLOW)
check("no tool_input fails open", {"tool_name": "Write"}, ALLOW)
check("tool_input is not a dict", {"tool_name": "Write", "tool_input": "nope"}, ALLOW)
check("no file_path fails open", {"tool_name": "Write", "tool_input": {"content": OVER}}, ALLOW)
check("file_path is not a string", {"tool_name": "Write", "tool_input": {"file_path": 7, "content": OVER}}, ALLOW)
check("an empty payload fails open", {}, ALLOW)
check("a non Write/Edit tool is ignored", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, ALLOW)
check("MultiEdit with no edits fails open", multiedit_payload(p_multi, []), ALLOW)
check("MultiEdit edits is not a list", {"tool_name": "MultiEdit", "tool_input": {"file_path": p_multi, "edits": "x"}}, ALLOW)
check(
    "MultiEdit edit entry is not a dict",
    multiedit_payload(p_multi, ["nope"]),
    ALLOW,
)

for label, raw_payload in [
    ("non-JSON stdin", "not json at all {{{"),
    ("empty stdin", ""),
    ("valid JSON that is a bare string", '"just a string"'),
    ("valid JSON that is a list", "[1, 2, 3]"),
    ("valid JSON that is null", "null"),
]:
    code, _ = run(raw_payload, raw=True)
    if code == ALLOW:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}: exit {code} (wanted {ALLOW})")

# --------------------------------------------------------------------------
print("\nan unreadable (binary/undecodable) index fails open")
p_bin = guarded_file(slug="-Users-zalo-binary")
with open(p_bin, "wb") as fh:
    fh.write(b"\xff\xfe\x00\x01 not utf-8 at all \xff")
check("an Edit against an undecodable file fails open", edit_payload(p_bin, "a", "b" * 40000), ALLOW)

# --------------------------------------------------------------------------
# The PostToolUse half (2026-09-22). Every session here runs bypass-permissions
# mode, where the harness tells the model to prefer Bash for file changes, so
# the tool that actually bloats the index is the one the PreToolUse half cannot
# see. This half reads disk after the fact and nudges. It must NEVER block.
print("\nthe PostToolUse audit half")

AUDIT_TMP = tempfile.mkdtemp(prefix="memory-index-audit-test-")


def audit_index(slug, text, age_sec=0):
    d = os.path.join(AUDIT_TMP, slug, "memory")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "MEMORY.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if age_sec:
        old = time.time() - age_sec
        os.utime(path, (old, old))
    return path


def run_audit(glob_pattern):
    env = dict(os.environ, MEMORY_INDEX_GUARD_AUDIT_GLOB=glob_pattern)
    p = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "echo hi"}}),
        capture_output=True, text=True, env=env,
    )
    return p.returncode, p.stdout


def audit_check(label, pattern, want_nudge, must_contain=None):
    global passed, failed
    code, out = run_audit(pattern)
    got_nudge = "memory-index-guard" in out
    ok = code == ALLOW and got_nudge == want_nudge
    why = "" if code == ALLOW else f"exit {code}, wanted {ALLOW}"
    if ok and must_contain and must_contain not in out:
        ok, why = False, f"stdout missing {must_contain!r}"
    if not ok and not why:
        why = f"nudge={got_nudge}, wanted {want_nudge}"
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}: {why}")


GLOB = os.path.join(AUDIT_TMP, "*", "memory", "MEMORY.md")

audit_index("-clean", "- [A](a.md) - short hook\n")
audit_check("a clean index says nothing", GLOB, False)

audit_index("-oversize", "- [A](a.md) - hook\n" + "- [B](b.md) - %s\n" % ("x" * 100) * 1)
audit_index("-oversize", "\n".join("- [M%d](m%d.md) - %s" % (i, i, "x" * 90)
                                    for i in range(400)))
audit_check("a freshly bloated index is named", GLOB, True, must_contain="MEMORY.md")

audit_check("the nudge is not a block", GLOB, True)

audit_index("-stale", "\n".join("- [M%d](m%d.md) - %s" % (i, i, "x" * 90)
                                 for i in range(400)), age_sec=600)
shutil.rmtree(os.path.join(AUDIT_TMP, "-oversize"), ignore_errors=True)
audit_check("an over-budget index nobody just touched stays quiet", GLOB, False)

audit_index("-longline", "- [A](a.md) - " + "y" * 300 + "\n")
audit_check("a single over-long pointer line is caught too", GLOB, True,
            must_contain="140")

shutil.rmtree(AUDIT_TMP, ignore_errors=True)

shutil.rmtree(TMP, ignore_errors=True)

total = passed + failed
print(f"\n{passed}/{total} passed")
sys.exit(1 if failed else 0)
