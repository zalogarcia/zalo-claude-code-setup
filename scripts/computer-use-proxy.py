#!/usr/bin/env python3
"""stdio MCP proxy in front of the Computer Use server, for scripts/computer-use.sh.

usage: computer-use-proxy.py --declined-log <file>

The allow list is always ~/.claude/config/computer-use-apps.json (no override: a path
argument or env var would let an agent swap in its own list), and the server runs on
the computer surface only (CODEX_CU_ENABLED_SURFACES=computer), so the browser plugin's
own access prompts never come up and the logged in Chrome is reachable only as an app,
which the list does not hold. An app in macOS Computer Use's own "Always allow" store
(ComputerUseAppApprovals.json) is approved without a prompt, so computer-use.py refuses
to run while that store holds an app the list does not, and social-pace-guard protects
both files.

Spawns the real cua_repl server through codex-cu-mcp.py and passes every message
through unchanged, except the app approval prompts. Headless `codex exec` declines
every "Allow Computer Use to use X?" prompt, so this answers those itself: it accepts
only when the app's bundle id is in the allow list (no _meta.persist, so the grant
lasts for this server session and is never stored) and declines the rest, appending
one JSON line per decline to the declined log so the caller can say which app to ask
Zalo about. Every other elicitation goes on to Codex unchanged: since CLI 0.160.0
Codex asks the server for a "Review JavaScript execution" prompt on each js call and
answers it itself (measured 2026-10-03; declining it here broke every run).
"""
import json
import os
import pwd
import re
import subprocess
import sys
import threading
import time

LAUNCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "codex-cu-mcp.py")
APPS = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".claude", "config",
                    "computer-use-apps.json")  # the account's home, not $HOME
APPROVAL_RE = re.compile(r'Allow Computer Use to use "(.+)"\?')


def load_apps(path):
    """{bundle_id_lower: name} from the allow list; an unreadable list allows nothing."""
    try:
        with open(path) as f:
            apps = json.load(f).get("apps") or []
        return {str(a["bundle_id"]).lower(): str(a.get("name") or a["bundle_id"])
                for a in apps if isinstance(a, dict) and a.get("bundle_id")}
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return {}


def decide(params, allowed):
    """("accept" | "decline" | "forward", label) for one elicitation/create params object.
    Only app approvals are decided here; anything else is Codex's to answer."""
    msg = str((params or {}).get("message") or "")
    m = APPROVAL_RE.fullmatch(msg)
    if not m:
        return "forward", msg[:120]
    meta = (params or {}).get("_meta") or {}
    tp = meta.get("tool_params") if isinstance(meta, dict) else None
    bundle = str((tp or {}).get("app") or "") if isinstance(tp, dict) else ""
    label = m.group(1) + (" (%s)" % bundle if bundle else "")
    return ("accept" if bundle and bundle.lower() in allowed else "decline"), label


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main():
    allowed = load_apps(APPS)
    declined_log = arg("--declined-log")
    srv = subprocess.Popen([sys.executable, LAUNCHER], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, bufsize=0,
                           env=dict(os.environ, CODEX_CU_ENABLED_SURFACES="computer"))
    lock = threading.Lock()

    def to_server(raw):
        with lock:
            srv.stdin.write(raw)
            srv.stdin.flush()

    def client_to_server():
        for line in sys.stdin.buffer:
            to_server(line)
        try:
            srv.stdin.close()
        except OSError:
            pass

    threading.Thread(target=client_to_server, daemon=True).start()
    for line in srv.stdout:
        try:
            m = json.loads(line)
        except ValueError:
            m = None
        if isinstance(m, dict) and m.get("method") == "elicitation/create" and "id" in m:
            verdict, label = decide(m.get("params"), allowed)
            if verdict != "forward":
                result = ({"action": "accept", "content": {}} if verdict == "accept"
                          else {"action": "decline"})
                to_server((json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": result})
                           + "\n").encode())
                if verdict == "decline" and declined_log:
                    with open(declined_log, "a") as f:
                        f.write(json.dumps({"t": round(time.time(), 1), "declined": label})
                                + "\n")
                continue
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    return srv.wait()


if __name__ == "__main__":
    # os._exit: the stdin pump thread may still hold the buffered stdin lock, and a
    # normal interpreter shutdown then aborts with _enter_buffered_busy (QA 10-03)
    code = main()
    sys.stdout.flush()
    os._exit(code if isinstance(code, int) and code >= 0 else 1)
