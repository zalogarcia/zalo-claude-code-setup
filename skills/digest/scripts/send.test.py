#!/usr/bin/env python3
"""Tests for send.py (dry runs only: nothing reaches Telegram). Run: python3 send.test.py"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "send.py")
spec = importlib.util.spec_from_file_location("send", SCRIPT)
send = importlib.util.module_from_spec(spec)
spec.loader.exec_module(send)
TMP = tempfile.mkdtemp(prefix="digest-send-test-")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL %s %s" % (name, detail))


def f(name, body, mode="w"):
    p = os.path.join(TMP, name)
    with open(p, mode) as fh:
        fh.write(body)
    return p


def run(*args, env=None):
    e = dict(os.environ)
    e["DIGEST_TG_THROTTLE"] = os.path.join(TMP, "no-throttle.json")
    e.update(env or {})
    return subprocess.run([sys.executable, SCRIPT] + list(args) + ["--dry-run"], capture_output=True, text=True, env=e)


good = f("good.txt", "The job runs every minute.\n\n1. The page sends the form.\n2. The API makes a session.\n")
# a 1080x3247 PNG header is enough for the size probe
png = f("d.png", b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (1080).to_bytes(4, "big") + (3247).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00", "wb")
tall = f("tall.png", b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (400).to_bytes(4, "big") + (9900).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00", "wb")
page = f("p.html", "<p>x</p>")

r = run("--text", good, "--photo", png, "--caption", "The flow")
lines = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
check("01 text first, then the photo", r.returncode == 0 and [l["method"] for l in lines] == ["sendMessage", "sendPhoto"], r.stdout + r.stderr)
r = run("--text", good, "--photo", png, "--document", page)
check("02 two extras refused", r.returncode == 2 and "one extra only" in r.stderr)
r = run("--text", f("dash.txt", "The job runs — every minute.\n"))
check("03 em dash refused", r.returncode == 1 and "dash" in r.stderr)
r = run("--text", good, "--photo", png, "--caption", "a – b")
check("04 dash in caption refused", r.returncode == 1)
bad = f("bad.txt", "We utilize the API.\n")
r = run("--text", bad)
check("05 lint findings block", r.returncode == 1 and "ste-lint" in r.stderr)
r = run("--text", bad, "--allow-lint-findings")
check("06 lint override sends", r.returncode == 0)
r = run("--text", good, "--document", page, "--shot", png)
lines = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
check("07 page order: text, document, screenshot", [l["method"] for l in lines] == ["sendMessage", "sendDocument", "sendPhoto"], r.stdout)
r = run("--text", good, "--photo", tall)
lines = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
check("08 too-tall photo goes as a document", [l["method"] for l in lines] == ["sendMessage", "sendDocument"], r.stdout)
th = f("throttle.json", json.dumps({"until": int(time.time() * 1000) + 600000}))
r = run("--text", good, env={"DIGEST_TG_THROTTLE": th})
check("09 throttled exits 3", r.returncode == 3 and "throttling" in r.stderr, r.stderr)
r = run("--text", f("empty.txt", "  \n"))
check("10 empty text refused", r.returncode == 1)
r = run("--text", good, "--shot", png)
check("11 shot without a page refused", r.returncode == 2)
r = run("--text", os.path.join(TMP, "missing.txt"))
check("12 missing file exit 2", r.returncode == 2)
parts = send.chunks("\n\n".join(["word " * 300] * 5), limit=4000)
check("13 long text splits on paragraphs", len(parts) == 3 and all(len(p) <= 4000 for p in parts), [len(p) for p in parts])
src = open(SCRIPT).read()
check("14 never edits a message", "editMessage" not in src.replace("never edits a message", ""))

check("15 echo matches", send.echo_ok({"caption": "a; b"}, {"caption": "a; b"}))
check("16 cut caption fails", not send.echo_ok({"caption": "web live; the app"}, {"caption": "web live"}))
check("17 text echo compared", not send.echo_ok({"text": "one two"}, {"text": "one"}))

# 18. a file path with , or ; is quoted for curl -F
captured = {}
class _R:
    stdout = '{"ok": true, "result": {"message_id": 1}}'
    stderr = ""
def _fake_run(cmd, **kw):
    captured["cmd"], captured["input"] = cmd, kw.get("input", "")
    return _R()
_orig = send.subprocess.run
send.subprocess.run = _fake_run
try:
    send.call("FAKETOKEN", "sendPhoto", {"chat_id": "1"}, {"photo": "/tmp/a,b;c.png"})
finally:
    send.subprocess.run = _orig
check("18 path quoted for curl -F", 'photo=@"/tmp/a,b;c.png"' in captured["cmd"], captured.get("cmd"))
check("19 token only on stdin", "FAKETOKEN" not in " ".join(captured["cmd"]) and "FAKETOKEN" in captured["input"])

# QA round 3 regressions
r = run("--text", good, "--document", page, "--shot", tall)
lines = [json.loads(l) for l in r.stdout.splitlines() if l.startswith("{")]
check("20 too-tall shot goes as a document", [l["method"] for l in lines] == ["sendMessage", "sendDocument", "sendDocument"], r.stdout)
r = run("--text", good, "--photo", png, "--caption", "x" * 1025)
check("21 caption over 1024 refused before any send", r.returncode == 1 and "1024" in r.stderr and "sendMessage" not in r.stdout)

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
