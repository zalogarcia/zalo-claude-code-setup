#!/usr/bin/env python3
"""Behaviour suite for social-load-audit.py. Run: python3 ~/.claude/scripts/social-load-audit.test.py

Builds fixture Chrome History databases (the real schema's visits and urls
columns) in a temp dir: a Default profile, a Blueprint profile and a Playwright
profile, plus a fixture gate ledger, then runs the audit's core with a fixed
clock and a fake Telegram sender. Nothing here reads a real History file or
sends a message.
"""
import argparse
import importlib.util
import json
import os
import random
import sqlite3
import sys
import tempfile
import time

AUD = os.path.expanduser("~/.claude/scripts/social-load-audit.py")
GATE = os.path.expanduser("~/.claude/scripts/social-gate.py")
REAL_CFG = os.path.expanduser("~/.claude/config/social-pacing.json")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


au = load("audit", AUD)
sg = load("gate", GATE)
cfg = sg.load_config(REAL_CFG)
T = tempfile.mkdtemp(prefix="sla-test-")
OFF = au.WEBKIT_EPOCH_OFFSET
NOW = 1790460000.0  # 2026-09-26 18:00 EDT
PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % label)
    else:
        FAIL += 1
        print("  FAIL  %s %s" % (label, detail))


def platform_of(url):
    return sg.platform_of_host(sg.host_of(url), cfg) if url else None


def make_history(path, visits):
    """visits: [(epoch, url, transition, from_index or None, origin guid)]"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE urls(id INTEGER PRIMARY KEY AUTOINCREMENT, url LONGVARCHAR, "
                "title LONGVARCHAR, visit_count INTEGER DEFAULT 0 NOT NULL, typed_count "
                "INTEGER DEFAULT 0 NOT NULL, last_visit_time INTEGER NOT NULL, hidden "
                "INTEGER DEFAULT 0 NOT NULL)")
    con.execute("CREATE TABLE visits(id INTEGER PRIMARY KEY AUTOINCREMENT, url INTEGER NOT "
                "NULL, visit_time INTEGER NOT NULL, from_visit INTEGER, transition INTEGER "
                "DEFAULT 0 NOT NULL, segment_id INTEGER, visit_duration INTEGER DEFAULT 0 NOT "
                "NULL, originator_cache_guid TEXT)")
    ids = []
    for t, url, tr, frm, origin in visits:
        cur = con.execute("INSERT INTO urls(url, title, last_visit_time) VALUES (?, ?, ?)",
                          (url, "a title", int((t + OFF) * 1e6)))
        cur = con.execute("INSERT INTO visits(url, visit_time, from_visit, transition, "
                          "originator_cache_guid) VALUES (?, ?, ?, ?, ?)",
                          (cur.lastrowid, int((t + OFF) * 1e6),
                           ids[frm] if frm is not None else 0, tr, origin))
        ids.append(cur.lastrowid)
    con.commit()
    con.close()


LINK, TYPED, SUB = 0, 1, 3
SERVER_REDIRECT_CHAIN_END = (0x80000000 | 0x20000000) - (1 << 32)  # stored signed, as Chrome does
FBP = "https://www.facebook.com/people/Some-Person/1000"

# Default profile: 20 facebook loads spread over 5 hours (fine), 3 subframes, one synced
# visit from a phone, one linkedin load, one non social page.
default = []
for i in range(20):
    default.append((NOW - 5 * 3600 + i * 900, FBP + str(i), LINK, None, ""))
for i in range(3):
    default.append((NOW - 3600 + i, "https://www.facebook.com/plugins/like.php", SUB, None, ""))
default.append((NOW - 1800, "https://www.facebook.com/x", LINK, None, "phone-guid"))
default.append((NOW - 1700, "https://www.linkedin.com/in/someone", TYPED, None, ""))
default.append((NOW - 1600, "https://example.com/page", LINK, None, ""))
make_history(os.path.join(T, "chrome", "Default", "History"), default)

# Blueprint profile: the incident shape, 60 facebook profiles in 30 minutes, each one
# redirected to the login wall (the redirect must NOT double count).
bp = []
for i in range(60):
    t = NOW - 7200 + i * 30
    bp.append((t, "https://www.facebook.com/p%d" % i, LINK, None, ""))
    bp.append((t + 1, "https://www.facebook.com/login/?next=x", SERVER_REDIRECT_CHAIN_END,
               len(bp) - 1, ""))
make_history(os.path.join(T, "blueprint", "Default", "History"), bp)

# Playwright profile: 2 instagram loads
make_history(os.path.join(T, "pw", "Default", "History"), [
    (NOW - 600, "https://www.instagram.com/a/", LINK, None, ""),
    (NOW - 500, "https://www.instagram.com/b/", LINK, None, "")])

SOURCES = [("chrome:Default", os.path.join(T, "chrome", "Default", "History")),
           ("blueprint", os.path.join(T, "blueprint", "Default", "History")),
           ("playwright", os.path.join(T, "pw", "Default", "History"))]
LEDGER = [{"ts": NOW - 4000 + k, "platform": "facebook", "route": "remote"} for k in range(5)]


class Sender:
    def __init__(self, ok=True):
        self.sent = []
        self.ok = ok

    def __call__(self, text):
        self.sent.append(text)
        return self.ok, "sent" if self.ok else "failed"


def args(**kw):
    a = argparse.Namespace(hours=24.0, json=False, alert=False, dry_run=False)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


print("A  counting")
state = os.path.join(T, "state")
rep, text = au.run(args(), cfg, SOURCES, LEDGER, NOW, platform_of, state, Sender())
fb = rep["platforms"]["facebook"]
ok(rep["sources"]["chrome:Default"]["facebook"] == 20, "Default: 20 facebook loads "
   "(subframes and the synced phone visit excluded)", str(rep["sources"]))
ok(rep["synced_excluded"] == 1, "one synced visit reported as excluded")
ok(rep["sources"]["blueprint"]["facebook"] == 60, "Blueprint: 60 loads, the login wall "
   "redirects not double counted", str(rep["sources"].get("blueprint")))
ok(fb["browser"] == 80 and fb["ledger_remote"] == 5, "facebook machine total 80, remote 5")
ok(rep["platforms"]["linkedin"]["browser"] == 1, "linkedin counted on its own")
ok(rep["platforms"]["instagram"]["browser"] == 2 and
   rep["sources"]["playwright"]["instagram"] == 2, "Playwright profile counted")
ok(fb["worst_hour"] == 64, "worst rolling hour: the 60 Blueprint loads plus the 4 Default "
   "loads in the same hour", str(fb["worst_hour"]))
ok("example.com" not in json.dumps(rep["platforms"]), "non social pages are not counted")

print("B  flags")
kinds = sorted((f["platform"], f["kind"]) for f in rep["flags"])
ok(("facebook", "hour") in kinds, "facebook rolling hour over 40 is flagged", str(kinds))
ok(("facebook", "blueprint") in kinds, "ANY Blueprint social visit is flagged")
ok(("facebook", "day") not in kinds, "80 in a day is under 150, not flagged")
ok(not any(p in ("linkedin", "instagram") for p, _ in kinds), "quiet platforms not flagged")
calm = [s for s in SOURCES if s[0] != "blueprint"]
rep2, _ = au.run(args(), cfg, calm, [], NOW, platform_of, state, Sender())
ok(rep2["flags"] == [], "without the Blueprint burst nothing is over a cap",
   str(rep2["flags"]))
many = [(NOW - 63900 + i * 400, FBP + "x%d" % i, LINK, None, "") for i in range(160)]  # 00:15 on
make_history(os.path.join(T, "busy", "Default", "History"), many)
rep3, _ = au.run(args(), cfg, [("chrome:Default", os.path.join(T, "busy", "Default",
                                                                "History"))], [], NOW,
                 platform_of, state, Sender())
ok(any(f["kind"] == "day" and f["count"] == 160 for f in rep3["flags"]),
   "160 loads in one local day is flagged over 150", str(rep3["flags"]))
ok(not any(f["kind"] == "hour" for f in rep3["flags"]),
   "one every 400 s never crosses 40 an hour")
led = [{"ts": NOW - 3000 + k * 10, "platform": "linkedin", "route": "local"} for k in range(45)]
rep4, _ = au.run(args(), cfg, [], led, NOW, platform_of, state, Sender())
ok(any(f["platform"] == "linkedin" and f["kind"] == "hour" for f in rep4["flags"]),
   "the gate ledger alone can trip the hourly flag (curl loads no browser sees)")

t0u = NOW - 3300
bro = [(t0u + k * 60, FBP + "u%d" % k, LINK, None, "") for k in range(25)]
make_history(os.path.join(T, "union", "Default", "History"), bro)
# gated curls that start 200 s after the last browser visit: no visit can explain them
curl_rows = [{"ts": t0u + 1640 + k * 60, "platform": "facebook", "route": "local",
              "actor": "worker", "via": "cli"} for k in range(25)]
gated_rows = [{"ts": t0u + k * 60 - 2, "platform": "facebook", "route": "local",
               "actor": "hook:abc", "via": "hook:mcp__playwright__browser_navigate"}
              for k in range(25)]
src_u = [("chrome:Default", os.path.join(T, "union", "Default", "History"))]
rep5, _ = au.run(args(), cfg, src_u, gated_rows, NOW, platform_of, state, Sender())
ok(rep5["platforms"]["facebook"]["machine"] == 25,
   "25 gated browser loads (ledger row plus visit) count once: 25",
   str(rep5["platforms"]["facebook"]["machine"]))
rep6, _ = au.run(args(), cfg, src_u, curl_rows, NOW, platform_of, state, Sender())
ok(rep6["platforms"]["facebook"]["machine"] == 50 and any(
    f["kind"] == "hour" for f in rep6["flags"]),
   "25 browser loads plus 25 disjoint gated curls count as 50 and trip the hour (QA round 2)",
   "%s %s" % (rep6["platforms"]["facebook"]["machine"], rep6["flags"]))
# QA round 3: curl and Python rows interleaved with ungated browsing (each row lands
# 300 s after a visit, inside the next visits' match window) must not eat those visits
inter = [{"ts": t0u + k * 60 + 300, "platform": "facebook", "route": "local", "actor": a,
          "via": v} for k, (a, v) in enumerate([("owner-resolver", "python"),
                                                 ("worker", "cli")] * 12 + [("m", "cli")])]
rep7, _ = au.run(args(), cfg, src_u, inter, NOW, platform_of, state, Sender())
ok(rep7["platforms"]["facebook"]["machine"] == 50,
   "25 visits plus 25 interleaved curl or Python rows count as 50 (QA round 3)",
   str(rep7["platforms"]["facebook"]["machine"]))
kinds = [({"via": "hook:mcp__playwright__browser_navigate", "actor": "hook:abc"}, True),
         ({"via": "cli", "actor": "astra"}, True), ({"via": "python", "actor": "jev"}, True),
         ({"via": "cli", "actor": "worker", "grant": True}, True),
         ({"via": "cli", "actor": "worker"}, False),
         ({"via": "python", "actor": "owner-resolver"}, False)]
ok(all(au.is_browser_row(r) == want for r, want in kinds),
   "hook rows, grants, Astra and Jev pair with History; curl and tool rows never do",
   str([(r, au.is_browser_row(r)) for r, _ in kinds]))
g = sg.Gate(config_path=REAL_CFG, state_dir=os.path.join(T, "gstate"),
            clock=sg.FakeClock(NOW), rng=random.Random(1))
g.acquire("https://www.facebook.com/x", "worker", grant=True)
ok(json.loads(open(g.ledger_path).read().splitlines()[-1]).get("grant") is True,
   "the gate marks a --grant row, so the audit can pair it")

print("C  output carries counts only")
for s in (text, json.dumps(rep, default=str)):
    ok("people" not in s and "/p1" not in s and "login" not in s and "a title" not in s,
       "no URL path or title in the output")

print("D  alerts")
snd = Sender()
st = os.path.join(T, "state-alert")
r, out = au.run(args(alert=True), cfg, SOURCES, LEDGER, NOW, platform_of, st, snd)
ok(len(snd.sent) == 1, "one Telegram message for the crossings", str(snd.sent))
msg = snd.sent[0] if snd.sent else ""
ok("Blueprint" in msg and "facebook" in msg and "http" not in msg,
   "the line names the crossing, no URL", msg)
ok(u"—" not in msg and u"–" not in msg, "no em or en dashes in the alert")
r, out = au.run(args(alert=True), cfg, SOURCES, LEDGER, NOW + 60, platform_of, st, snd)
ok(len(snd.sent) == 1 and "already alerted" in out, "the same crossing is not re-sent")
snd2 = Sender()
au.run(args(alert=True), cfg, calm, [], NOW, platform_of, os.path.join(T, "s3"), snd2)
ok(snd2.sent == [], "nothing over a cap: nothing sent")
snd3 = Sender(ok=False)
st4 = os.path.join(T, "s4")
au.run(args(alert=True), cfg, SOURCES, LEDGER, NOW, platform_of, st4, snd3)
snd4 = Sender()
au.run(args(alert=True), cfg, SOURCES, LEDGER, NOW, platform_of, st4, snd4)
ok(len(snd4.sent) == 1, "a failed send is retried on the next run")
snd5 = Sender()
r, out = au.run(args(alert=True, dry_run=True), cfg, SOURCES, LEDGER, NOW, platform_of,
                os.path.join(T, "s5"), snd5)
ok(snd5.sent == [] and "WOULD SEND" in out, "--dry-run prints and never sends")

print("E  read only, copy first")
live = SOURCES[1][1]
before = (os.path.getmtime(live), os.path.getsize(live))
au.run(args(), cfg, SOURCES, LEDGER, NOW, platform_of, state, Sender())
ok((os.path.getmtime(live), os.path.getsize(live)) == before, "the source History file is "
   "untouched")
src = open(AUD).read()
ok("mode=ro&immutable=1" in src and "copyfile" in src, "opens only a copy, read only")

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
