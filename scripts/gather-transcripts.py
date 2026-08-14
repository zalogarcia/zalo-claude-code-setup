#!/usr/bin/env python3
"""Gather Claude Code transcripts whose REAL CONTENT falls inside a sync window.

Why this exists
---------------
The obvious gather step is `find ~/.claude/projects -name '*.jsonl' -newermt "<WATERMARK>"`,
which selects by **mtime**. A transcript's mtime does not bound its content: Claude Code
appends metadata-only lines (`last-prompt`, `custom-title`, `mode`, `permission-mode`) that
carry no timestamp, so a session whose conversation ended days ago gets a fresh mtime and
enters the window looking substantive.

Measured 2026-08-03: three of six memory-sync cluster agents spent their whole budget
proving their assigned window was empty — including a 92MB transcript briefed as "the
richest source in the window" whose last real record was two days before the watermark.

mtime never *under*-selects (a file with in-window records always has an in-window mtime),
so the fix is a cheap post-filter: keep a candidate only if its newest real record
timestamp is at or after the watermark.

Usage
-----
    gather-transcripts.py --since 2026-08-02T07:00:00Z
    gather-transcripts.py --since 2026-08-02T07:00:00Z --json
    gather-transcripts.py --since 2026-08-02T07:00:00Z --min-size 50000 --show-dropped

Output (TSV, one row per surviving transcript, largest in-window record count first):
    path  size_bytes  first_record  last_record  in_window_records

Exit codes: 0 = ran (even if nothing survived), 2 = bad arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# Matching the raw bytes beats json.loads() per line: these files reach 90MB+ and we only
# ever need one field. Tolerates the trailing-comma/whitespace variations in the format.
TS_RE = re.compile(rb'"timestamp"\s*:\s*"([^"]+)"')

# How much of the tail to read when looking for the last real record. The metadata lines
# that cause the bug are short and few, so the newest timestamped record sits well within
# this; if it doesn't, we fall back to a full scan rather than guess.
TAIL_BYTES = 512 * 1024
HEAD_BYTES = 64 * 1024

EXCLUDE_DIR_RE = re.compile(r"/(subagents|workflows)/")


def parse_iso(value: str) -> datetime:
    """Parse an ISO8601 timestamp into an aware UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def timestamps_in(chunk: bytes) -> list[datetime]:
    out = []
    for raw in TS_RE.findall(chunk):
        try:
            out.append(parse_iso(raw.decode("utf-8", "replace")))
        except ValueError:
            continue  # a malformed timestamp is not a reason to drop the file
    return out


def scan_whole_file(path: str) -> tuple[datetime | None, datetime | None, list[datetime]]:
    """Stream the entire file, returning (first, last, all timestamps)."""
    seen: list[datetime] = []
    try:
        with open(path, "rb") as fh:
            for line in fh:
                seen.extend(timestamps_in(line))
    except OSError:
        return None, None, []
    if not seen:
        return None, None, []
    return min(seen), max(seen), seen


def probe(path: str, size: int) -> tuple[datetime | None, datetime | None, bool]:
    """Cheaply find (first_record, last_record) without reading the whole file.

    Returns (first, last, did_full_scan). Falls back to a full scan when the tail
    window holds no timestamped record — correctness over speed.
    """
    if size <= TAIL_BYTES:
        first, last, _ = scan_whole_file(path)
        return first, last, True

    try:
        with open(path, "rb") as fh:
            head = fh.read(HEAD_BYTES)
            fh.seek(-TAIL_BYTES, os.SEEK_END)
            tail = fh.read()
    except OSError:
        return None, None, False

    # The first line of a mid-file seek is almost certainly partial — drop it so we never
    # read a truncated timestamp as real.
    tail = tail.split(b"\n", 1)[1] if b"\n" in tail else b""

    head_ts = timestamps_in(head)
    tail_ts = timestamps_in(tail)

    if not tail_ts:
        first, last, _ = scan_whole_file(path)
        return first, last, True

    first = min(head_ts) if head_ts else min(tail_ts)
    return first, max(tail_ts), False


def count_in_window(path: str, since: datetime) -> int:
    """Count records at or after the watermark. Only called for survivors."""
    n = 0
    try:
        with open(path, "rb") as fh:
            for line in fh:
                for ts in timestamps_in(line):
                    if ts >= since:
                        n += 1
    except OSError:
        return 0
    return n


def iter_candidates(root: str, since: datetime, min_size: int):
    """mtime prefilter — cheap, and it never drops a file that has in-window records."""
    cutoff = since.timestamp()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("subagents", "workflows")]
        for name in filenames:
            if not name.endswith(".jsonl"):
                continue
            full = os.path.join(dirpath, name)
            if EXCLUDE_DIR_RE.search(full):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            if st.st_mtime < cutoff or st.st_size < min_size:
                continue
            yield full, st.st_size


def fmt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else "-"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="watermark, ISO8601 (e.g. 2026-08-02T07:00:00Z)")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--min-size", type=int, default=0, help="skip files smaller than this many bytes")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of TSV")
    ap.add_argument("--show-dropped", action="store_true", help="also report what mtime over-selected")
    args = ap.parse_args()

    try:
        since = parse_iso(args.since)
    except ValueError:
        print(f"error: --since is not valid ISO8601: {args.since!r}", file=sys.stderr)
        return 2

    if not os.path.isdir(args.root):
        print(f"error: --root does not exist: {args.root}", file=sys.stderr)
        return 2

    kept, dropped = [], []
    for path, size in iter_candidates(args.root, since, args.min_size):
        first, last, _ = probe(path, size)
        if last is None:
            dropped.append({"path": path, "size": size, "first": None, "last": None,
                            "reason": "no timestamped record"})
            continue
        if last < since:
            dropped.append({"path": path, "size": size, "first": first, "last": last,
                            "reason": "newest real record predates watermark"})
            continue
        kept.append({"path": path, "size": size, "first": first, "last": last,
                     "in_window": count_in_window(path, since)})

    kept.sort(key=lambda r: r["in_window"], reverse=True)

    if args.json:
        payload = {
            "since": fmt(since),
            "kept": [{**r, "first": fmt(r["first"]), "last": fmt(r["last"])} for r in kept],
            "dropped": [{**r, "first": fmt(r["first"]), "last": fmt(r["last"])} for r in dropped],
            "summary": {"candidates": len(kept) + len(dropped), "kept": len(kept), "dropped": len(dropped)},
        }
        print(json.dumps(payload, indent=2))
        return 0

    for r in kept:
        print(f"{r['path']}\t{r['size']}\t{fmt(r['first'])}\t{fmt(r['last'])}\t{r['in_window']}")

    if args.show_dropped:
        print(f"\n# dropped by content filter ({len(dropped)} of {len(kept) + len(dropped)} mtime candidates)",
              file=sys.stderr)
        for r in dropped:
            print(f"# {r['path']}\tlast_real={fmt(r['last'])}\t{r['reason']}", file=sys.stderr)

    print(f"\n# {len(kept)} in-window transcripts, {len(dropped)} rejected "
          f"(mtime said yes, content said no)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
