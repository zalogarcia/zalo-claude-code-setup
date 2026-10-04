#!/usr/bin/env python3
"""Run one native Mac app task on GPT-6.1 Sol through Codex Computer Use.

Entry point: ~/.claude/scripts/computer-use.sh "<task>" | --file <task.md> [--timeout S]

Zalo's decision (2026-10-03): computer use runs on GPT-6.1 Sol. This is the bench's
Sol arm made a rail: `codex exec -m gpt-6.1-sol` on the ChatGPT LOGIN (no API key in
the env, so it costs nothing extra per run; auth.json is never touched), read only
sandbox, --ephemeral, and NOTHING but Computer Use: shell, unified exec, multi agent,
apps, browser use, image generation and web search are off, and every MCP server and
plugin in ~/.codex/config.toml is disabled for the run (otherwise the model would also
hold Playwright, Supabase and GitHub, and the app allow list would not be the
boundary). Computer Use itself is served by computer-use-proxy.py on the computer
surface only, which answers the "Allow Computer Use to use X?" prompt from
~/.claude/config/computer-use-apps.json (Zalo's list, guarded by social-pace-guard).

Prints the final answer, the calls and the token usage; logs one JSON line per run to
~/.claude/logs/computer-use.log. Exit 0 done, 2 failed (a declined app, a timeout, an
error, no answer, a bad argument), 3 Codex limited: then fall back to mcp__codex-cu__js
in Claude. COMPUTER_USE_LOG overrides the log path (tests only).
"""
import json
import os
import pwd
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

try:
    import tomllib
except ImportError:  # python < 3.11
    tomllib = None

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir  # not $HOME: an env var must not move the list
LOG = os.environ.get("COMPUTER_USE_LOG") or os.path.join(HOME, ".claude", "logs",
                                                          "computer-use.log")
APPS = os.path.join(REAL_HOME, ".claude", "config", "computer-use-apps.json")  # no override
# macOS Computer Use's own "Always allow" store: an app listed there is approved by the
# server itself and no prompt reaches the proxy, so the rail refuses to run while it
# holds an app that is not on Zalo's list (QA 10-03). Today it holds Calculator only.
APPROVALS_STORE = os.path.join(
    REAL_HOME, "Library", "Group Containers", "2DC432GLL2.com.openai.sky.CUAService", "Library",
    "Application Support", "Software", "ComputerUseAppApprovals.json")
CODEX_CONFIG = os.path.join(os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex"),
                            "config.toml")
PROXY = os.path.join(HERE, "computer-use-proxy.py")
MODEL = "gpt-6.1-sol"
DEFAULT_TIMEOUT, MAX_TIMEOUT = 480, 570  # under the 600 s Bash ceiling
OFF_FEATURES = ("shell_tool", "unified_exec", "multi_agent", "apps", "browser_use",
                "browser_use_external", "in_app_browser", "image_generation")
# the bridge's Codex failure classifier (bg-codex.mjs), read only on the failure channel
LIMIT_RE = re.compile(r"\b429\b|rate[ _-]?limit|usage limit|quota|too many requests"
                      r"|you've (?:hit|reached) your", re.IGNORECASE)
PREAMBLE = (
    "Do this task on this Mac through the Computer Use `js` tool (the cua_repl MCP "
    "server); you have no shell. Only approved apps can be used: if an app is declined, "
    "stop and name it. Do not close or quit an app or window you did not open. Do not "
    "send, post, buy or delete anything unless the task explicitly asks for it. When "
    "finished, end your reply with one line in the form `ANSWER: <result>`.\n\nTask: ")
USAGE = 'usage: computer-use.sh "<task>" | --file <task.md> [--timeout SECONDS]'


def usage_error(msg):
    print("computer-use: %s\n%s" % (msg, USAGE), file=sys.stderr)
    sys.exit(2)


def parse_args(argv):
    task, timeout, i = None, DEFAULT_TIMEOUT, 0
    while i < len(argv):
        a = argv[i]
        if a == "--file" and i + 1 < len(argv):
            try:
                with open(argv[i + 1]) as f:
                    task = f.read()
            except OSError as e:
                usage_error("cannot read %s: %s" % (argv[i + 1], e.strerror or e))
            i += 2
        elif a == "--timeout" and i + 1 < len(argv):
            try:
                timeout = max(1, min(MAX_TIMEOUT, int(argv[i + 1])))
            except ValueError:
                usage_error("--timeout needs whole seconds, got %r" % argv[i + 1])
            i += 2
        elif a in ("-h", "--help"):
            print(USAGE)
            sys.exit(0)
        elif task is None and not a.startswith("--"):
            task = a
            i += 1
        else:
            usage_error("unknown argument %r" % a)
    if not task or not task.strip():
        usage_error("no task given")
    return task.strip(), timeout


BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_@\-]+$")


def store_extras(store_path, apps_path):
    """Bundle ids the native approvals store allows that Zalo's list does not, or a
    problem string when either file cannot be read (fail closed)."""
    try:
        with open(apps_path) as f:
            allowed = {str(a["bundle_id"]).lower() for a in json.load(f).get("apps") or []
                       if isinstance(a, dict) and a.get("bundle_id")}
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as e:
        return None, "cannot read the allow list %s (%s)" % (apps_path, e)
    if not os.path.exists(store_path):
        return [], None
    try:
        with open(store_path) as f:
            stored = json.load(f).get("approvedBundleIdentifiers") or []
    except (OSError, ValueError, AttributeError) as e:
        return None, "cannot read the Computer Use approvals store (%s)" % e
    return sorted({str(b) for b in stored if str(b).lower() not in allowed}), None


def isolation_overrides():
    """(-c flags that switch off every MCP server and plugin in Codex's config, problem).
    `codex -c` splits keys on dots and does not read TOML quotes (measured: a quoted
    `mcp_servers."x".enabled=false` makes a NEW empty server and Codex refuses to start,
    and a quoted plugin key disables nothing), so a name it cannot address as a bare key
    is a problem: the run refuses rather than start with that server loaded."""
    flags, cfg = [], {}
    if os.path.exists(CODEX_CONFIG):
        if tomllib is None:
            return [], "python has no tomllib to read %s" % CODEX_CONFIG
        try:
            with open(CODEX_CONFIG, "rb") as f:
                cfg = tomllib.load(f)
        except (OSError, ValueError) as e:
            return [], "cannot read %s (%s)" % (CODEX_CONFIG, e)
    servers = [n for n in sorted(cfg.get("mcp_servers") or {}) if n != "cua_repl"]
    plugins = sorted(set(cfg.get("plugins") or {}) | {"unified-computer-use@openai-bundled"})
    bad = [n for n in servers + plugins if not BARE_KEY_RE.match(n)]
    if bad:
        return [], "cannot switch off %s for the run (codex -c needs bare names)" % ", ".join(bad)
    for name in servers:
        flags += ["-c", "mcp_servers.%s.enabled=false" % name]
    for name in plugins:
        flags += ["-c", "plugins.%s.enabled=false" % name]
    return flags, None


def codex_cmd(workdir, last_msg, declined_log, isolation):
    server =('mcp_servers.cua_repl={command=%s, args=["--declined-log", %s], '
              'startup_timeout_sec=120, enabled_tools=["js","js_reset","turn_ended"], '
              'omit_tools_from=["code_mode","deferred"], tools={js={output_token_limit=25000}}}'
              % (json.dumps(PROXY), json.dumps(declined_log)))
    off = []
    for feat in OFF_FEATURES:
        off += ["--disable", feat]
    return (["codex", "exec", "--skip-git-repo-check", "-C", workdir, "--sandbox", "read-only",
             "--ephemeral", "-m", MODEL] + off + isolation
            + ["-c", 'web_search="disabled"', "-c", server,
               "--color", "never", "--json", "-o", last_msg, "-"])


def parse_events(out):
    usage, calls, errors, turn_failed, warnings, msgs = {}, 0, [], False, [], []
    for line in out.decode("utf-8", "replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t, it = e.get("type"), e.get("item") or {}
        if t == "turn.completed":
            for k, v in (e.get("usage") or {}).items():
                if isinstance(v, int):
                    usage[k] = usage.get(k, 0) + v
        elif t in ("error", "turn.failed"):
            turn_failed = turn_failed or t == "turn.failed"
            err = e.get("error") if isinstance(e.get("error"), dict) else {}
            errors.append(str(e.get("message") or err.get("message") or json.dumps(e))[:300])
        elif t == "item.completed" and it.get("type") == "mcp_tool_call":
            calls += 1
        elif t == "item.completed" and it.get("type") == "error":
            warnings.append(str(it.get("message", ""))[:120])
        elif t == "item.completed" and it.get("type") == "agent_message":
            msgs.append(str(it.get("text", "")))
    return usage, calls, errors, turn_failed, warnings, msgs


def run(task, timeout, workdir):
    env = {k: v for k, v in os.environ.items() if k not in ("CODEX_API_KEY", "OPENAI_API_KEY")}
    last_msg = os.path.join(workdir, "last.md")
    declined_log = os.path.join(workdir, "declined.jsonl")
    try:
        cli = subprocess.run(["codex", "--version"], capture_output=True, text=True, env=env,
                             timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        cli = "?"
    t0 = time.time()
    isolation, problem = isolation_overrides()
    if problem:
        return finish(task, 2, "failed", "refusing to run without isolation: " + problem, t0,
                      cli, {}, 0, [], "")
    extras, problem = store_extras(APPROVALS_STORE, APPS)
    if problem or extras:
        return finish(task, 2, "failed", "refusing to run: " + (problem or (
            "macOS Computer Use already allows %s for good (an \"Always allow\" given in Codex), "
            "which is not on Zalo's list %s; he adds it to the list or removes that approval"
            % (", ".join(extras), APPS))), t0, cli, {}, 0, [], "")
    try:
        proc = subprocess.Popen(codex_cmd(workdir, last_msg, declined_log, isolation),
                                cwd=workdir, env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError as e:
        return finish(task, 2, "failed", "codex did not start: %s" % e, t0, cli, {}, 0, [], "")
    timed_out = False
    try:
        out, err = proc.communicate((PREAMBLE + task).encode(), timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except (ProcessLookupError, PermissionError):  # macOS: EPERM once it exited
                break
            try:
                proc.wait(timeout=3)
                break
            except subprocess.TimeoutExpired:
                continue
        out, err = proc.communicate()
    usage, calls, errors, turn_failed, warnings, msgs = parse_events(out or b"")
    answer = open(last_msg).read().strip() if os.path.exists(last_msg) else (
        msgs[-1].strip() if msgs else "")
    declined = []
    if os.path.exists(declined_log):
        for line in open(declined_log):
            try:
                declined.append(json.loads(line)["declined"])
            except (ValueError, KeyError):
                pass
    declined = list(dict.fromkeys(declined))
    # a run counts as failed only on a failed turn or a nonzero exit; a top level error
    # event in a run that recovered and answered (a reconnect) is a warning
    failed = bool(proc.returncode) or turn_failed
    fail_text = "\n".join(errors + ([(err or b"").decode("utf-8", "replace")[-2000:]]
                                    if proc.returncode else []))
    if timed_out:
        code, status, why = 2, "failed", "timed out after %d s" % timeout
    elif failed and LIMIT_RE.search(fail_text):
        code, status, why = 3, "limited", "Codex is limited: %s" % (
            errors or [fail_text.strip()])[-1][:200]
    elif declined:
        code, status, why = 2, "failed", ("app not approved: %s. Adding an app to %s is Zalo's "
                                          "call." % (", ".join(declined), APPS))
    elif failed or not answer:
        code, status, why = 2, "failed", ("codex exit %s: %s" % (
            proc.returncode, (errors or [fail_text.strip()[-200:] or "no answer"])[-1][:200]))
    else:
        code, status, why = 0, "done", ""
        warnings = ["Codex reported (recovered): " + e[:100] for e in errors] + warnings
    return finish(task, code, status, why, t0, cli, usage, calls, warnings, answer, declined)


def finish(task, code, status, why, t0, cli, usage, calls, warnings, answer, declined=()):
    secs = round(time.time() - t0, 1)
    if answer:
        print(answer)
    print("computer-use: %s · %.0f s · %d calls · tokens in %s (cached %s) out %s · %s · %s" % (
        status, secs, calls, usage.get("input_tokens", 0), usage.get("cached_input_tokens", 0),
        usage.get("output_tokens", 0), MODEL, cli or "?"))
    if why:
        print("computer-use: " + why)
    for w in warnings:
        print("computer-use: warning: " + w)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "status": status, "exit": code,
           "secs": secs, "calls": calls, "usage": usage, "model": MODEL, "cli": cli,
           "declined": list(declined), "why": why, "task": task[:160],
           "answer": answer[-200:]}
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        print("computer-use: could not write the log %s: %s" % (LOG, e), file=sys.stderr)
    return code


def main(argv):
    task, timeout = parse_args(argv)
    workdir = tempfile.mkdtemp(prefix="computer-use-")
    try:
        return run(task, timeout, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
