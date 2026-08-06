#!/usr/bin/env python3
"""Tests for edge-deploy-guard.py. Run: python3 edge-deploy-guard.test.py"""

import json
import subprocess
import sys
import os

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge-deploy-guard.py")

ALLOW, BLOCK = 0, 2
passed = failed = 0


def run(payload, raw=False) -> tuple:
    p = subprocess.run(
        [sys.executable, HOOK],
        input=payload if raw else json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stderr


def check(label, payload, expected, expect_in_stderr=None):
    global passed, failed
    code, err = run(payload)
    ok = code == expected
    if ok and expect_in_stderr:
        ok = expect_in_stderr in err
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}: exit {code} (wanted {expected})")
        if expect_in_stderr and expect_in_stderr not in err:
            print(f"        stderr missing {expect_in_stderr!r}")
            print(f"        stderr was: {err[:400]}")


def deploy(files, name="demo-chat", project_id="testprojectref00"):
    return {
        "tool_name": "mcp__supabase__deploy_edge_function",
        "tool_input": {
            "project_id": project_id,
            "name": name,
            "entrypoint_path": "index.ts",
            "verify_jwt": False,
            "files": files,
        },
    }


def f(content, name="demo-chat/index.ts"):
    return [{"name": name, "content": content}]


print("edge-deploy-guard tests\n")

# --- The real incident -------------------------------------------------------
print("regression: the 2026-08-05 demo-chat corruption")
check(
    "blocks the unicode escape that shipped literal text",
    deploy(f('const icon = "\\uD83D\\uDCAC";')),
    BLOCK,
    "\\u",
)
check(
    "blocks the SSE newline that killed streaming",
    deploy(f('return `data: ${JSON.stringify(d)}\\n\\n`;')),
    BLOCK,
    "\\n",
)
check(
    "blocks the split that stopped extracting deltas",
    deploy(f('const lines = chunk.split("\\n");')),
    BLOCK,
)
check(
    "blocks the template-var regex that stopped matching",
    deploy(f("t.replace(/\\{\\{company_name\\}\\}/g, x);")),
    BLOCK,
    "\\{",
)

# --- Clean files must not be blocked -----------------------------------------
print("\nfiles with no backslash pass through")
check(
    "plain function with no escapes",
    deploy(f('Deno.serve(() => new Response("ok"));')),
    ALLOW,
)
check(
    "real emoji character instead of an escape",
    deploy(f('const icon = "\U0001F4AC";')),
    ALLOW,
)
check(
    "empty file list",
    deploy([]),
    ALLOW,
)

# --- Multi-file: any offending file blocks the whole deploy -------------------
print("\nmulti-file deploys")
check(
    "clean entrypoint + dirty shared file still blocks",
    deploy(
        [
            {"name": "fn/index.ts", "content": 'const a = "ok";'},
            {"name": "_shared/crypto.ts", "content": 'x.split("\\n");'},
        ]
    ),
    BLOCK,
    "_shared/crypto.ts",
)
check(
    "all-clean multi-file passes",
    deploy(
        [
            {"name": "fn/index.ts", "content": 'const a = "ok";'},
            {"name": "deno.json", "content": '{ "imports": {} }'},
        ]
    ),
    ALLOW,
)

# --- Message quality: it must name the escape hatch --------------------------
print("\nblock message is actionable")
check(
    "names the CLI command",
    deploy(f('x.split("\\n");')),
    BLOCK,
    "supabase functions deploy",
)
check(
    "carries the function name into the command",
    deploy(f('x.split("\\n");'), name="reacher-copilot"),
    BLOCK,
    "deploy reacher-copilot",
)
check(
    "carries the project ref into the command",
    deploy(f('x.split("\\n");'), project_id="abcdef123456"),
    BLOCK,
    "--project-ref abcdef123456",
)
check(
    "demands content verification, not just a version bump",
    deploy(f('x.split("\\n");')),
    BLOCK,
    "version bump alone is not proof",
)
check(
    "reports the backslash count",
    deploy(f('a("\\n"); b("\\n"); c("\\n");')),
    BLOCK,
    "3 backslash(es)",
)

# --- Malformed input must never block ---------------------------------------
print("\nmalformed payloads always allow (never block what we can't read)")
check("no tool_input", {"tool_name": "x"}, ALLOW)
check("files is not a list", {"tool_input": {"files": "nope"}}, ALLOW)
check("file entry is not a dict", {"tool_input": {"files": ["nope"]}}, ALLOW)
check("content is not a string", {"tool_input": {"files": [{"name": "a", "content": 5}]}}, ALLOW)
check("missing content key", {"tool_input": {"files": [{"name": "a"}]}}, ALLOW)
check("empty payload", {}, ALLOW)

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

total = passed + failed
print(f"\n{passed}/{total} passed")
sys.exit(1 if failed else 0)
