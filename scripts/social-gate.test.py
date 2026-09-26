#!/usr/bin/env python3
"""Behaviour suite for social-gate.py. Run: python3 ~/.claude/scripts/social-gate.test.py

Offline. Nothing here loads a page and nothing touches the real ledger: every
Gate is built on a temp state dir. The config is a COPY of the real one (so the
real numbers are what gets proven), with the gap model path kept as is.

Sections
  A  host classification (subdomains, look alikes, bare hosts)
  B  one platform, fake clock, 200 requests at the real numbers: gap floor,
     rolling hour cap, daily cap, refusals, day rollover
  C  the gap is not uniform: many distinct values, heavy right tail, positive
     lag 1 autocorrelation of the log gaps (the governor's property)
  D  budgets are per platform and per route
  E  two real processes racing on one ledger: the gap and the hourly cap hold
     across processes (the file lock)
  F  fail closed: missing gap model, unreadable config, torn ledger line,
     corrupt state file, bad actor, no env override in the CLI
  G  grants: one slot, one use, expiry
  H  the day boundary ignores the TZ variable
"""
import importlib.util
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

GATE = os.path.expanduser("~/.claude/scripts/social-gate.py")
REAL_CFG = os.path.expanduser("~/.claude/config/social-pacing.json")

spec = importlib.util.spec_from_file_location("social_gate", GATE)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)

PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % label)
    else:
        FAIL += 1
        print("  FAIL  %s %s" % (label, detail))


def tmp_cfg(**overrides):
    d = tempfile.mkdtemp(prefix="sg-test-")
    cfg = json.load(open(REAL_CFG))
    for route, vals in overrides.items():
        cfg["routes"][route].update(vals)
    path = os.path.join(d, "cfg.json")
    json.dump(cfg, open(path, "w"))
    return d, path


def new_gate(start=None, seed=1, **overrides):
    d, path = tmp_cfg(**overrides)
    clk = sg.FakeClock(start or 1790380800.0)  # 2026-09-26 00:00 local-ish
    return sg.Gate(config_path=path, state_dir=os.path.join(d, "state"), clock=clk,
                   rng=random.Random(seed)), clk, d


def ledger(gate):
    if not os.path.exists(gate.ledger_path):
        return []
    return [json.loads(line) for line in open(gate.ledger_path) if line.strip()]


FB = "https://www.facebook.com/some.person.123"

# ---------------------------------------------------------------- A
print("A  host classification")
cfg = sg.load_config(REAL_CFG)
cases = [
    ("https://www.facebook.com/x", "facebook"), ("m.facebook.com", "facebook"),
    ("https://fb.com/x", "facebook"), ("https://www.messenger.com/t/1", "facebook"),
    ("https://instagram.com/x", "instagram"), ("https://www.linkedin.com/in/x", "linkedin"),
    ("https://x.com/x", "x"), ("https://mobile.twitter.com/x", "x"),
    ("https://www.tiktok.com/@x", "tiktok"), ("https://www.threads.net/@x", "threads"),
    ("https://www.threads.com/@x", "threads"), ("HTTPS://WWW.FACEBOOK.COM/X", "facebook"),
    ("https://notfacebook.com/x", None), ("https://box.com/x", None),
    ("https://facebook.com.evil.org/x", None), ("https://example.com/?u=facebook.com", None),
    ("https://www.facebook.com:443/x", "facebook"),
]
for url, want in cases:
    got = sg.platform_of_host(sg.host_of(url), cfg)
    ok(got == want, "platform_of %s -> %s" % (url, want), "got %r" % got)
found = sg.find_social_hosts(
    "curl https://m.facebook.com/x notfacebook.com box.com mobile.x.com "
    "facebook.com.evil.org fb.com/y sfb.com graph.facebook.com", cfg)
ok([h for _, h in found] == ["m.facebook.com", "mobile.x.com", "fb.com"],
   "find_social_hosts skips look alikes and API hosts", str(found))
for api in ("https://graph.facebook.com/v21.0/act_1/insights", "https://api.linkedin.com/v2/me",
            "https://graph.instagram.com/me"):
    ok(sg.platform_of_host(sg.host_of(api), cfg) is None, "API host is not a page: %s" % api)

# ---------------------------------------------------------------- B
print("B  fake clock, 200 requests at the real numbers (facebook, local)")
g, clk, d = new_gate(seed=11)
codes = []
for i in range(200):
    r = g.acquire(FB, "test", "local", max_wait=10 ** 6)
    codes.append(r.code)
    if r.code in (sg.WAIT, sg.HOUR_FULL, sg.DAY_FULL):
        clk.t = r.retry_at  # the caller comes back when told
rows = ledger(g)
ts = [r["ts"] for r in rows]
gaps = [b - a for a, b in zip(ts, ts[1:])]
ok(len(rows) == codes.count(sg.OK), "every OK wrote exactly one ledger row",
   "%d rows, %d OK" % (len(rows), codes.count(sg.OK)))
ok(min(gaps) >= 45.0 - 1e-6, "no two loads closer than 45 s", "min %.2f" % min(gaps))
worst_hour = max(sum(1 for u in ts if t0 <= u < t0 + 3600) for t0 in ts)
ok(worst_hour <= 40, "no rolling hour holds more than 40 loads", "worst %d" % worst_hour)
by_day = {}
for t in ts:
    by_day.setdefault(g.day_start(t), 0)
    by_day[g.day_start(t)] += 1
ok(max(by_day.values()) <= 150, "no local day holds more than 150", str(by_day))
ok(set(r["host"] for r in rows) == {"www.facebook.com"} and all(
    "/" not in r["host"] for r in rows), "ledger keeps the host only, never the path")
ok(all(set(r) >= {"ts", "platform", "route", "actor", "host", "via"} for r in rows),
   "ledger rows carry time, platform, route, actor, host, via")
print("     %d requests: %d OK, %d wait, %d hour full, %d day full; gaps min %.0f "
      "median %.0f mean %.0f max %.0f s" % (
          len(codes), codes.count(0), codes.count(3), codes.count(4), codes.count(5),
          min(gaps), statistics.median(gaps), statistics.mean(gaps), max(gaps)))

# hammer the daily cap directly: tiny gap, no hourly cap, 200 requests in a day
g2, clk2, _ = new_gate(seed=3, local={"min_gap_s": 1, "per_hour": 0})
clk2.t = g2.day_start(clk2.t) + 3600  # 01:00 local
c2 = []
for i in range(200):
    r = g2.acquire(FB, "test", max_wait=10 ** 6)
    c2.append(r.code)
    if r.code == sg.WAIT:
        clk2.t = r.retry_at
    if r.code == sg.DAY_FULL:
        break
ok(c2.count(sg.OK) == 150 and c2[-1] == sg.DAY_FULL,
   "daily cap: exactly 150 granted, then exit 5", "%d OK, last %d" % (c2.count(0), c2[-1]))
r = g2.acquire(FB, "test", max_wait=0)
ok(r.code == sg.DAY_FULL and len(ledger(g2)) == 150, "a refused call writes nothing")
ok(r.retry_at == g2.next_day_start(clk2.t), "day refusal points at local midnight")
clk2.t = r.retry_at + 1
r = g2.acquire(FB, "test", max_wait=10 ** 6)
ok(r.code == sg.OK, "a new local day opens a fresh budget", "code %d" % r.code)

# the hourly cap refuses immediately, it does not queue
g3, clk3, _ = new_gate(seed=5, local={"min_gap_s": 1, "per_hour": 5})
c3 = []
for i in range(8):
    r = g3.acquire(FB, "test", max_wait=10 ** 6)
    c3.append(r.code)
    if r.code == sg.WAIT:
        clk3.t = r.retry_at
before = list(clk3.slept)
r = g3.acquire(FB, "test", max_wait=10 ** 6)
ok(c3.count(sg.OK) == 5 and r.code == sg.HOUR_FULL, "hourly cap: 5 granted then exit 4",
   str(c3))
ok(clk3.slept == before, "a full hour refuses at once, no sleeping toward it")
ok(r.retry_at and r.retry_at > clk3.t, "hour refusal names when a slot frees")

# check never writes
g4, clk4, _ = new_gate()
r = g4.check(FB)
ok(r.code == sg.OK and ledger(g4) == [], "check on a fresh budget: 0, nothing written")
g4.acquire(FB, "test")
r = g4.check(FB)
ok(r.code == sg.WAIT and r.wait_s >= 45 and len(ledger(g4)) == 1,
   "check right after a load: exit 3 with the wait, nothing written",
   "code %d wait %.1f" % (r.code, r.wait_s))
r = g4.acquire(FB, "test", max_wait=0)
ok(r.code == sg.WAIT and len(ledger(g4)) == 1, "acquire with --max-wait 0 does not wait")
g5w, c5w, _ = new_gate()
g5w.acquire(FB, "test")
st = json.load(open(g5w.state_path))
st["facebook/local"]["next_at"] = c5w.t + 1000
json.dump(st, open(g5w.state_path, "w"))
t0w = c5w.t
r = g5w.acquire(FB, "test", max_wait=300)
ok(r.code == sg.WAIT and abs((c5w.t - t0w) - 300) < 1e-6 and 699 < r.wait_s < 701,
   "a gap longer than --max-wait: the call waits its full 300 s, then exits 3 with ~700 s left",
   "slept %.0f wait %.0f" % (c5w.t - t0w, r.wait_s))
for _ in range(2):
    r = g5w.acquire(FB, "test", max_wait=300)
ok(r.code == sg.WAIT, "after three calls (900 s) a 1000 s gap is still running")
r = g5w.acquire(FB, "test", max_wait=300)
ok(r.code == sg.OK and abs((c5w.t - t0w) - 1000) < 1e-6,
   "the fourth call gets the slot exactly when the 1000 s gap ends", "code %d" % r.code)
r = g4.acquire("https://example.com/x", "test")
ok(r.code == sg.OK and not r.social and len(ledger(g4)) == 1,
   "a non social URL passes and is not logged")

# ---------------------------------------------------------------- C
print("C  the gap is not uniform")
allgaps = []
lag = []
for seed in (1, 2, 3, 4):
    gx, cx, _ = new_gate(seed=seed, local={"per_hour": 0, "per_day": 100000})
    for i in range(400):
        r = gx.acquire(FB, "test", max_wait=10 ** 6)
        if r.code == sg.WAIT:
            cx.t = r.retry_at
            gx.acquire(FB, "test", max_wait=0)
    t = [row["ts"] for row in ledger(gx)]
    gp = [b - a for a, b in zip(t, t[1:])]
    allgaps += gp
    lg = [math.log(x) for x in gp]
    m = statistics.mean(lg)
    num = sum((a - m) * (b - m) for a, b in zip(lg, lg[1:]))
    den = sum((a - m) ** 2 for a in lg)
    lag.append(num / den)
cv = statistics.pstdev(allgaps) / statistics.mean(allgaps)
distinct = len(set(round(x, 3) for x in allgaps))
p50, p95 = statistics.quantiles(allgaps, n=20)[9], statistics.quantiles(allgaps, n=20)[18]
ok(min(allgaps) >= 45 - 1e-6, "floor holds over %d gaps" % len(allgaps))
ok(distinct > len(allgaps) * 0.9, "gaps are not a small set of values",
   "%d distinct of %d" % (distinct, len(allgaps)))
at_floor = sum(1 for x in allgaps if x < 45.5)
ok(at_floor < len(allgaps) * 0.02, "no pile at the floor (under 2 percent within 0.5 s)",
   "%d of %d" % (at_floor, len(allgaps)))
ok(cv > 0.6, "coefficient of variation well above a uniform band's", "cv %.2f" % cv)
ok(p95 > 3 * p50, "heavy right tail: p95 over 3x the median",
   "p50 %.0f p95 %.0f" % (p50, p95))
ok(all(x > 0.1 for x in lag), "positive lag 1 autocorrelation of log gaps, every seed",
   str([round(x, 3) for x in lag]))
print("     %d gaps: median %.0f s, p95 %.0f s, mean %.0f s (%.1f loads an hour on "
      "average), cv %.2f, lag1 %s" % (len(allgaps), p50, p95, statistics.mean(allgaps),
                                      3600 / statistics.mean(allgaps), cv,
                                      [round(x, 2) for x in lag]))

# ---------------------------------------------------------------- D
print("D  per platform, per route")
g5, clk5, _ = new_gate(local={"min_gap_s": 45, "per_hour": 2})
g5.acquire(FB, "t")
clk5.t += 3000
g5.acquire(FB, "t")
clk5.t += 100
ok(g5.acquire(FB, "t", max_wait=0).code == sg.HOUR_FULL, "facebook hour full")
ok(g5.acquire("https://www.linkedin.com/in/x", "t", max_wait=0).code == sg.OK,
   "linkedin still has its own budget")
ok(g5.acquire(FB, "t", route="remote", max_wait=0).code == sg.OK,
   "facebook remote route has its own budget")
r = g5.acquire(FB, "t", route="remote", max_wait=0)
ok(r.code == sg.WAIT and 8 - 1e-6 <= r.wait_s, "remote gap floor is 8 s", "wait %.1f" % r.wait_s)
ok(g5.acquire("https://fb.com/x", "t", max_wait=0).code == sg.HOUR_FULL,
   "fb.com shares the facebook budget")
ok(g5.acquire("https://www.messenger.com/t/1", "t", max_wait=0).code == sg.HOUR_FULL,
   "messenger.com shares the facebook budget")

# ---------------------------------------------------------------- E
print("E  two real processes racing on one ledger")
RACER = r"""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("sg", %r)
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
g = sg.Gate(config_path=sys.argv[1], state_dir=sys.argv[2])
codes = []
for i in range(int(sys.argv[3])):
    codes.append(g.acquire(%r, "racer" + sys.argv[4], max_wait=30).code)
print(json.dumps(codes))
""" % (GATE, FB)


def race(n_procs, each, **overrides):
    d, path = tmp_cfg(**overrides)
    state = os.path.join(d, "state")
    procs = [subprocess.Popen([sys.executable, "-c", RACER, path, state, str(each), str(i)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for i in range(n_procs)]
    outs = [p.communicate(timeout=120) for p in procs]
    codes = []
    for out, err in outs:
        try:
            codes += json.loads(out.strip().splitlines()[-1])
        except Exception:
            print("racer output:", out, err)
    rows = [json.loads(line) for line in open(os.path.join(state, sg.LEDGER_NAME))]
    return codes, rows


t0 = time.time()
codes, rows = race(2, 4, local={"min_gap_s": 0.4, "per_hour": 0})
ts = sorted(r["ts"] for r in rows)
gaps = [b - a for a, b in zip(ts, ts[1:])]
ok(codes.count(0) == 8 and len(rows) == 8, "2 processes x 4: all 8 granted, 8 rows",
   str(codes))
ok(min(gaps) >= 0.4 - 0.01, "the gap held ACROSS processes (min %.3f s, floor 0.4)" % min(gaps))
ok(len(set(r["actor"] for r in rows)) == 2, "both processes got loads in")
codes, rows = race(3, 4, local={"min_gap_s": 0.05, "per_hour": 5})
ok(codes.count(0) == 5 and len(rows) == 5 and codes.count(4) == 7,
   "3 processes x 4 against an hourly cap of 5: exactly 5 granted, 7 refused",
   str(codes))
print("     race wall time %.1f s" % (time.time() - t0))

# ---------------------------------------------------------------- F
print("F  fail closed")
d, path = tmp_cfg()
c = json.load(open(path))
c["gap_model"] = "/nonexistent/governor.py"
json.dump(c, open(path, "w"))
gx = sg.Gate(config_path=path, state_dir=os.path.join(d, "s"), clock=sg.FakeClock(1e9))
try:
    gx.acquire(FB, "t")
    ok(False, "missing gap model refuses")
except sg.GateError as e:
    ok("gap model" in str(e), "missing gap model raises GateError (exit 2)")
try:
    sg.Gate(config_path="/nonexistent.json", state_dir=d).acquire(FB, "t")
    ok(False, "unreadable config refuses")
except sg.GateError:
    ok(True, "unreadable config raises GateError")
gx, cx, _ = new_gate(local={"min_gap_s": 1, "per_hour": 3})
os.makedirs(gx.state_dir, exist_ok=True)
with open(gx.ledger_path, "w") as fh:
    fh.write('{"ts": %f, "platform": "facebook", "route": "local"}\n' % (cx.t - 10))
    fh.write('{"ts": 17903\n')  # torn line
r = gx.acquire(FB, "t", max_wait=0)
ok(r.code == sg.OK and r.hour == 3, "a torn ledger line counts as a used slot", "hour %d" % r.hour)
cx.t += 5
ok(gx.acquire(FB, "t", max_wait=0).code == sg.HOUR_FULL, "and the cap bites one early")
gy, cy, _ = new_gate()
os.makedirs(gy.state_dir, exist_ok=True)
open(gy.state_path, "w").write("{not json")
r = gy.check(FB)
ok(r.code == sg.WAIT and r.wait_s >= 45, "a corrupt state file forces a full floor wait")
ok(os.path.exists(gy.state_path + ".corrupt"), "the corrupt state file is moved aside")
cy.t += 46
r = gy.acquire(FB, "t", max_wait=0)
ok(r.code == sg.OK, "one floor gap later the gate works again (self heals; QA round 2)",
   "code %d" % r.code)
ok(gy.acquire("https://www.linkedin.com/in/x", "t", max_wait=0).code == sg.OK,
   "and every other platform works again too")
gz, cz, _ = new_gate(local={"min_gap_s": 1, "per_hour": 3})
os.makedirs(gz.state_dir, exist_ok=True)
with open(gz.ledger_path, "w") as fh:
    fh.write('{"ts": %f, "platform": "linkedin", "route": "local"}\n' % (cz.t - 30 * 86400))
    fh.write('{"ts": 17903\n')  # torn, 30 days old by its neighbour
r = gz.acquire(FB, "t", max_wait=0)
ok(r.code == sg.OK and r.hour == 1 and r.day == 1,
   "an old torn line is dated by its neighbour and has aged out (QA round 2)",
   "hour %d day %d" % (r.hour, r.day))
for bad in ("", "has space", "x" * 60, "semi;colon"):
    try:
        gy.acquire(FB, bad)
        ok(False, "bad actor %r refused" % bad)
    except sg.GateError:
        ok(True, "bad actor %r refused" % bad)
cli_help = subprocess.run([sys.executable, GATE, "acquire", "--help"], capture_output=True,
                          text=True).stdout
ok("--config" not in cli_help and "--state" not in cli_help,
   "the CLI has no config or state override")
src = open(GATE).read()
ok("os.environ" not in src and "getenv" not in src, "the gate reads no environment variable")
r = subprocess.run([sys.executable, GATE, "check", "--url", "https://example.com/"],
                   capture_output=True, text=True)
ok(r.returncode == 0 and "NOT SOCIAL" in r.stdout, "CLI check on a non social URL: 0")
r = subprocess.run([sys.executable, GATE, "acquire", "--url", FB], capture_output=True,
                   text=True)
ok(r.returncode == 2, "CLI acquire without --actor: exit 2")

# ---------------------------------------------------------------- G
print("G  grants")
gg, cg, _ = new_gate()
ok(not gg.consume_grant("facebook"), "no grant, nothing to consume")
gg.acquire(FB, "t", grant=True)
ok(gg.consume_grant("facebook"), "a grant is consumed once")
ok(not gg.consume_grant("facebook"), "and only once")
cg.t += 1000
gg.acquire(FB, "t", grant=True)
ok(not gg.consume_grant("linkedin"), "a facebook grant does not open linkedin")
ok(not gg.consume_grant("facebook", "remote"), "a local grant does not open remote")
cg.t += 121
ok(not gg.consume_grant("facebook"), "a grant expires after grant_ttl_s")
cg.t += 1000
gg.acquire(FB, "t", grant=True)
gg.acquire(FB, "t", max_wait=10 ** 6)
ok(not gg.consume_grant("facebook"), "a later plain acquire clears an unused grant")

# ---------------------------------------------------------------- H
print("H  the day is the Mac's zone, never the TZ variable (QA round 3)")
TZ_PROBE = r"""
import importlib.util, json, os, sys, tempfile
spec = importlib.util.spec_from_file_location("g", sys.argv[1])
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
d = tempfile.mkdtemp(); cfg = json.load(open(sys.argv[2]))
if sys.argv[3] != "-":
    cfg["day_zone"] = sys.argv[3]
cp = os.path.join(d, "c.json"); json.dump(cfg, open(cp, "w"))
st = os.path.join(d, "s"); os.makedirs(st)
now = 1790461800.0  # 2026-09-26 22:30 UTC: evening in the Americas, past midnight in Berlin
with open(os.path.join(st, "social-loads.jsonl"), "w") as fh:
    for i in range(150):
        fh.write(json.dumps({"ts": now - 3720 - i, "platform": "facebook", "route": "local",
                             "actor": "t", "host": "www.facebook.com", "via": "cli"}) + "\n")
g = sg.Gate(config_path=cp, state_dir=st, clock=sg.FakeClock(now))
print(g.check("https://www.facebook.com/x").code)
"""


def tz_code(tz, zone="-"):
    env = dict(os.environ)
    if tz:
        env["TZ"] = tz
    r = subprocess.run([sys.executable, "-c", TZ_PROBE, GATE, REAL_CFG, zone],
                       capture_output=True, text=True, env=env)
    return r.stdout.strip() or r.stderr.strip()[-200:]


ok(tz_code(None) == "5", "150 loads earlier this evening: the day is full (exit 5)",
   tz_code(None))
ok(tz_code("Europe/Berlin") == "5", "TZ=Europe/Berlin does not open a fresh day",
   tz_code("Europe/Berlin"))
ok(tz_code("Pacific/Kiritimati") == "5", "TZ=Pacific/Kiritimati does not either",
   tz_code("Pacific/Kiritimati"))
ok(tz_code(None, "Europe/Berlin") == "0", "a day_zone in the owner's config does move it",
   tz_code(None, "Europe/Berlin"))
ok("cannot load the day zone" in tz_code(None, "Not/AZone"),
   "an unknown day_zone fails closed (GateError)", tz_code(None, "Not/AZone"))

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
