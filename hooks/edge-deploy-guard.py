#!/usr/bin/env python3
"""PreToolUse guard for mcp__supabase__deploy_edge_function.

The MCP deploy tool passes file content as a JSON string and DOUBLES every
backslash in it. Source that is correct on disk arrives in prod corrupted:

    "\\n"        -> literal \\n text, so SSE frames never terminate
    "\\uD83D"    -> literal \\uD83D text instead of the emoji
    /\\{\\{x\\}\\}/g  -> regex that can never match

Measured 2026-08-05 in 90-day-cmaa-game-app: demo-chat deployed this way took
31 prospect messages and returned 0 AI replies for ~7 hours. The version
number bumped cleanly, so nothing downstream looked wrong -- only pulling the
deployed content back or watching runtime behavior revealed it.

This guard blocks the deploy when any file's content contains a backslash and
points at the CLI, which uploads byte-exact from disk. Files with no backslash
are unaffected by the bug and pass through.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import sys

# Escape sequences whose corruption is silent -- the function still boots and
# the version still bumps, so no downstream signal exists. Ordered by how
# badly they bit us.
NOTABLE = [
    ("\\n", "newline -> SSE frames / line splitting break silently"),
    ("\\u", "unicode escape -> literal \\uXXXX text renders to users"),
    ("\\t", "tab -> literal \\t text"),
    ("\\r", "carriage return -> literal \\r text"),
    ("\\d", "regex digit class -> pattern never matches"),
    ("\\w", "regex word class -> pattern never matches"),
    ("\\s", "regex whitespace class -> pattern never matches"),
    ("\\.", "escaped dot -> pattern never matches"),
    ("\\{", "escaped brace -> template/regex substitution silently stops"),
]


def describe(content: str) -> list:
    """Which notable escape sequences appear in this file."""
    return [f"{seq}  ({why})" for seq, why in NOTABLE if seq in content]


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        # Never block on a payload we cannot read.
        sys.exit(0)

    # Valid JSON that isn't an object (a bare string/list) must allow, not
    # crash -- .get() on a str raises and exits non-zero.
    if not isinstance(data, dict):
        sys.exit(0)

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        sys.exit(0)
    files = tool_input.get("files")
    if not isinstance(files, list):
        sys.exit(0)

    fn_name = tool_input.get("name") or "<unnamed>"
    project_id = tool_input.get("project_id") or "<project-ref>"

    offenders = []
    for f in files:
        if not isinstance(f, dict):
            continue
        content = f.get("content")
        if not isinstance(content, str) or "\\" not in content:
            continue
        name = f.get("name") or "<unnamed file>"
        offenders.append((name, content.count("\\"), describe(content)))

    if not offenders:
        sys.exit(0)

    lines = [
        "BLOCKED (edge-deploy-guard): mcp__supabase__deploy_edge_function "
        "doubles every backslash in uploaded content, so this deploy would "
        "ship corrupted code that still boots and still bumps the version.",
        "",
        "Files containing backslashes:",
    ]
    for name, count, notable in offenders:
        lines.append(f"  - {name}: {count} backslash(es)")
        for n in notable:
            lines.append(f"      {n}")

    lines += [
        "",
        "Use the Supabase CLI instead -- it uploads byte-exact from disk:",
        "",
        f"  supabase functions deploy {fn_name} \\",
        f"    --project-ref {project_id} --no-verify-jwt --use-api",
        "",
        "(--use-api is required when Docker isn't running. Never --prune.)",
        "",
        "Then VERIFY before claiming success: pull the deployed content back "
        "with mcp__supabase__get_edge_function and confirm the backslashes are "
        "single. A version bump alone is not proof -- that is exactly the "
        "check that missed the 2026-08-05 demo-chat outage.",
    ]

    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
