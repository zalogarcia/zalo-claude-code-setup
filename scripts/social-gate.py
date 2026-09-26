#!/usr/bin/env python3
"""social-gate: ONE machine wide pacing gate for social media page loads.

Why this exists
---------------
2026-09-26. A background worker looking for Facebook owners loaded about 631
Facebook profiles, logged out, in the Blueprint Chrome on port 9222 (the
GoHighLevel browser), 556 of them onto a login wall, all from this Mac's IP,
where Zalo's real Facebook, LinkedIn and Instagram accounts are logged in.
Zalo, the same afternoon: "we cannot have hundreds of stuff, you know, pages and
traffic from social media, as we might get banned easily because it's not
human-like."

So every job on this Mac that loads a social page asks this gate first, and the
gate shares ONE budget across all of them: a file lock serialises the callers
and an append only ledger on disk is the denominator, so parallel jobs, new
processes and restarts all see the same count.

Usage
-----
    social-gate.py acquire --url <url> --actor <name> [--route local|remote]
                           [--max-wait <s>] [--grant] [--json]
    social-gate.py check   --url <url> [--route local|remote] [--json]
    social-gate.py status  [--json]

acquire waits (bounded by --max-wait, default max_wait_s in the config) until the
platform's gap has passed, then appends one ledger row and exits 0. It REFUSES,
never queues, when the rolling hour or the day is full. check answers the same
question without waiting and without writing anything.

--grant hands the slot to the NEXT load that goes through the hook
(~/.claude/hooks/social-pace-guard.py) within grant_ttl_s: a Playwright
browser_navigate, or a lone curl in the next Bash call. That is how an agent
waits for a slot (this command sleeps; a hook cannot) and then loads the page.

Exit codes
----------
  0  allowed (acquire: slot taken and logged; check: a load would pass now).
     Also 0 for a URL that is not a social host: nothing to gate, nothing logged.
  2  error: bad arguments, unreadable config, missing gap model. Fail closed.
  3  wait: the gap has not passed (check), or it would not pass within --max-wait
     (acquire). The output says how long.
  4  refused: the rolling hour for this platform and route is full.
  5  refused: the day for this platform and route is full. Stop for the day.

The gap
-------
The gap is NOT a uniform sleep. Uniform random delays are catchable from the
timing sequence alone (see the header of the outreach governor, which cites the
evidence). The gap is drawn from the governor's own model, imported from the
file named by `gap_model` in the config: its sticky three state chain (bursts,
switches, breaks), its AR(1) rhythm (positive autocorrelation between
consecutive gaps) and its diurnal envelope. The governor's gaps are floored at
its GAP_FLOOR_S (90 s); this gate multiplies them by min_gap_s / GAP_FLOOR_S so
the whole shape is kept and the floor lands on the configured min_gap_s. The
chain state is kept per platform and route in the state file, so the
autocorrelation carries across processes. If the governor cannot be loaded the
gate fails CLOSED (exit 2): no gap model, no social loads.

What it records
---------------
~/.claude/state/social-loads.jsonl, one line per granted load: time, platform,
route, actor, the HOST only (never the path: a profile path names a person),
how it came in (cli, hook, python), and the next gap drawn.

There is no environment override and no --config flag, on purpose: an agent
that could point the gate at a looser file would have a way around it. Tests
import this module and construct Gate(...) with their own paths.
"""

import argparse
import contextlib
import errno
import fcntl
import importlib.util
import json
import math
import os
import random
import re
import sys
import time
import types
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urlsplit

HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, ".claude", "config", "social-pacing.json")
STATE_DIR = os.path.join(HOME, ".claude", "state")
LEDGER_NAME = "social-loads.jsonl"
STATE_NAME = "social-gate-state.json"
LOCK_NAME = "social-gate.lock"

OK, ERROR, WAIT, HOUR_FULL, DAY_FULL = 0, 2, 3, 4, 5
ROUTES = ("local", "remote")
HARD_MAX_WAIT_S = 540  # a Bash call caps at 600 s; the gate never outlives it
ACTOR_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,48}$")


class GateError(Exception):
    """Config, gap model or argument problem. The gate fails closed on it."""


class Clock:
    def now(self):
        return time.time()

    def sleep(self, seconds):
        if seconds > 0:
            time.sleep(seconds)


class FakeClock(Clock):
    """Tests only. Advances instantly and remembers what it was asked to sleep."""

    def __init__(self, start):
        self.t = float(start)
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        if seconds < 0:
            raise ValueError("negative sleep")
        self.slept.append(seconds)
        self.t += seconds


# --------------------------------------------------------------------------
# config and host classification
# --------------------------------------------------------------------------

def load_config(path=CONFIG_PATH):
    try:
        with open(path) as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as e:
        raise GateError("cannot read the pacing config %s: %s" % (path, e))
    plats = cfg.get("platforms")
    routes = cfg.get("routes")
    if not isinstance(plats, dict) or not plats:
        raise GateError("config has no platforms")
    for r in ROUTES:
        rc = (routes or {}).get(r)
        if not isinstance(rc, dict):
            raise GateError("config has no %s route budget" % r)
        for k in ("min_gap_s", "per_hour", "per_day"):
            v = rc.get(k)
            if not isinstance(v, (int, float)) or v < 0:
                raise GateError("config routes.%s.%s must be a number >= 0" % (r, k))
        if rc["min_gap_s"] <= 0 or rc["per_day"] <= 0:
            raise GateError("config routes.%s needs min_gap_s > 0 and per_day > 0" % r)
    return cfg


def day_zone(cfg):
    """The zone per_day counts in: the config's day_zone, else the Mac's system zone
    read from /etc/localtime. Never the TZ variable: `TZ=Europe/Berlin python3
    social-gate.py acquire ...` opened a fresh day at 18:00 local time (QA round 3)."""
    name = (cfg or {}).get("day_zone")
    if not name:
        real = os.path.realpath("/etc/localtime")
        name = real.split("zoneinfo/", 1)[1] if "zoneinfo/" in real else "UTC"
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(str(name))
    except Exception as e:  # noqa: BLE001 no zone, no day budget: fail closed
        raise GateError("cannot load the day zone %r: %s" % (name, e))


def social_suffixes(cfg):
    """[(domain, platform)], longest domain first."""
    out = []
    for plat, domains in cfg["platforms"].items():
        for d in domains:
            out.append((d.lower().strip("."), plat))
    out.sort(key=lambda x: -len(x[0]))
    return out


def normalize(text):
    """What a browser would resolve: NFKC (fullwidth letters), ideographic and
    fullwidth full stops as dots, percent encoded dots decoded. The hook applies the
    same rule, so a spelling the gate misses cannot be paired past the hook."""
    s = unicodedata.normalize("NFKC", text or "")
    for ch in "\u3002\uff0e\uff61":
        s = s.replace(ch, ".")
    return re.sub(r"%2e", ".", s, flags=re.IGNORECASE)


def host_of(url):
    """The host of a URL, or of a bare 'facebook.com/x' string. Lowercase, no port,
    no userinfo."""
    s = normalize(url).strip()
    if not s:
        return ""
    if "://" not in s:
        s = "https://" + s.lstrip("/")
    try:
        host = urlsplit(s).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def not_page_hosts(cfg):
    return [h.lower().strip(".") for h in
            ((cfg.get("not_page_hosts") or {}).get("hosts") or [])]


def platform_of_host(host, cfg):
    """The platform a host belongs to, or None. An authenticated API host listed in
    not_page_hosts (graph.facebook.com and the like) is not a page load."""
    host = (host or "").lower().rstrip(".")
    if any(host == h or host.endswith("." + h) for h in not_page_hosts(cfg)):
        return None
    for dom, plat in social_suffixes(cfg):
        if host == dom or host.endswith("." + dom):
            return plat
    return None


def host_regex(cfg):
    """Matches any social host inside free text, subdomains included.

    Left edge: not preceded by a host character, so 'notfacebook.com' and
    'box.com' do not match. Right edge: not followed by a host character or by
    '.<label>', so 'facebook.company' and 'facebook.com.evil.org' do not match.
    """
    alts = "|".join(re.escape(d) for d, _ in social_suffixes(cfg))
    return re.compile(
        r"(?<![a-z0-9\-@])((?:[a-z0-9\-]+\.)*(?:%s))(?![a-z0-9\-]|\.[a-z0-9])" % alts,
        re.IGNORECASE)


def find_social_hosts(text, cfg, rx=None):
    """[(platform, host)] for every social host named in text, in order."""
    rx = rx or host_regex(cfg)
    out = []
    for m in rx.finditer(normalize(text).lower()):
        host = m.group(1).lower()
        plat = platform_of_host(host, cfg)
        if plat:
            out.append((plat, host))
    return out


# --------------------------------------------------------------------------
# the gap model (the governor's, reused, not rewritten)
# --------------------------------------------------------------------------

def load_gap_model(cfg):
    path = os.path.expanduser(str(cfg.get("gap_model") or ""))
    if not path or not os.path.isfile(path):
        raise GateError("gap model not found at %r (config gap_model). The gate fails "
                        "closed without it: no gap model, no social loads." % path)
    spec = importlib.util.spec_from_file_location("_social_gate_governor", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 any import failure is fail closed
        raise GateError("gap model %s failed to import: %s" % (path, e))
    for name in ("Governor", "GAP_FLOOR_S", "RHYTHM_SIGMA"):
        if not hasattr(mod, name):
            raise GateError("gap model %s has no %s" % (path, name))
    if not hasattr(mod.Governor, "_next_gap"):
        raise GateError("gap model %s has no Governor._next_gap" % path)
    return mod


def draw_gap(gov, rng, clock, key_state, min_gap_s):
    """One gap from the governor's model, scaled so its floor is min_gap_s.

    Calls Governor._next_gap itself with a stand in object that carries only the
    state that method reads (the rng, the chain mode, the AR(1) rhythm, the clock
    and the local time), so a retune of the governor retunes this gate too.
    """
    shim = types.SimpleNamespace()
    shim._rng = rng
    shim._mode = key_state.get("mode") or "slow"
    rhythm = key_state.get("rhythm")
    shim._rhythm = float(rhythm) if isinstance(rhythm, (int, float)) \
        else rng.gauss(0.0, gov.RHYTHM_SIGMA)
    shim.clock = clock
    shim._local = lambda epoch, caps: datetime.fromtimestamp(epoch)
    raw = float(gov.Governor._next_gap(shim, {}))
    floor = float(gov.GAP_FLOOR_S)
    # The governor CLAMPS a short draw to its floor, which piles 6 to 20 percent of
    # its gaps (measured over 20,000 draws at 04:00, 10:00 and 14:00) onto exactly
    # the floor value: a spike at one number, the regularity the model exists to
    # avoid. Reflect instead: rebuild the unclamped draw from the governor's own
    # constants and the state its method just advanced, and mirror it above the
    # floor. The chain, the rhythm and the diurnal factor are still the governor's.
    try:
        unclamped = math.exp(gov.MODE_MU[shim._mode] + shim._rhythm) * gov.DIURNAL.get(
            datetime.fromtimestamp(clock.now()).hour, gov.OUT_OF_TABLE_DIURNAL)
    except (AttributeError, KeyError, TypeError, OverflowError):
        unclamped = raw
    if raw <= floor and unclamped < floor:
        raw = 2.0 * floor - unclamped
    scale = float(min_gap_s) / floor
    gap = max(float(min_gap_s), raw * scale)
    return gap, shim._mode, shim._rhythm


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------

class Decision:
    def __init__(self, code, platform=None, route=None, host=None, reason="",
                 wait_s=0.0, hour=0, day=0, per_hour=0, per_day=0, retry_at=None,
                 social=True, granted_by=None):
        self.code = code
        self.platform = platform
        self.route = route
        self.host = host
        self.reason = reason
        self.wait_s = float(wait_s)
        self.hour = hour
        self.day = day
        self.per_hour = per_hour
        self.per_day = per_day
        self.retry_at = retry_at
        self.social = social
        self.granted_by = granted_by

    @property
    def ok(self):
        return self.code == OK

    def as_dict(self):
        d = dict(code=self.code, ok=self.ok, social=self.social, platform=self.platform,
                 route=self.route, host=self.host, reason=self.reason,
                 wait_s=round(self.wait_s, 1), hour=self.hour, day=self.day,
                 per_hour=self.per_hour, per_day=self.per_day)
        if self.retry_at:
            d["retry_at"] = datetime.fromtimestamp(self.retry_at).isoformat(
                timespec="seconds")
        if self.granted_by:
            d["granted_by"] = self.granted_by
        return d

    def line(self):
        if not self.social:
            return "NOT SOCIAL: %s is not a social host, nothing to gate" % (self.host or "?")
        caps = "%s %s: %d of %s this hour, %d of %d today" % (
            self.platform, self.route, self.hour,
            self.per_hour if self.per_hour else "no cap", self.day, self.per_day)
        word = {OK: "ALLOWED", WAIT: "WAIT", HOUR_FULL: "REFUSED", DAY_FULL: "REFUSED",
                ERROR: "ERROR"}.get(self.code, "ERROR")
        s = "%s %s. %s" % (word, caps, self.reason)
        if self.retry_at:
            s += " Next possible at %s." % datetime.fromtimestamp(
                self.retry_at).strftime("%H:%M:%S")
        return s.strip()


class Gate:
    def __init__(self, config_path=CONFIG_PATH, state_dir=STATE_DIR, clock=None,
                 rng=None, lock_timeout_s=30.0):
        self.config_path = config_path
        self.state_dir = state_dir
        self.clock = clock or Clock()
        self.rng = rng if rng is not None else random.Random()
        self.lock_timeout_s = lock_timeout_s
        self.ledger_path = os.path.join(state_dir, LEDGER_NAME)
        self.state_path = os.path.join(state_dir, STATE_NAME)
        self.lock_path = os.path.join(state_dir, LOCK_NAME)
        self._gov = None

    # ------------------------------------------------------------ plumbing

    def config(self):
        return load_config(self.config_path)

    def gov(self, cfg):
        if self._gov is None:
            self._gov = load_gap_model(cfg)
        return self._gov

    @contextlib.contextmanager
    def _locked(self):
        os.makedirs(self.state_dir, mode=0o700, exist_ok=True)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        # Real time on purpose: the lock is about other PROCESSES, and a fake
        # clock in a test must not turn a busy lock into an instant pass.
        deadline = time.monotonic() + self.lock_timeout_s
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                        raise
                    if time.monotonic() > deadline:
                        raise GateError("the pacing lock is busy (%s); refusing rather "
                                        "than loading unpaced" % self.lock_path)
                    time.sleep(0.02)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _read_state(self, cfg=None):
        try:
            with open(self.state_path) as fh:
                st = json.load(fh)
            if not isinstance(st, dict):
                raise ValueError("state is not an object")
            return st
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            # A state file we cannot read loses the chain state and the next allowed
            # times. Fail closed ONCE: move it aside, and hold every platform for one
            # full floor gap from now, then carry on. (QA round 2: returning a marker
            # without rewriting the file held every platform forever.)
            floor = max((float(r["min_gap_s"]) for r in (cfg or {}).get(
                "routes", {}).values()), default=45.0)
            fresh = {"_hold_until": self.clock.now() + floor}
            try:
                os.replace(self.state_path, self.state_path + ".corrupt")
                self._write_state(dict(fresh))
            except OSError:
                pass
            return fresh

    def _write_state(self, st):
        tmp = "%s.%d.tmp" % (self.state_path, os.getpid())
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(st, fh, sort_keys=True)
        os.replace(tmp, self.state_path)

    def _append(self, row):
        fd = os.open(self.ledger_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def rows_since(self, since_epoch):
        """Ledger rows with ts >= since_epoch, read from the END of the file.

        An unparseable line counts as a load for every platform and route: a line
        torn by a crash mid write may have been a load, and skipping it would hand
        the slot back. It is dated by its nearest readable neighbour (not "now"),
        so it spends one slot in its own hour and day and then ages out.
        """
        try:
            size = os.path.getsize(self.ledger_path)
        except OSError:
            return []
        chunk = 256 * 1024
        with open(self.ledger_path, "rb") as fh:
            while True:
                start = max(0, size - chunk)
                fh.seek(start)
                data = fh.read(size - start)
                lines = data.split(b"\n")
                if start > 0:
                    lines = lines[1:]  # first line may be cut mid way
                parsed, oldest = [], None
                for raw in lines:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        r = json.loads(raw)
                        ts = float(r["ts"])
                    except (ValueError, KeyError, TypeError):
                        parsed.append(None)
                        continue
                    oldest = ts if oldest is None else min(oldest, ts)
                    parsed.append(r)
                if start == 0 or (oldest is not None and oldest < since_epoch):
                    rows = []
                    for i, r in enumerate(parsed):
                        if r is None:
                            near = next((parsed[k]["ts"] for k in range(i - 1, -1, -1)
                                         if parsed[k] is not None), None)
                            if near is None:
                                near = next((parsed[k]["ts"] for k in range(i + 1, len(parsed))
                                             if parsed[k] is not None), self.clock.now())
                            r = {"ts": float(near), "platform": "*", "route": "*",
                                 "unparseable": True}
                        if float(r["ts"]) >= since_epoch:
                            rows.append(r)
                    return rows
                chunk *= 4

    def day_start(self, now, cfg=None):
        d = datetime.fromtimestamp(now, day_zone(cfg or self.config()))
        return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def next_day_start(self, now, cfg=None):
        d = datetime.fromtimestamp(now, day_zone(cfg or self.config())).replace(
            hour=0, minute=0, second=0, microsecond=0)
        return (d + timedelta(days=1)).replace(hour=0).timestamp()

    # --------------------------------------------------------------- core

    def _classify(self, url, route, cfg):
        if route not in ROUTES:
            raise GateError("route must be local or remote, not %r" % route)
        host = host_of(url)
        if not host:
            raise GateError("could not read a host from %r" % url)
        return host, platform_of_host(host, cfg)

    def _evaluate(self, platform, route, host, cfg, st, now):
        rc = cfg["routes"][route]
        per_hour, per_day = int(rc["per_hour"]), int(rc["per_day"])
        day0 = self.day_start(now, cfg)
        rows = self.rows_since(min(now - 3600.0, day0))
        mine = [r for r in rows
                if (r.get("platform") == platform or r.get("platform") == "*")
                and (r.get("route") == route or r.get("route") == "*")]
        hour_rows = sorted(float(r["ts"]) for r in mine if float(r["ts"]) > now - 3600.0)
        day_n = sum(1 for r in mine if float(r["ts"]) >= day0)
        d = Decision(OK, platform, route, host, hour=len(hour_rows), day=day_n,
                     per_hour=per_hour, per_day=per_day)
        if day_n >= per_day:
            d.code, d.retry_at = DAY_FULL, self.next_day_start(now, cfg)
            d.reason = ("The %s %s budget for today is spent. Stop %s loads for the "
                        "day." % (platform, route, platform))
            return d
        if per_hour and len(hour_rows) >= per_hour:
            d.code = HOUR_FULL
            d.retry_at = hour_rows[len(hour_rows) - per_hour] + 3600.0
            d.reason = ("The %s %s rolling hour is full." % (platform, route))
            return d
        key = "%s/%s" % (platform, route)
        ks = st.get(key) or {}
        next_at = ks.get("next_at")
        hold = st.get("_hold_until")
        if isinstance(hold, (int, float)) and hold > now:
            next_at = max(float(next_at or 0), float(hold))
        if isinstance(next_at, (int, float)) and next_at > now:
            d.code, d.wait_s, d.retry_at = WAIT, next_at - now, next_at
            d.reason = "The paced gap has %.0f s to run." % (next_at - now)
        return d

    def _record(self, d, actor, via, cfg, st, now, grant):
        rc = cfg["routes"][d.route]
        key = "%s/%s" % (d.platform, d.route)
        ks = dict(st.get(key) or {})
        gap, mode, rhythm = draw_gap(self.gov(cfg), self.rng, self.clock, ks,
                                     rc["min_gap_s"])
        ks.update({"next_at": now + gap, "mode": mode, "rhythm": rhythm, "last_at": now})
        if grant:
            ks["grant"] = {"until": now + float(cfg.get("grant_ttl_s", 120)),
                           "host": d.host, "actor": actor}
        else:
            ks.pop("grant", None)
        st[key] = ks
        row = {"ts": round(now, 3),
               "iso": datetime.fromtimestamp(now, day_zone(cfg)).isoformat(timespec="seconds"),
               "platform": d.platform, "route": d.route, "actor": actor,
               "host": d.host, "via": via, "next_gap_s": round(gap, 1)}
        if grant:
            row["grant"] = True  # spent by a browser call: the audit pairs it with History
        self._append(row)
        self._write_state(st)
        d.hour += 1
        d.day += 1
        d.reason = ("Logged. The next %s %s load is not before %s." % (
            d.platform, d.route,
            datetime.fromtimestamp(now + gap).strftime("%H:%M:%S")))
        return d

    def check(self, url, route="local"):
        cfg = self.config()
        host, plat = self._classify(url, route, cfg)
        if not plat:
            return Decision(OK, None, route, host, social=False)
        self.gov(cfg)  # a missing gap model fails the check too
        with self._locked():
            return self._evaluate(plat, route, host, cfg, self._read_state(cfg),
                                  self.clock.now())

    def acquire(self, url, actor, route="local", max_wait=None, grant=False, via="cli"):
        if not actor or not ACTOR_RE.match(str(actor)):
            raise GateError("--actor must be 1 to 48 of [A-Za-z0-9_.:@-], got %r" % actor)
        cfg = self.config()
        host, plat = self._classify(url, route, cfg)
        if not plat:
            return Decision(OK, None, route, host, social=False)
        self.gov(cfg)
        if max_wait is None:
            max_wait = float(cfg.get("max_wait_s", 300))
        max_wait = max(0.0, min(float(max_wait), HARD_MAX_WAIT_S))
        deadline = self.clock.now() + max_wait
        while True:
            with self._locked():
                st = self._read_state(cfg)
                now = self.clock.now()
                d = self._evaluate(plat, route, host, cfg, st, now)
                if d.code == OK:
                    return self._record(d, actor, via, cfg, st, now, grant)
            if d.code != WAIT:
                return d
            remaining = deadline - self.clock.now()
            if remaining <= 0:
                d.reason += (" This call may wait %.0f s and that has run out; nothing was "
                             "logged. Call again to keep waiting." % max_wait)
                return d
            # Sleep toward the slot, but never past this call's own budget: a gap longer
            # than --max-wait is waited out across calls, each one making progress.
            self.clock.sleep(min(d.wait_s, remaining))

    def consume_grant(self, platform, route="local"):
        """Use a slot an earlier `acquire --grant` reserved. True if one was used."""
        with self._locked():
            st = self._read_state()
            key = "%s/%s" % (platform, route)
            ks = st.get(key) or {}
            g = ks.get("grant")
            if not isinstance(g, dict) or float(g.get("until", 0)) <= self.clock.now():
                return False
            ks.pop("grant", None)
            st[key] = ks
            self._write_state(st)
            return True

    def status(self):
        cfg = self.config()
        now = self.clock.now()
        with self._locked():
            st = self._read_state(cfg)
            out = []
            for plat in cfg["platforms"]:
                for route in ROUTES:
                    d = self._evaluate(plat, route, None, cfg, st, now)
                    out.append(d)
        return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _emit(d, as_json):
    if as_json:
        print(json.dumps(d.as_dict(), sort_keys=True))
    else:
        print(d.line())


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="social-gate.py",
        description="One machine wide pacing gate for social media page loads.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("acquire", help="wait for and log one social page load")
    a.add_argument("--url", required=True)
    a.add_argument("--actor", required=True)
    a.add_argument("--route", default="local", choices=ROUTES)
    a.add_argument("--max-wait", type=float, default=None)
    a.add_argument("--grant", action="store_true",
                   help="hand the slot to the next hook checked load within grant_ttl_s")
    a.add_argument("--json", action="store_true")
    c = sub.add_parser("check", help="would a load pass right now? writes nothing")
    c.add_argument("--url", required=True)
    c.add_argument("--route", default="local", choices=ROUTES)
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("status", help="every platform and route budget")
    s.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    gate = Gate()
    try:
        if args.cmd == "acquire":
            d = gate.acquire(args.url, args.actor, args.route, args.max_wait,
                             grant=args.grant, via="cli")
            _emit(d, args.json)
            return d.code
        if args.cmd == "check":
            d = gate.check(args.url, args.route)
            _emit(d, args.json)
            return d.code
        rows = gate.status()
        if args.json:
            print(json.dumps([r.as_dict() for r in rows], sort_keys=True))
        else:
            for r in rows:
                print(r.line())
        return 0
    except GateError as e:
        print("ERROR social-gate: %s" % e, file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
