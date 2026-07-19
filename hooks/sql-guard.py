#!/usr/bin/env python3
"""PreToolUse guard for mcp__supabase__execute_sql.

v1 (2026-07-11) mechanized two prose rules a 60-session audit showed were
routinely skipped under momentum:
  1. Multi-statement SQL is always blocked — execute_sql returns only the
     LAST statement's result, so earlier output is silently lost.
  2. Schema-first: the first data query of a session is held once, pointing
     at the schema snapshot, to kill column-name guessing.

v2 (2026-07-19 weekly audit, P3): the one-time hold worked 4/4 on first
queries, but guessing resumed on LATER queries (~7 SQL shape-guess instances
across the week; one session ran on a 12-day-stale snapshot). Added:
  3. Per-query table validation: every query's FROM/JOIN/UPDATE/INSERT/DELETE
     targets are checked against the repo's docs/SCHEMA-PROD.md; unknown
     tables block with the snapshot's section for the closest match.
     Parse uncertainty always ALLOWS — this guard never blocks what it
     cannot confidently read (CTEs and function calls are excluded).
  4. Snapshot staleness: if the snapshot's generated-at date is >7 days old,
     the first data query is held once with "regen via /schema-snapshot".

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import datetime
import difflib
import json
import os
import re
import sys

SNAPSHOT_RELPATH = os.path.join("docs", "SCHEMA-PROD.md")
SNAPSHOT_MAX_STALE_DAYS = 7


def strip_sql(q: str) -> str:
    """Remove string literals, dollar-quoted bodies, and comments so structural
    checks don't false-positive.

    Single left-to-right pass: strings/dollar-bodies/comments are consumed by ONE
    alternation, so a `--` inside a quoted region can never be eaten as a comment.
    (Sequential re.sub passes with comments first false-blocked legit single
    statements AND false-passed real multi-statement SQL — QA finding 2026-07-11.)
    """
    return re.sub(
        r"'(?:[^']|'')*'"  # standard string literal ('' = escaped quote)
        r"|\$([A-Za-z_][A-Za-z0-9_]*|)\$.*?\$\1\$"  # dollar-quoted body, tag may have digits or be empty
        r"|--[^\n]*"  # line comment
        r"|/\*.*?\*/",  # block comment
        # strings/dollar-bodies collapse to a placeholder token; comments must
        # vanish entirely — replacing a trailing "-- comment" with '' made
        # "SELECT 1; -- done" look multi-statement (QA iteration-2 finding)
        lambda m: "" if m.group(0).startswith("--") or m.group(0).startswith("/*") else "''",
        q,
        flags=re.S,
    )


def find_snapshot(cwd: str):
    """Walk up from cwd looking for docs/SCHEMA-PROD.md. None if absent."""
    d = os.path.abspath(cwd or os.getcwd())
    for _ in range(8):
        candidate = os.path.join(d, SNAPSHOT_RELPATH)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def snapshot_age_days(text: str):
    """Age in days from the first YYYY-MM-DD in the header lines; None if
    no parseable date (fail open — absence of a date never blocks)."""
    for line in text.splitlines()[:10]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if m:
            try:
                gen = datetime.date.fromisoformat(m.group(1))
            except ValueError:
                continue
            return (datetime.date.today() - gen).days
    return None


def snapshot_tables(text: str):
    """Table inventory from markdown headers (## table / ### table). Returns
    a set, or None when the format is unrecognized (fewer than 3 headers) —
    None means membership can't be judged, so validation is skipped."""
    tables = {
        m.group(1).lower()
        for m in re.finditer(r"^#{2,4}\s+`?([A-Za-z_][\w]*)`?\s*$", text, re.M)
    }
    return tables if len(tables) >= 3 else None


def extract_tables(stripped: str):
    """Physical tables referenced by the query, lowercased, schema prefix
    dropped. CTE names and set-returning function calls are excluded.
    Deliberately dumb; anything it can't see simply isn't validated."""
    s = stripped.lower()
    ctes = set(re.findall(r"\bwith\s+(?:recursive\s+)?([a-z_]\w*)\s+as\b", s))
    ctes |= set(re.findall(r",\s*([a-z_]\w*)\s+as\s*\(", s))
    refs = set()
    for pat in (
        # \b before the lookahead prevents backtracking one char to defeat it
        # (without it, "unnest(" matched as table "unnes" — caught in testing).
        # LATERAL/ONLY are consumed as optional keywords so "JOIN LATERAL fn(...)"
        # validates fn (excluded by the paren lookahead), not the keyword itself
        # (QA 2026-07-19: 'lateral'/'only' were captured as phantom tables).
        r"\b(?:from|join)\s+(?:lateral\s+|only\s+)?([a-z_][\w.]*)\b(?!\s*\()",
        r"\bupdate\s+(?:only\s+)?([a-z_][\w.]*)",
        r"\binsert\s+into\s+([a-z_][\w.]*)",
        r"\bdelete\s+from\s+(?:only\s+)?([a-z_][\w.]*)",
    ):
        refs |= set(re.findall(pat, s))
    refs -= {"lateral", "only"}  # belt-and-braces: never validate SQL keywords
    out = set()
    for r in refs:
        name = r.split(".")[-1]
        if name and name not in ctes:
            out.add(name)
    return out


def snapshot_section(text: str, table: str) -> str:
    """The snapshot's section for `table` (up to 20 lines), or ''. Best effort."""
    lines = text.splitlines()
    start = None
    header = re.compile(r"^#{2,4}\s+`?" + re.escape(table) + r"`?\s*$", re.I)
    any_header = re.compile(r"^#{2,4}\s+\S")
    for i, line in enumerate(lines):
        if header.match(line):
            start = i
            break
    if start is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1:start + 21]:
        if any_header.match(line):
            break
        out.append(line)
    return "\n".join(out).strip()


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "mcp__supabase__execute_sql":
        sys.exit(0)

    query = (data.get("tool_input") or {}).get("query", "") or ""
    if not query.strip():
        sys.exit(0)

    stripped = strip_sql(query)

    # --- Rule 1: multi-statement block (always) ---
    if re.search(r";\s*\S", stripped):
        print(
            "BLOCKED (sql-guard): multi-statement SQL — execute_sql returns only "
            "the LAST statement's result; earlier statements' output is silently "
            "lost. Split into one execute_sql call per statement.",
            file=sys.stderr,
        )
        sys.exit(2)

    session = data.get("session_id") or "nosession"
    marker_dir = os.path.join("/tmp", f"claude-sql-guard-{os.getuid()}")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, session)

    schema_catalog = re.search(
        r"\b(information_schema|pg_catalog|pg_policies|pg_class|pg_indexes|"
        r"pg_tables|pg_attribute|pg_proc|pg_namespace|pg_constraint)\b",
        stripped,
        re.I,
    )
    if schema_catalog:
        # Schema was consulted — satisfies the check for the rest of the session.
        with open(marker, "w") as f:
            f.write("schema-consulted\n")
        sys.exit(0)

    snapshot_path = find_snapshot(data.get("cwd") or "")
    snapshot_text = ""
    if snapshot_path:
        try:
            with open(snapshot_path, encoding="utf-8", errors="replace") as f:
                snapshot_text = f.read()
        except Exception:
            snapshot_text = ""

    # --- Rule 2: schema-first, one-time hold per session (v2: stale-aware) ---
    if not os.path.exists(marker):
        with open(marker, "w") as f:
            f.write("warned\n")
        age = snapshot_age_days(snapshot_text) if snapshot_text else None
        if age is not None and age > SNAPSHOT_MAX_STALE_DAYS:
            print(
                f"HOLD (sql-guard, fires once per session): {snapshot_path} is "
                f"{age} days old (>{SNAPSHOT_MAX_STALE_DAYS}d) — a stale snapshot "
                "caused wrong-column guesses in a recent session. Run "
                "/schema-snapshot to refresh it (or verify via an "
                "information_schema.columns query), then re-run this exact query; "
                "this guard will not fire again.",
                file=sys.stderr,
            )
        else:
            print(
                "HOLD (sql-guard, fires once per session): schema-first rule. Before "
                "the first data query, confirm the schema for the tables you're about "
                "to touch — read the repo's schema snapshot (.claude/VERIFY.md points "
                "to it; regen via /schema-snapshot) or run an information_schema.columns "
                "query. Guessed column names cost retries in 10+ recent sessions. "
                "Re-run this exact query after checking; this guard will not fire again.",
                file=sys.stderr,
            )
        sys.exit(2)

    # --- Rule 3 (v2): per-query table validation against the snapshot ---
    if snapshot_text:
        known = snapshot_tables(snapshot_text)
        if known:
            unknown = [t for t in sorted(extract_tables(stripped)) if t not in known]
            if unknown:
                msgs = []
                for t in unknown:
                    close = difflib.get_close_matches(t, known, n=3, cutoff=0.6)
                    section = snapshot_section(snapshot_text, close[0]) if close else ""
                    hint = f" Did you mean: {', '.join(close)}?" if close else ""
                    msgs.append(f"- '{t}' is not in {snapshot_path}.{hint}")
                    if section:
                        msgs.append(f"  Closest match's snapshot section:\n{section}")
                print(
                    "BLOCKED (sql-guard v2): query references table(s) missing from "
                    "the schema snapshot:\n" + "\n".join(msgs) + "\n"
                    "If the table genuinely exists (snapshot drift), refresh via "
                    "/schema-snapshot or verify with information_schema.columns "
                    "(catalog queries always pass this guard).",
                    file=sys.stderr,
                )
                sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
