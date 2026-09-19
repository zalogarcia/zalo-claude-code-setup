#!/usr/bin/env python3
"""Behaviour suite for emdash-guard.

Run: python3 ~/.claude/hooks/emdash-guard.test.py
Green before wiring. Exit 2 is the "flag it" signal; exit 0 is silence.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.path.expanduser("~/.claude/hooks/emdash-guard.py")
EM = "—"
EN = "–"
FLAG, QUIET = True, False

_dirs = []


def workdir():
    d = tempfile.mkdtemp(prefix="emdash-guard-test-")
    _dirs.append(d)
    return d


def transcript(d, user_texts, name="t.jsonl", broken=False):
    """Write a fake session transcript with the given opening user turns."""
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        for t in user_texts:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": t}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"role": "assistant",
                                                                 "content": [{"type": "text", "text": "ok"}]}}) + "\n")
        if broken:
            f.write('{"type": "user", "message": {"conte')  # truncated tail
    return p


def run(payload, state_dir, raw=None):
    data = raw if raw is not None else json.dumps(payload)
    p = subprocess.run(
        ["python3", HOOK],
        input=data,
        capture_output=True,
        text=True,
        env=dict(os.environ, EMDASH_GUARD_STATE_DIR=state_dir),
    )
    assert p.returncode in (0, 2), f"unexpected exit {p.returncode}: {p.stderr}"
    return p.returncode == 2, p.stderr


def write_payload(file_path, content, transcript_path, session="s1"):
    return {
        "session_id": session,
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
        "transcript_path": transcript_path,
        "cwd": "/tmp",
    }


BAN = "Write the reel captions. NO EM DASHES anywhere in the copy."
BAN_HYPHEN = "Formatting rules: no em-dashes, no en dashes, plain punctuation only."
BAN_SENTENCE = "Em dashes are banned in every deliverable."
NO_BAN = "Write the reel captions in Zalo's voice. Keep it short."

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS | {label}")
    else:
        failed += 1
        print(f"FAIL | {label}")


def main():
    # --- FLAG: the ban is in the brief and an em dash was written -------------
    d = workdir()
    t = transcript(d, [BAN])
    fired, err = run(write_payload("/tmp/copy.md", f"Hook line {EM} then the payoff.", t), workdir())
    check("1a: ban + em dash in a .md flags", fired)
    check("1b: message names the file and the line", "/tmp/copy.md" in err and "line 1" in err)
    check("1c: message names the character", "U+2014" in err)

    d = workdir()
    fired, _ = run(write_payload("/tmp/c.md", f"range 3{EN}5 units", transcript(d, [BAN_HYPHEN])), workdir())
    check("2: 'no em-dashes' phrasing + en dash flags", fired)

    d = workdir()
    fired, _ = run(write_payload("/tmp/c.md", f"a {EM} b", transcript(d, [BAN_SENTENCE])), workdir())
    check("3: 'em dashes are banned' phrasing flags", fired)

    d = workdir()
    t = transcript(d, ["Here is the job.", "Second turn.", BAN])
    fired, _ = run(write_payload("/tmp/c.md", f"a {EM} b", t), workdir())
    check("4: ban stated in a later opening turn still flags", fired)

    # --- QUIET: no ban in the brief ------------------------------------------
    d = workdir()
    fired, _ = run(write_payload("/tmp/c.md", f"a {EM} b", transcript(d, [NO_BAN])), workdir())
    check("5: no ban in the brief stays silent (zero effect on normal work)", not fired)

    # --- QUIET: ban present but nothing to flag ------------------------------
    d = workdir()
    t = transcript(d, [BAN])
    fired, _ = run(write_payload("/tmp/c.md", "Clean copy, commas only.", t), workdir())
    check("6: clean copy stays silent", not fired)

    d = workdir()
    t = transcript(d, [BAN])
    fired, _ = run(write_payload("/tmp/c.md", "hyphen-joined words and minus 3 - 2", t), workdir())
    check("7: plain ASCII hyphens are not em dashes", not fired)

    # --- SCOPE: source code is exempt ----------------------------------------
    d = workdir()
    t = transcript(d, [BAN])
    sd = workdir()
    for ext in (".py", ".ts", ".tsx", ".js", ".sh", ".css"):
        fired, _ = run(write_payload(f"/tmp/x{ext}", f"# comment {EM} note", t), sd)
        if fired:
            check(f"8: source file {ext} is exempt", False)
            break
    else:
        check("8: source files (.py/.ts/.tsx/.js/.sh/.css) are exempt", True)

    # --- SCOPE: only ADDED text is judged ------------------------------------
    d = workdir()
    t = transcript(d, [BAN])
    edit = {
        "session_id": "s1", "tool_name": "Edit", "transcript_path": t,
        "tool_input": {"file_path": "/tmp/c.md",
                       "old_string": f"pre-existing {EM} dash",
                       "new_string": "clean replacement"},
    }
    fired, _ = run(edit, workdir())
    check("9: an em dash in old_string only is not flagged", not fired)

    multi = {
        "session_id": "s1", "tool_name": "MultiEdit", "transcript_path": t,
        "tool_input": {"file_path": "/tmp/c.md",
                       "edits": [{"old_string": "a", "new_string": "clean"},
                                 {"old_string": "b", "new_string": f"bad {EM} here"}]},
    }
    fired, _ = run(multi, workdir())
    check("10: MultiEdit flags a dash in any new_string", fired)

    # --- caching: verdict is reused, and a stale cache is honoured -----------
    sd = workdir()
    d = workdir()
    t = transcript(d, [BAN])
    run(write_payload("/tmp/c.md", f"a {EM} b", t), sd)
    os.remove(t)  # transcript gone; the cached verdict must still apply
    fired, _ = run(write_payload("/tmp/c.md", f"a {EM} b", t), sd)
    check("11: verdict is cached per session (survives an unreadable transcript)", fired)

    # --- MALFORMED input: exit 0, silent ------------------------------------
    sd = workdir()
    d = workdir()
    t = transcript(d, [BAN])
    bad = [
        ("unparseable JSON", None, '{"broken":'),
        ("empty stdin", None, ""),
        ("top-level list", None, "[1,2,3]"),
        ("no tool_name", {"tool_input": {"file_path": "/tmp/c.md", "content": EM}}, None),
        ("wrong tool", {"tool_name": "Bash", "tool_input": {"command": EM}}, None),
        ("tool_input is null", {"tool_name": "Write", "tool_input": None}, None),
        ("file_path is a dict", {"tool_name": "Write",
                                 "tool_input": {"file_path": {"a": 1}, "content": EM}}, None),
        ("content is a list", {"tool_name": "Write", "transcript_path": t,
                               "tool_input": {"file_path": "/tmp/c.md", "content": [EM]}}, None),
        ("edits is not a list", {"tool_name": "MultiEdit", "transcript_path": t,
                                 "tool_input": {"file_path": "/tmp/c.md", "edits": "nope"}}, None),
        ("transcript_path missing", {"tool_name": "Write", "session_id": "zz",
                                     "tool_input": {"file_path": "/tmp/c.md", "content": EM}}, None),
        ("transcript_path points nowhere", {"tool_name": "Write", "session_id": "zy",
                                            "transcript_path": "/tmp/does-not-exist-9x.jsonl",
                                            "tool_input": {"file_path": "/tmp/c.md", "content": EM}}, None),
    ]
    ok = True
    for label, pl, raw in bad:
        try:
            fired, _ = run(pl, workdir(), raw=raw)
        except AssertionError as e:
            print(f"FAIL | malformed: {label} — {e}")
            ok = False
            continue
        if fired:
            print(f"FAIL | malformed: {label} — expected silence")
            ok = False
    check("12: every malformed payload exits 0 and stays silent", ok)

    # a corrupt transcript (truncated final line) must not crash the parse
    d = workdir()
    t = transcript(d, [BAN], broken=True)
    fired, _ = run(write_payload("/tmp/c.md", f"a {EM} b", t), workdir())
    check("13: corrupt transcript tail still parses the ban", fired)

    # a transcript that is not JSONL at all
    d = workdir()
    p = os.path.join(d, "junk.jsonl")
    open(p, "w").write("this is not json at all\nnor is this\n")
    fired, _ = run(write_payload("/tmp/c.md", f"a {EM} b", p), workdir())
    check("14: non-JSONL transcript is treated as 'no ban'", not fired)

    for x in _dirs:
        shutil.rmtree(x, ignore_errors=True)
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
