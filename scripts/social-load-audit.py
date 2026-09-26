#!/usr/bin/env python3
"""social-load-audit: count social media page loads from this Mac, per hour and day.

The hook (~/.claude/hooks/social-pace-guard.py) only sees tool calls a Claude or
Codex session makes. It cannot see Astra's Computer Use clicks in Chrome, a
Python lane inside Jev, or a script that reads its URLs from a file it opens
itself. The browsers can: every top level page load lands in a profile's
History database. So this audit reads them, joins the gate's own ledger, and
flags any platform whose loads crossed the caps in
~/.claude/config/social-pacing.json, plus ANY social visit in the Blueprint
Chrome profile (the GoHighLevel browser never loads a social host).

Read only, copy first: each History file is COPIED to a temp dir and the copy
is opened read only (immutable), so the live database a running Chrome holds is
never opened. Output is counts only. No URL, no path, no title is printed or sent.

Sources
  chrome:<profile>   every profile under the Chrome user data dir
  blueprint          ~/.blueprint-chrome-profile (the GHL browser)
  playwright         every Playwright MCP profile
  ledger             ~/.claude/state/social-loads.jsonl (the gate)
Visits synced from another device (originator_cache_guid set) are excluded,
subframes are excluded, and a redirect that stays on the same platform counts
once, so a profile that bounces to a login wall is one load, not two.

The browser count and the gate count overlap (a gated Astra load is in both), so
the machine figure for the local route is their UNION: every browser visit plus
every gate row no visit accounts for (see union_local).

Usage
  social-load-audit.py [--hours 24] [--json]
  social-load-audit.py --alert [--dry-run]   send ONE Telegram line, only for a
                                             crossing not alerted before
Exit 0 nothing over a cap, 1 something over a cap, 2 error.
"""

import argparse
import glob
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime

HOME = os.path.expanduser("~")
GATE_PATH = os.path.join(HOME, ".claude", "scripts", "social-gate.py")
CONFIG_PATH = os.path.join(HOME, ".claude", "config", "social-pacing.json")
STATE_DIR = os.path.join(HOME, ".claude", "state")
ALERTED_NAME = "social-audit-alerted.json"
SETTINGS_LOCAL = os.path.join(HOME, ".claude", "settings.local.json")
THROTTLE = os.path.join(HOME, "dev", "claude-telegram-bridge", "tg-throttle.json")

WEBKIT_EPOCH_OFFSET = 11644473600  # seconds between 1601-01-01 and 1970-01-01
SUBFRAMES = (3, 4)                 # AUTO_SUBFRAME, MANUAL_SUBFRAME
REDIRECT_BITS = 0x40000000 | 0x80000000  # CLIENT_REDIRECT | SERVER_REDIRECT


def load_gate_module():
    spec = importlib.util.spec_from_file_location("social_gate_for_audit", GATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def history_sources(cfg):
    """[(label, History path)] for every profile that has one."""
    aud = cfg.get("audit") or {}
    out = []
    ud = os.path.expanduser(aud.get("chrome_user_data",
                                    "~/Library/Application Support/Google/Chrome"))
    for h in sorted(glob.glob(os.path.join(ud, "*", "History"))):
        prof = os.path.basename(os.path.dirname(h))
        if prof == "System Profile":
            continue
        out.append(("chrome:" + prof, h))
    bp = os.path.expanduser((cfg.get("blueprint") or {}).get("profile_dir",
                                                             "~/.blueprint-chrome-profile"))
    for h in sorted(glob.glob(os.path.join(bp, "*", "History"))):
        out.append(("blueprint", h))
    pw = os.path.expanduser(aud.get("playwright_profiles_glob",
                                    "~/Library/Caches/ms-playwright/mcp-chrome-*"))
    for h in sorted(glob.glob(os.path.join(pw, "*", "History"))):
        out.append(("playwright", h))
    return out


def read_visits(history_path, since_epoch, platform_of, tmpdir):
    """[(epoch, platform)] of top level social loads, plus a count of synced ones.

    Copies the file first and opens only the copy, read only and immutable.
    """
    copy = os.path.join(tmpdir, "h-%d" % abs(hash(history_path)))
    shutil.copyfile(history_path, copy)
    con = sqlite3.connect("file:%s?mode=ro&immutable=1" % copy, uri=True)
    try:
        since_wk = int((since_epoch + WEBKIT_EPOCH_OFFSET) * 1e6)
        cols = {r[1] for r in con.execute("PRAGMA table_info(visits)")}
        guid = "COALESCE(v.originator_cache_guid, '')" if "originator_cache_guid" in cols \
            else "''"
        rows = con.execute(
            "SELECT v.id, v.visit_time, v.from_visit, v.transition, u.url, %s "
            "FROM visits v JOIN urls u ON u.id = v.url WHERE v.visit_time >= ?" % guid,
            (since_wk,)).fetchall()
        from_ids = {r[2] for r in rows if r[2]}
        from_url = {}
        if from_ids:
            ids = list(from_ids)
            for k in range(0, len(ids), 500):
                chunk = ids[k:k + 500]
                q = ("SELECT v.id, u.url FROM visits v JOIN urls u ON u.id = v.url "
                     "WHERE v.id IN (%s)" % ",".join("?" * len(chunk)))
                from_url.update(dict(con.execute(q, chunk).fetchall()))
    finally:
        con.close()
        os.remove(copy)
    loads, synced = [], 0
    for vid, vt, from_visit, transition, url, origin in rows:
        plat = platform_of(url)
        if not plat:
            continue
        if origin:
            synced += 1
            continue
        if (transition & 0xFF) in SUBFRAMES:
            continue
        if transition & REDIRECT_BITS and from_visit and \
                platform_of(from_url.get(from_visit, "")) == plat:
            continue
        loads.append((vt / 1e6 - WEBKIT_EPOCH_OFFSET, plat))
    return loads, synced


def worst_rolling_hour(times):
    """(count, start epoch) of the busiest 60 minute window."""
    times = sorted(times)
    best, start, j = 0, None, 0
    for i, t in enumerate(times):
        while times[j] <= t - 3600:
            j += 1
        if i - j + 1 > best:
            best, start = i - j + 1, times[j]
    return best, start


BROWSER_ACTORS = ("astra", "jev")  # callers that open the page in Chrome after acquire


def is_browser_row(row, browser_actors=BROWSER_ACTORS):
    """Does this gate row stand for a load Chrome History will also show? A hook row
    (a browser tool call), a --grant (spent by a browser call), or a caller that
    browses (Astra, Jev's lane). A plain `acquire && curl` or a Python tool's fetch
    never reaches History."""
    if not isinstance(row, dict):
        return True
    actor = str(row.get("actor") or "").lower()
    return (str(row.get("via") or "").startswith("hook:") or bool(row.get("grant"))
            or any(actor == a or actor.startswith(a + ":") for a in browser_actors))


def union_local(browser_ts, ledger_rows, before=5.0, after=180.0,
                browser_actors=BROWSER_ACTORS):
    """One timeline of local loads: every browser visit, plus every gate row that no
    browser visit accounts for (a gated curl, a script's own fetch).

    A gated browser load shows up twice, once in the ledger when the slot is taken
    and once in History a moment later, so a browser row (is_browser_row) is matched
    to the first unmatched visit from `before` s earlier to `after` s later and
    counted once. Any other row never consumes a visit: QA round 3 showed curl rows
    matched to unrelated browsing collapsed the count back toward the larger of the
    two. QA round 2: taking the larger of the two counts missed a crossing when the
    two sets were disjoint (25 browser + 25 curl loads in an hour reported as 25).
    ledger_rows: [(ts, row dict)] or bare timestamps (treated as browser rows)."""
    b = sorted(browser_ts)
    used = [False] * len(b)
    extra = []
    j0 = 0
    rows = sorted(((r, None) if not isinstance(r, tuple) else r for r in ledger_rows),
                  key=lambda x: x[0])
    for t, row in rows:
        if not is_browser_row(row, browser_actors):
            extra.append(t)
            continue
        while j0 < len(b) and b[j0] < t - before:
            j0 += 1
        k = j0
        while k < len(b) and b[k] <= t + after and used[k]:
            k += 1
        if k < len(b) and b[k] <= t + after and not used[k]:
            used[k] = True
        else:
            extra.append(t)
    return sorted(b + extra)


def audit(cfg, sources, ledger_rows, now, hours, platform_of, tmpdir):
    since = now - hours * 3600
    local = cfg["routes"]["local"]
    remote = cfg["routes"]["remote"]
    try:  # the gate's day: the Mac's zone, never the TZ variable
        zone = load_gate_module().day_zone(cfg)
    except Exception:  # noqa: BLE001 an old gate: fall back to process local time
        zone = None
    browser_actors = tuple((cfg.get("audit") or {}).get("browser_actors") or BROWSER_ACTORS)
    per_source = {}
    browser = {}
    synced_total = 0
    errors = []
    for label, path in sources:
        try:
            loads, synced = read_visits(path, since, platform_of, tmpdir)
        except (OSError, sqlite3.Error) as e:
            errors.append("%s: %s" % (label, type(e).__name__))
            continue
        synced_total += synced
        for t, p in loads:
            per_source.setdefault(label, {}).setdefault(p, 0)
            per_source[label][p] += 1
            browser.setdefault(p, []).append((t, label))
    ledger = {}
    for r in ledger_rows:
        try:
            t = float(r["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        if t >= since and r.get("platform") and r.get("route") in ("local", "remote"):
            ledger.setdefault((r["platform"], r["route"]), []).append((t, r))

    plats = sorted(set(browser) | {p for p, _ in ledger})
    report = {"window_start": since, "window_end": now, "platforms": {}, "flags": [],
              "synced_excluded": synced_total, "errors": errors,
              "sources": {k: v for k, v in per_source.items()}}
    for p in plats:
        bt = sorted(t for t, _ in browser.get(p, []))
        lrows = sorted(ledger.get((p, "local"), []), key=lambda x: x[0])
        lt = [t for t, _ in lrows]
        rt = sorted(t for t, _ in ledger.get((p, "remote"), []))
        days = {}
        for t in bt:
            d = datetime.fromtimestamp(t, zone).strftime("%Y-%m-%d")
            days.setdefault(d, [0, 0, 0])[0] += 1
        for t in lt:
            d = datetime.fromtimestamp(t, zone).strftime("%Y-%m-%d")
            days.setdefault(d, [0, 0, 0])[1] += 1
        for t in rt:
            d = datetime.fromtimestamp(t, zone).strftime("%Y-%m-%d")
            days.setdefault(d, [0, 0, 0])[2] += 1
        hours_b = {}
        for t in bt:
            h = datetime.fromtimestamp(t, zone).strftime("%Y-%m-%d %H:00")
            hours_b[h] = hours_b.get(h, 0) + 1
        combined = union_local(bt, lrows, browser_actors=browser_actors)
        machine_days = {}
        for t in combined:
            d = datetime.fromtimestamp(t, zone).strftime("%Y-%m-%d")
            machine_days[d] = machine_days.get(d, 0) + 1
        wh, wh_at = worst_rolling_hour(combined) if combined else (0, None)
        gaps_under = sum(1 for a, b in zip(bt, bt[1:]) if b - a < local["min_gap_s"])
        info = {"browser": len(bt), "ledger_local": len(lt), "ledger_remote": len(rt),
                "machine": len(combined), "days": days, "hours": hours_b,
                "worst_hour": wh, "worst_hour_at": wh_at, "gaps_under_min": gaps_under,
                "blueprint": sum(1 for _, s in browser.get(p, []) if s == "blueprint")}
        report["platforms"][p] = info
        for d, (b, lloc, lrem) in sorted(days.items()):
            machine = machine_days.get(d, 0)
            if machine > local["per_day"]:
                report["flags"].append({"key": "%s:%s:day" % (d, p), "platform": p,
                                        "kind": "day", "count": machine,
                                        "cap": local["per_day"], "day": d})
            if lrem > remote["per_day"]:
                report["flags"].append({"key": "%s:%s:remote-day" % (d, p), "platform": p,
                                        "kind": "remote day", "count": lrem,
                                        "cap": remote["per_day"], "day": d})
        if local.get("per_hour") and info["worst_hour"] > local["per_hour"]:
            at = info["worst_hour_at"]
            d = datetime.fromtimestamp(at, zone).strftime("%Y-%m-%d") if at else "?"
            report["flags"].append({"key": "%s:%s:hour" % (d, p), "platform": p,
                                    "kind": "hour", "count": info["worst_hour"],
                                    "cap": local["per_hour"], "day": d,
                                    "at": datetime.fromtimestamp(at, zone).strftime("%H:%M")
                                    if at else "?"})
        if info["blueprint"]:
            bdays = sorted({datetime.fromtimestamp(t, zone).strftime("%Y-%m-%d")
                            for t, s in browser.get(p, []) if s == "blueprint"})
            report["flags"].append({"key": "%s:%s:blueprint" % (bdays[-1], p), "platform": p,
                                    "kind": "blueprint", "count": info["blueprint"],
                                    "cap": 0, "day": bdays[-1]})
    return report


def render(report):
    ws = datetime.fromtimestamp(report["window_start"]).strftime("%m-%d %H:%M")
    we = datetime.fromtimestamp(report["window_end"]).strftime("%m-%d %H:%M")
    lines = ["social load audit, %s to %s local (counts only)" % (ws, we)]
    if not report["platforms"]:
        lines.append("  no social page loads in any browser profile or in the gate ledger")
    for p, i in sorted(report["platforms"].items()):
        srcs = ", ".join("%s %d" % (s, c[p]) for s, c in sorted(report["sources"].items())
                         if c.get(p))
        lines.append("  %s: browsers %d (%s), gate local %d, gate remote %d; worst rolling "
                     "hour %d; %d gaps under the floor" % (
                         p, i["browser"], srcs or "none", i["ledger_local"],
                         i["ledger_remote"], i["worst_hour"], i["gaps_under_min"]))
        for d, (b, lloc, lrem) in sorted(i["days"].items()):
            lines.append("    %s: browsers %d, gate local %d, gate remote %d" % (d, b, lloc,
                                                                                lrem))
        busy = sorted(i["hours"].items(), key=lambda kv: -kv[1])[:3]
        if busy:
            lines.append("    busiest clock hours: " + ", ".join("%s %d" % (h[11:], c)
                                                                 for h, c in busy))
    if report["synced_excluded"]:
        lines.append("  %d social visits synced from other devices were excluded"
                     % report["synced_excluded"])
    for e in report["errors"]:
        lines.append("  could not read %s" % e)
    if report["flags"]:
        lines.append("OVER THE CAPS:")
        for f in report["flags"]:
            lines.append("  " + flag_text(f))
    else:
        lines.append("nothing over the caps")
    return "\n".join(lines)


def flag_text(f):
    if f["kind"] == "blueprint":
        return ("%s: the Blueprint Chrome loaded %d %s pages (it should load none)"
                % (f["day"], f["count"], f["platform"]))
    if f["kind"] == "hour":
        return ("%s: %d %s loads in one rolling hour from %s (cap %d)"
                % (f["day"], f["count"], f["platform"], f["at"], f["cap"]))
    return "%s: %d %s loads in the %s (cap %d)" % (
        f["day"], f["count"], f["platform"],
        "day" if f["kind"] == "day" else "day via remote renderers", f["cap"])


def alert_line(flags):
    parts = [flag_text(f) for f in flags[:4]]
    more = " and %d more" % (len(flags) - 4) if len(flags) > 4 else ""
    return ("Social pacing alert. " + "; ".join(parts) + more +
            ". Details: python3 ~/.claude/scripts/social-load-audit.py")


def telegram_send(text):
    """One message via curl, the token passed on stdin so it never shows in ps."""
    try:
        env = json.load(open(SETTINGS_LOCAL)).get("env", {})
    except (OSError, ValueError):
        env = {}
    tok, cid = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")
    if not tok or not cid:
        return False, "no Telegram credentials in settings.local.json"
    try:
        th = json.load(open(THROTTLE))
        if float(th.get("until", 0)) / 1000.0 > time.time():
            return False, "Telegram throttled until %s" % datetime.fromtimestamp(
                float(th["until"]) / 1000.0).strftime("%H:%M")
    except (OSError, ValueError, TypeError):
        pass
    cfg = 'url = "https://api.telegram.org/bot%s/sendMessage"\n' % tok
    r = subprocess.run(["curl", "-s", "-m", "20", "-K", "-", "--data-urlencode",
                        "chat_id=%s" % cid, "--data-urlencode", "text=%s" % text],
                       input=cfg, capture_output=True, text=True)
    ok = r.returncode == 0 and '"ok":true' in r.stdout.replace(" ", "")
    return ok, "sent" if ok else "send failed (curl exit %d)" % r.returncode


def run(args, cfg, sources, ledger_rows, now, platform_of, state_dir, sender):
    tmpdir = tempfile.mkdtemp(prefix="social-audit-")
    try:
        report = audit(cfg, sources, ledger_rows, now, args.hours, platform_of, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    out = [json.dumps(report, sort_keys=True, default=str) if args.json else render(report)]
    if args.alert and report["flags"]:
        path = os.path.join(state_dir, ALERTED_NAME)
        try:
            done = json.load(open(path))
        except (OSError, ValueError):
            done = {}
        new = [f for f in report["flags"] if f["key"] not in done]
        if new:
            text = alert_line(new)
            if args.dry_run:
                out.append("WOULD SEND: " + text)
            else:
                ok, why = sender(text)
                out.append("telegram: %s" % why)
                if ok:
                    for f in new:
                        done[f["key"]] = f["count"]
                    os.makedirs(state_dir, mode=0o700, exist_ok=True)
                    tmp = path + ".tmp"
                    with open(tmp, "w") as fh:
                        json.dump(done, fh, sort_keys=True)
                    os.replace(tmp, path)
        else:
            out.append("already alerted for every crossing in this window")
    return report, "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="social-load-audit.py")
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--alert", action="store_true",
                   help="send one Telegram line for crossings not alerted before")
    p.add_argument("--dry-run", action="store_true", help="with --alert: print, never send")
    args = p.parse_args(argv)
    try:
        sg = load_gate_module()
        cfg = sg.load_config(CONFIG_PATH)
    except Exception as e:  # noqa: BLE001
        print("ERROR social-load-audit: %s" % e, file=sys.stderr)
        return 2

    def platform_of(url):
        return sg.platform_of_host(sg.host_of(url), cfg) if url else None

    ledger_rows = []
    ledger = os.path.join(STATE_DIR, sg.LEDGER_NAME)
    if os.path.exists(ledger):
        with open(ledger) as fh:
            for line in fh:
                try:
                    ledger_rows.append(json.loads(line))
                except ValueError:
                    continue
    report, text = run(args, cfg, history_sources(cfg), ledger_rows, time.time(), platform_of,
                       STATE_DIR, telegram_send)
    print(text)
    return 1 if report["flags"] else 0


if __name__ == "__main__":
    sys.exit(main())
