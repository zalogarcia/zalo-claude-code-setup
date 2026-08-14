#!/usr/bin/env python3
"""Tests for gather-transcripts.py — run: python3 ~/.claude/scripts/gather-transcripts.test.py

The case that matters is TEST 1: a transcript whose conversation ended days ago but whose
mtime is fresh (metadata-only append) must be DROPPED. That is the bug this script exists
to kill, and it is the one a future refactor is most likely to reintroduce.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "gather-transcripts.py")

spec = importlib.util.spec_from_file_location("gt", SCRIPT)
gt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gt)

passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n         got:  {got!r}\n         want: {want!r}")


def rec(ts, text="hello"):
    return json.dumps({"timestamp": ts, "type": "user", "message": text}) + "\n"


def meta():
    """A metadata-only append — no timestamp. This is what freshens mtime."""
    return json.dumps({"type": "custom-title", "value": "some session"}) + "\n"


def write(root, relpath, body, mtime=None):
    full = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(body)
    if mtime:
        os.utime(full, (mtime, mtime))
    return full


def run(root, since, extra=None):
    out = subprocess.run(
        [sys.executable, SCRIPT, "--since", since, "--root", root, "--json"] + (extra or []),
        capture_output=True, text=True,
    )
    return out, json.loads(out.stdout) if out.stdout.strip() else None


def kept_names(payload):
    return sorted(os.path.basename(r["path"]) for r in payload["kept"])


def dropped_names(payload):
    return sorted(os.path.basename(r["path"]) for r in payload["dropped"])


WATERMARK = "2026-08-02T07:00:00Z"
NOW = time.time()

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 1 — the regression that caused this script (stale content, fresh mtime)")
    # Conversation ended 2026-08-01, then a metadata line freshened the mtime to now.
    write(root, "proj-a/stale.jsonl",
          rec("2026-08-01T20:16:50Z") * 50 + meta(), mtime=NOW)
    write(root, "proj-a/live.jsonl",
          rec("2026-08-02T15:00:00Z") * 50 + meta(), mtime=NOW)
    out, p = run(root, WATERMARK)
    check("stale transcript dropped despite fresh mtime", dropped_names(p), ["stale.jsonl"])
    check("in-window transcript kept", kept_names(p), ["live.jsonl"])
    check("drop reason is content-based", p["dropped"][0]["reason"],
          "newest real record predates watermark")
    check("true span reported, not mtime", p["dropped"][0]["last"], "2026-08-01T20:16:50Z")

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 2 — watermark boundary is inclusive")
    write(root, "p/exact.jsonl", rec(WATERMARK), mtime=NOW)
    write(root, "p/onesec-before.jsonl", rec("2026-08-02T06:59:59Z"), mtime=NOW)
    out, p = run(root, WATERMARK)
    check("record exactly at watermark is kept", kept_names(p), ["exact.jsonl"])
    check("record one second before is dropped", dropped_names(p), ["onesec-before.jsonl"])

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 3 — files with no timestamped record at all")
    write(root, "p/metaonly.jsonl", meta() * 20, mtime=NOW)
    out, p = run(root, WATERMARK)
    check("metadata-only file dropped", dropped_names(p), ["metaonly.jsonl"])
    check("reason names the cause", p["dropped"][0]["reason"], "no timestamped record")

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 4 — large file (tail-scan path, >512KB)")
    # Pad past TAIL_BYTES so probe() takes the seek path rather than reading it whole.
    pad = rec("2026-07-01T00:00:00Z", "x" * 500)
    n = (gt.TAIL_BYTES // len(pad)) + 200
    write(root, "p/big-stale.jsonl", pad * n + meta(), mtime=NOW)
    write(root, "p/big-live.jsonl", pad * n + rec("2026-08-02T12:00:00Z") + meta(), mtime=NOW)
    out, p = run(root, WATERMARK)
    check("large stale file dropped via tail scan", dropped_names(p), ["big-stale.jsonl"])
    check("large live file kept via tail scan", kept_names(p), ["big-live.jsonl"])
    check("first_record found from head, not tail", p["kept"][0]["first"], "2026-07-01T00:00:00Z")

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 5 — full-scan fallback when the tail holds no timestamp")
    # A real record early, then enough metadata-only padding to swamp the whole tail window.
    body = rec("2026-08-02T09:00:00Z") + (meta() * ((gt.TAIL_BYTES // len(meta())) + 500))
    write(root, "p/buried.jsonl", body, mtime=NOW)
    out, p = run(root, WATERMARK)
    check("in-window record buried under metadata is still found", kept_names(p), ["buried.jsonl"])

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 6 — noise directories and size floor")
    write(root, "p/subagents/x.jsonl", rec("2026-08-02T15:00:00Z"), mtime=NOW)
    write(root, "p/workflows/y.jsonl", rec("2026-08-02T15:00:00Z"), mtime=NOW)
    write(root, "p/real.jsonl", rec("2026-08-02T15:00:00Z"), mtime=NOW)
    write(root, "p/notjson.txt", rec("2026-08-02T15:00:00Z"), mtime=NOW)
    out, p = run(root, WATERMARK)
    check("subagents/ and workflows/ excluded", kept_names(p) + dropped_names(p), ["real.jsonl"])

    big = rec("2026-08-02T15:00:00Z", "y" * 2000)
    write(root, "p/large-enough.jsonl", big, mtime=NOW)
    out, p = run(root, WATERMARK, extra=["--min-size", "1000"])
    check("--min-size filters small files", kept_names(p), ["large-enough.jsonl"])

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 7 — in-window record counting")
    write(root, "p/mixed.jsonl",
          rec("2026-08-01T10:00:00Z") * 5 + rec("2026-08-02T10:00:00Z") * 3, mtime=NOW)
    out, p = run(root, WATERMARK)
    check("counts only in-window records", p["kept"][0]["in_window"], 3)

with tempfile.TemporaryDirectory() as root:
    print("\nTEST 8 — argument handling")
    out, _ = run(root, "not-a-date")
    check("bad --since exits 2", out.returncode, 2)
    out = subprocess.run([sys.executable, SCRIPT, "--since", WATERMARK, "--root", "/nope/nope"],
                         capture_output=True, text=True)
    check("missing --root exits 2", out.returncode, 2)
    out, p = run(root, WATERMARK)
    check("empty root exits 0", out.returncode, 0)
    check("empty root keeps nothing", kept_names(p), [])

print("\nTEST 9 — timestamp parsing")
check("Z suffix", gt.parse_iso("2026-08-02T07:00:00Z").isoformat(), "2026-08-02T07:00:00+00:00")
check("offset form", gt.parse_iso("2026-08-02T03:00:00-04:00").isoformat(), "2026-08-02T07:00:00+00:00")
check("naive treated as UTC", gt.parse_iso("2026-08-02T07:00:00").isoformat(), "2026-08-02T07:00:00+00:00")
check("millis", gt.parse_iso("2026-08-02T07:00:00.123Z").isoformat(), "2026-08-02T07:00:00.123000+00:00")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
