#!/usr/bin/env python3
"""Behaviour suite for codex-cu-mcp.py (the codex-cu MCP launcher).

Run: python3 ~/.claude/scripts/codex-cu-mcp.test.py
Every case points CODEX_CU_CACHE_DIR at a fake cache; the real ChatGPT app is
never launched.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex-cu-mcp.py")
passed = failed = 0
_dirs = []


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  ok   %s" % label)
    else:
        failed += 1
        print("  FAIL %s %s" % (label, detail))


def workdir():
    d = tempfile.mkdtemp(prefix="codex-cu-mcp-test-")
    _dirs.append(d)
    return d


def fake_server(d, name):
    """An executable that prints its argv and two env vars, like the real server would read them."""
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\necho \"ARGS=$*\"\necho \"VER=$BROWSER_USE_CODEX_APP_VERSION\"\n"
                "echo \"PARENT=$CODEX_CU_TEST_PARENT\"\n")
    os.chmod(path, 0o755)
    return path


def add_version(cache, version, command, marker):
    vd = os.path.join(cache, version)
    os.makedirs(vd)
    with open(os.path.join(vd, ".mcp.json"), "w") as f:
        json.dump({"mcpServers": {"cua_repl": {
            "command": command, "args": ["cua-repl-%s.mjs" % marker],
            "env": {"BROWSER_USE_CODEX_APP_VERSION": version}}}}, f)


def run(cache):
    env = dict(os.environ, CODEX_CU_CACHE_DIR=cache, CODEX_CU_TEST_PARENT="kept")
    return subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True,
                          text=True, timeout=20)


def main():
    # 1-4: two versions; string order would pick 26.917.62051 ("9" > "1"),
    # version order must pick 26.1000.1.
    d = workdir()
    cache = os.path.join(d, "cache")
    os.makedirs(cache)
    server = fake_server(d, "server")
    add_version(cache, "26.917.62051", server, "old")
    add_version(cache, "26.1000.1", server, "new")
    os.makedirs(os.path.join(cache, "not-a-version"))
    r = run(cache)
    check("1: exits 0 when a valid config exists", r.returncode == 0, r.stderr)
    check("2: picks the newest version by version order, not string order",
          "ARGS=cua-repl-new.mjs" in r.stdout and "VER=26.1000.1" in r.stdout, r.stdout)
    check("3: the config env reaches the server", "VER=26.1000.1" in r.stdout, r.stdout)
    check("4: the parent env passes through", "PARENT=kept" in r.stdout, r.stdout)

    # 5-6: a missing cache fails loudly with one stderr line.
    r = run(os.path.join(d, "no-such-cache"))
    check("5: a missing cache exits nonzero", r.returncode != 0)
    check("6: a missing cache prints one clear stderr line",
          r.stderr.startswith("codex-cu-mcp: no Computer Use plugin cache")
          and r.stderr.count("\n") == 1 and r.stdout == "", repr(r.stderr))

    # 7: a cache with no version dir fails loudly.
    empty = os.path.join(d, "empty")
    os.makedirs(os.path.join(empty, "junk"))
    r = run(empty)
    check("7: a cache with no <version>/.mcp.json exits nonzero with a message",
          r.returncode != 0 and "no <version>/.mcp.json" in r.stderr, r.stderr)

    # 8: a broken .mcp.json fails loudly, no traceback.
    bad = os.path.join(d, "bad")
    os.makedirs(os.path.join(bad, "1.2.3"))
    with open(os.path.join(bad, "1.2.3", ".mcp.json"), "w") as f:
        f.write("{not json")
    r = run(bad)
    check("8: an unparseable .mcp.json exits nonzero, one line, no traceback",
          r.returncode != 0 and "cannot read mcpServers.cua_repl" in r.stderr
          and "Traceback" not in r.stderr and r.stderr.count("\n") == 1, r.stderr)

    # 9: valid JSON without cua_repl fails loudly.
    nokey = os.path.join(d, "nokey")
    os.makedirs(os.path.join(nokey, "1.2.3"))
    with open(os.path.join(nokey, "1.2.3", ".mcp.json"), "w") as f:
        json.dump({"mcpServers": {}}, f)
    r = run(nokey)
    check("9: a config with no cua_repl entry exits nonzero",
          r.returncode != 0 and "cua_repl" in r.stderr, r.stderr)

    # 11-13: wrong field types fail with one line, no traceback (QA round 1).
    for n, (label, spec) in enumerate((
            ("args as a string", {"command": server, "args": "abc"}),
            ("env with a null value", {"command": server, "env": {"V": None}}),
            ("command as a list", {"command": [server]})), start=11):
        bad_t = os.path.join(d, "types%d" % n)
        os.makedirs(os.path.join(bad_t, "1.0.0"))
        with open(os.path.join(bad_t, "1.0.0", ".mcp.json"), "w") as f:
            json.dump({"mcpServers": {"cua_repl": spec}}, f)
        r = run(bad_t)
        check("%d: %s exits nonzero with one line" % (n, label),
              r.returncode != 0 and r.stderr.count("\n") == 1 and "Traceback" not in r.stderr
              and r.stdout == "", repr(r.stderr))

    # 14: a non ASCII digit dir name is not a version and does not crash.
    odd = os.path.join(d, "odd")
    os.makedirs(os.path.join(odd, "²"))
    add_version(odd, "2.0.0", server, "ascii")
    r = run(odd)
    check("14: a non ASCII digit dir is skipped, the real version runs",
          r.returncode == 0 and "ARGS=cua-repl-ascii.mjs" in r.stdout, r.stderr)

    # 15: CODEX_CU_ENABLED_SURFACES (set by computer-use-proxy.py) wins over the config.
    surf = os.path.join(d, "surf")
    os.makedirs(os.path.join(surf, "1.0.0"))
    srv2 = os.path.join(d, "server2")
    with open(srv2, "w") as f:
        f.write("#!/bin/sh\necho \"SURF=$CUA_REPL_ENABLED_SURFACES\"\n"
                "echo \"SVC=$NODE_REPL_TRUSTED_SERVICES\"\n")
    os.chmod(srv2, 0o755)
    with open(os.path.join(surf, "1.0.0", ".mcp.json"), "w") as f:
        json.dump({"mcpServers": {"cua_repl": {"command": srv2, "env": {
            "CUA_REPL_ENABLED_SURFACES": "browser,computer",
            "NODE_REPL_TRUSTED_SERVICES": json.dumps({"browser": "@oai/browser-desktop/service",
                                                      "sky": "@oai/sky/service"})}}}}, f)
    r1 = run(surf)
    env2 = dict(os.environ, CODEX_CU_CACHE_DIR=surf, CODEX_CU_ENABLED_SURFACES="computer")
    r2 = subprocess.run([sys.executable, SCRIPT], env=env2, capture_output=True, text=True,
                        timeout=20)
    check("15: the config surfaces apply by default, the override narrows them",
          "SURF=browser,computer" in r1.stdout and "SURF=computer" in r2.stdout,
          r1.stdout + r2.stdout)
    check("16: without the browser surface the browser trusted service is dropped too",
          '"browser"' in r1.stdout and 'SVC={"sky": "@oai/sky/service"}' in r2.stdout,
          r1.stdout + r2.stdout)

    # 10: the server command is gone (ChatGPT.app uninstalled).
    gone = os.path.join(d, "gone")
    os.makedirs(gone)
    add_version(gone, "1.0.0", "/Applications/NoSuchApp.app/Contents/node", "x")
    r = run(gone)
    check("10: a missing ChatGPT.app command exits nonzero with a message",
          r.returncode != 0 and "is missing" in r.stderr, r.stderr)

    for x in _dirs:
        shutil.rmtree(x, ignore_errors=True)
    total = passed + failed
    print("\n%d/%d passed, %d failed" % (passed, total, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
