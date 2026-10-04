#!/usr/bin/env python3
"""Behaviour suite for computer-use.sh / computer-use.py / computer-use-proxy.py.

Run: python3 ~/.claude/scripts/computer-use.test.py
A fake `codex` first on PATH plays each scenario; no model is called, no app is
driven, and the log goes to a temp file (COMPUTER_USE_LOG).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SH = os.path.join(HERE, "computer-use.sh")
passed = failed = 0
T = tempfile.mkdtemp(prefix="computer-use-test-")


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  ok   %s" % label)
    else:
        failed += 1
        print("  FAIL %s %s" % (label, detail))


FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys, time
d = os.environ["FAKE_DIR"]
if sys.argv[1:] == ["--version"]:
    print("codex-cli 9.9.9-fake"); sys.exit(0)
open(os.path.join(d, "argv.json"), "w").write(json.dumps(sys.argv[1:]))
open(os.path.join(d, "keys.txt"), "w").write(" ".join(
    k for k in ("CODEX_API_KEY", "OPENAI_API_KEY") if os.environ.get(k)))
open(os.path.join(d, "stdin.txt"), "w").write(sys.stdin.read())
open(os.path.join(d, "pid"), "w").write(str(os.getpid()))
last = sys.argv[sys.argv.index("-o") + 1]
declined = re.search(r'"--declined-log", "([^"]+)"', " ".join(sys.argv)).group(1)
sc = os.environ["FAKE_SCENARIO"]
ev = lambda o: print(json.dumps(o), flush=True)
usage = {"input_tokens": 1000, "cached_input_tokens": 600, "cache_write_input_tokens": 0,
         "output_tokens": 50, "reasoning_output_tokens": 5}
ev({"type": "thread.started", "thread_id": "x"})
if sc == "slow":
    time.sleep(60); sys.exit(0)
if sc == "limited":
    ev({"type": "error", "message": "You've hit your usage limit. Try again at 3:00 PM."})
    sys.stderr.write("ERROR: You've hit your usage limit\n"); sys.exit(1)
if sc == "failed":
    ev({"type": "turn.failed", "error": {"message": "stream disconnected before completion"}})
    sys.exit(1)
text = {"done": "The display shows 4,053.\nANSWER: 4053",
        "declined": "Computer Use was not approved to use Google Chrome.\nANSWER: blocked",
        "quote": "The dialog says: You've hit your usage limit (a 429).\nANSWER: read it",
        "noanswer": "",
        "reconnect": "The display shows 144.\nANSWER: 144"}[sc]
if sc == "reconnect":
    ev({"type": "error", "message": "Reconnecting... 1/5 (stream disconnected, 429)"})
if sc == "declined":
    open(declined, "a").write(json.dumps({"declined": "Google Chrome (com.google.Chrome)"}) + "\n")
for i in range(3):
    ev({"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "cua_repl",
                                           "tool": "js", "arguments": {"code": "x"}}})
if text:
    ev({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
    open(last, "w").write(text)
ev({"type": "turn.completed", "usage": usage})
'''


def setup_fake():
    b = os.path.join(T, "bin")
    os.makedirs(b, exist_ok=True)
    p = os.path.join(b, "codex")
    with open(p, "w") as f:
        f.write(FAKE)
    os.chmod(p, 0o755)
    return b


def run(scenario, args, extra_env=None):
    d = os.path.join(T, scenario + str(time.time()))
    os.makedirs(d)
    log = os.path.join(T, "computer-use.log")
    env = dict(os.environ, PATH=BIN + os.pathsep + os.environ["PATH"], FAKE_DIR=d,
               FAKE_SCENARIO=scenario, COMPUTER_USE_LOG=log, CODEX_HOME=CODEX_HOME,
               CODEX_API_KEY="sk-test-should-not-pass", OPENAI_API_KEY="sk-test-should-not-pass")
    env.update(extra_env or {})
    t0 = time.time()
    r = subprocess.run([SH] + args, env=env, capture_output=True, text=True, timeout=120)
    return r, d, log, time.time() - t0


def last_log(log):
    return json.loads(open(log).read().splitlines()[-1])


BIN = setup_fake()
CODEX_HOME = os.path.join(T, "codex-home")
os.makedirs(CODEX_HOME)
with open(os.path.join(CODEX_HOME, "config.toml"), "w") as f:
    f.write('[mcp_servers.playwright]\ncommand = "npx"\n\n[mcp_servers.github]\n'
            'url = "https://x.test/mcp"\n\n[plugins."chrome@openai-bundled"]\nenabled = true\n')
ODD_HOME = os.path.join(T, "codex-home-odd")
os.makedirs(ODD_HOME)
with open(os.path.join(ODD_HOME, "config.toml"), "w") as f:
    f.write('[mcp_servers."my.server"]\ncommand = "npx"\n')

# 1-6: done
r, d, log, _ = run("done", ["In Calculator compute (123+456)*7"])
check("1: done exits 0", r.returncode == 0, r.stdout + r.stderr)
check("2: prints the answer", "ANSWER: 4053" in r.stdout, r.stdout)
check("3: prints the calls and the token usage",
      "computer-use: done" in r.stdout and "3 calls" in r.stdout
      and "tokens in 1000 (cached 600) out 50" in r.stdout and "gpt-6.1-sol" in r.stdout, r.stdout)
rec = last_log(log)
check("4: logs one JSON line with status, calls and usage",
      rec["status"] == "done" and rec["exit"] == 0 and rec["calls"] == 3
      and rec["usage"]["input_tokens"] == 1000, rec)
check("5: no API key reaches codex (ChatGPT login)", open(os.path.join(d, "keys.txt")).read() == "",
      open(os.path.join(d, "keys.txt")).read())
argv = json.loads(open(os.path.join(d, "argv.json")).read())
joined = " ".join(argv)
check("6: codex exec runs gpt-6.1-sol read only, ephemeral, shell/exec/multi agent off, --json",
      argv[0] == "exec" and argv[argv.index("-m") + 1] == "gpt-6.1-sol"
      and argv[argv.index("--sandbox") + 1] == "read-only" and "--ephemeral" in argv
      and "--json" in argv and all(f in joined for f in (
          "--disable shell_tool", "--disable unified_exec", "--disable multi_agent")), joined)
check("7: the Computer Use server is the proxy, and no allow list path is passed to it",
      "computer-use-proxy.py" in joined and "--apps" not in joined
      and "plugins.unified-computer-use@openai-bundled.enabled=false" in joined, joined)
check("7b: every other MCP server and plugin in config.toml is switched off, bare keys",
      "mcp_servers.playwright.enabled=false" in joined
      and "mcp_servers.github.enabled=false" in joined
      and "plugins.chrome@openai-bundled.enabled=false" in joined
      and "plugins.unified-computer-use@openai-bundled.enabled=false" in joined
      and "cua_repl.enabled=false" not in joined and '."' not in joined.split("-c mcp_servers.cua_repl")[0],
      joined)
r_odd, d_odd, _, _ = run("done", ["x"], {"CODEX_HOME": ODD_HOME})
check("7e: a server name codex -c cannot address makes the run refuse (fail closed)",
      r_odd.returncode == 2 and "refusing to run without isolation" in r_odd.stdout
      and not os.path.exists(os.path.join(d_odd, "argv.json")), r_odd.stdout)
check("7c: apps, browser use, image generation and web search are off",
      all(f in joined for f in ("--disable apps", "--disable browser_use",
                                 "--disable in_app_browser", "--disable image_generation",
                                 'web_search="disabled"')), joined)
check("7d: the run's temp dir is removed afterwards",
      not os.path.exists(argv[argv.index("-C") + 1]), argv[argv.index("-C") + 1])
check("8: the task reaches the model behind the preamble",
      open(os.path.join(d, "stdin.txt")).read().endswith("Task: In Calculator compute (123+456)*7"))

# 9-10: failed and limited
r, d, log, _ = run("failed", ["x"])
check("9: a codex error exits 2", r.returncode == 2 and "computer-use: failed" in r.stdout
      and "stream disconnected" in r.stdout, r.stdout)
r, d, log, _ = run("limited", ["x"])
check("10: a usage limit exits 3 and says so", r.returncode == 3
      and "Codex is limited" in r.stdout and last_log(log)["status"] == "limited", r.stdout)

# 11: an answer that QUOTES a limit is not a limit (failure channel only)
r, d, log, _ = run("quote", ["read the dialog"])
check("11: an answer quoting 'usage limit' still exits 0", r.returncode == 0, r.stdout)

# 12-13: a declined app
r, d, log, _ = run("declined", ["open Chrome"])
check("12: a declined app exits 2 and names the app", r.returncode == 2
      and "app not approved: Google Chrome (com.google.Chrome)" in r.stdout
      and "Zalo's call" in r.stdout, r.stdout)
check("13: the log names the declined app",
      last_log(log)["declined"] == ["Google Chrome (com.google.Chrome)"], last_log(log))

# 14-15: the time cap
r, d, log, secs = run("slow", ["x", "--timeout", "2"])
pid = int(open(os.path.join(d, "pid")).read())
try:
    os.kill(pid, 0)
    alive = True
except ProcessLookupError:
    alive = False
check("14: the time cap stops the run: exit 2, 'timed out', well under the fake's 60 s",
      r.returncode == 2 and "timed out after 2 s" in r.stdout and secs < 15, "%s %.1fs" % (
          r.stdout, secs))
check("15: the timed out codex process is killed", not alive)

# 16-18: arguments
tf = os.path.join(T, "task.md")
open(tf, "w").write("In Calculator compute 2+2\n")
r, d, log, _ = run("done", ["--file", tf])
check("16: --file reads the task", r.returncode == 0 and open(os.path.join(
    d, "stdin.txt")).read().endswith("Task: In Calculator compute 2+2"))
r, _, _, _ = run("done", [])
check("17: no task exits nonzero with the usage", r.returncode != 0 and "usage:" in r.stderr,
      r.stderr)
r, d, log, _ = run("reconnect", ["x"])
check("18a: a recovered error event (even one naming 429) with an answer exits 0, as a warning",
      r.returncode == 0 and "recovered" in r.stdout, r.stdout)
r, d, log, _ = run("done", ["x"], {"COMPUTER_USE_APPS": "/tmp/evil-apps.json"})
check("18b: COMPUTER_USE_APPS has no effect (the list path is fixed)",
      "evil-apps" not in open(os.path.join(d, "argv.json")).read())
for label, args in (("a missing --file", ["--file", "/nonexistent/task.md"]),
                    ("a bad --timeout", ["x", "--timeout", "abc"])):
    r, _, _, _ = run("done", args)
    check("18c: %s exits 2 with a message, no traceback" % label,
          r.returncode == 2 and "Traceback" not in r.stderr and "usage:" in r.stderr, r.stderr)
r, d, log, _ = run("noanswer", ["x"])
check("18: a run with no answer exits 2", r.returncode == 2, r.stdout)
r, d, _, _ = run("done", ["x", "--timeout", "9999"])
check("19: --timeout is clamped under the 600 s Bash ceiling", r.returncode == 0)

# 20-27: the proxy's decision
spec = importlib.util.spec_from_file_location("cup", os.path.join(HERE, "computer-use-proxy.py"))
cup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cup)
apps = cup.load_apps(os.path.expanduser("~/.claude/config/computer-use-apps.json"))


def ask(name, bundle):
    p = {"message": 'Allow Computer Use to use "%s"?' % name, "mode": "form"}
    if bundle is not None:
        p["_meta"] = {"tool_params": {"app": bundle}}
    return cup.decide(p, apps)


check("20: the seeded list is exactly Calculator, TextEdit, Finder, Preview",
      sorted(apps.values()) == ["Calculator", "Finder", "Preview", "TextEdit"], apps)
check("21: an allowed app (TextEdit) is accepted", ask("TextEdit", "com.apple.TextEdit")[0] == "accept")
check("22: the bundle id match ignores case", ask("Calculator", "COM.APPLE.CALCULATOR")[0] == "accept")
for n, (name, bundle) in enumerate((("Google Chrome", "com.google.Chrome"),
                                    ("Safari", "com.apple.Safari"), ("Messages", "com.apple.MobileSMS"),
                                    ("Terminal", "com.apple.Terminal")), start=23):
    ok, label = ask(name, bundle)
    check("%d: %s is declined and named" % (n, name), ok == "decline" and name in label, label)
check("27: a display name alone, with no bundle id, is declined",
      ask("TextEdit", None)[0] == "decline")
check("28: any other elicitation goes on to Codex (it answers the JS review itself)",
      cup.decide({"message": "Review JavaScript execution: Select Calculator"}, apps)[0]
      == "forward" and cup.decide({"message": "Allow Computer Use to record computer audio?"},
                                  apps)[0] == "forward")
check("29: an unreadable allow list allows nothing", cup.load_apps(os.path.join(T, "nope")) == {})

# 30-34: the native approvals store must not allow more than Zalo's list
spec2 = importlib.util.spec_from_file_location("cupy", os.path.join(HERE, "computer-use.py"))
cupy = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(cupy)
lst = os.path.join(T, "list.json")
with open(lst, "w") as f:
    json.dump({"apps": [{"name": "Calculator", "bundle_id": "com.apple.calculator"}]}, f)
store = os.path.join(T, "store.json")
with open(store, "w") as f:
    json.dump({"approvedBundleIdentifiers": ["com.apple.calculator"]}, f)
check("30: a store inside the list is fine", cupy.store_extras(store, lst) == ([], None))
with open(store, "w") as f:
    json.dump({"approvedBundleIdentifiers": ["com.apple.Calculator", "com.google.Chrome"]}, f)
check("31: a store app missing from the list is named (case ignored for the rest)",
      cupy.store_extras(store, lst) == (["com.google.Chrome"], None), cupy.store_extras(store, lst))
check("32: no store file is fine", cupy.store_extras(os.path.join(T, "none"), lst) == ([], None))
with open(store, "w") as f:
    f.write("{broken")
check("33: an unreadable store fails closed", cupy.store_extras(store, lst)[1] is not None)
check("34: the list and the store paths follow the account home, not $HOME",
      cupy.APPS.startswith(cupy.REAL_HOME) and cupy.APPROVALS_STORE.startswith(cupy.REAL_HOME)
      and "Group Containers" in cupy.APPROVALS_STORE and "computer-use-apps" in cupy.APPS)

shutil.rmtree(T, ignore_errors=True)
print("\n%d/%d passed, %d failed" % (passed, passed + failed, failed))
sys.exit(1 if failed else 0)
