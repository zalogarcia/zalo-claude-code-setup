#!/usr/bin/env python3
"""Launch Codex Computer Use (the ChatGPT app's cua_repl MCP server) for Claude Code.

Registered as the user scope MCP server `codex-cu`:
    claude mcp add codex-cu --scope user -- ~/.claude/scripts/codex-cu-mcp.py
Its `js` tool can drive the logged in Chrome, so the social-pace-guard matcher in
settings.json names `mcp__codex-cu__.*`, and codex-sync.py keeps codex-cu out of
~/.codex (CLAUDE_ONLY_MCP). Re-registering elsewhere: land both of those first.

The ChatGPT app ships the server config in
~/.codex/plugins/cache/openai-bundled/unified-computer-use/<version>/.mcp.json,
and its env embeds the version, so a hard coded copy breaks on every app
update. This reads the newest version's `cua_repl` entry at launch and execs
it, so stdio passes straight through. Any failure prints one line to stderr
and exits 1, which `claude mcp list` shows as "Failed to connect".

CODEX_CU_CACHE_DIR overrides the cache dir; only codex-cu-mcp.test.py sets it.
"""

import json
import os
import sys

CACHE = os.environ.get("CODEX_CU_CACHE_DIR") or os.path.expanduser(
    "~/.codex/plugins/cache/openai-bundled/unified-computer-use")


def fail(msg):
    sys.stderr.write("codex-cu-mcp: %s\n" % msg)
    sys.exit(1)


def version_key(name):
    """'26.917.62051' -> (26, 917, 62051); None for anything that is not a version."""
    parts = name.split(".")
    if not all(p.isascii() and p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def newest_config(cache):
    if not os.path.isdir(cache):
        fail("no Computer Use plugin cache at %s (is the ChatGPT app installed and "
             "signed in?)" % cache)
    found = []
    for name in os.listdir(cache):
        key = version_key(name)
        path = os.path.join(cache, name, ".mcp.json")
        if key is not None and os.path.isfile(path):
            found.append((key, path))
    if not found:
        fail("no <version>/.mcp.json under %s" % cache)
    return max(found)[1]


def main():
    path = newest_config(CACHE)
    try:
        with open(path) as f:
            spec = json.load(f)["mcpServers"]["cua_repl"]
        command, args, env = spec["command"], spec.get("args") or [], spec.get("env") or {}
        if not (isinstance(command, str) and isinstance(args, list)
                and all(isinstance(a, str) for a in args) and isinstance(env, dict)
                and all(isinstance(v, str) for v in env.values())):
            raise TypeError("command must be a string, args a list of strings, "
                            "env an object of strings")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        fail("cannot read mcpServers.cua_repl from %s: %s: %s"
             % (path, type(e).__name__, e))
    if not (os.path.isfile(command) and os.access(command, os.X_OK)):
        fail("server command %s is missing (ChatGPT.app moved or uninstalled?)" % command)
    merged = dict(os.environ)
    merged.update(env)
    # computer-use-proxy.py narrows the server to the computer surface (no browser plugin)
    surfaces = os.environ.get("CODEX_CU_ENABLED_SURFACES")
    if surfaces:
        merged["CUA_REPL_ENABLED_SURFACES"] = surfaces
        if "browser" not in surfaces.split(","):
            # the trusted services list would still start the browser service (QA 10-03)
            try:
                services = json.loads(merged.get("NODE_REPL_TRUSTED_SERVICES") or "{}")
                services.pop("browser", None)
                merged["NODE_REPL_TRUSTED_SERVICES"] = json.dumps(services)
            except (ValueError, AttributeError):
                fail("cannot narrow NODE_REPL_TRUSTED_SERVICES for surfaces %r" % surfaces)
    os.execve(command, [command] + args, merged)


if __name__ == "__main__":
    main()
