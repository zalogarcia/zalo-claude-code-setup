#!/usr/bin/env python3
"""PreToolUse guard for mcp__supabase__execute_sql.

Mechanizes two prose rules that a 60-session audit (2026-07-11) showed were
routinely skipped under momentum:
  1. Multi-statement SQL is always blocked — execute_sql returns only the
     LAST statement's result, so earlier output is silently lost (cost
     retries in 10+ sessions).
  2. Schema-first: the first data query of a session is held once, with a
     pointer to the schema snapshot / information_schema, to kill
     column-name guessing. Schema-catalog queries pass freely and satisfy
     the check; the held query passes on re-run (deadlock-free by design).

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import os
import re
import sys


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

    # --- Rule 2: schema-first, one-time hold per session ---
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

    if not os.path.exists(marker):
        with open(marker, "w") as f:
            f.write("warned\n")
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

    sys.exit(0)


if __name__ == "__main__":
    main()
