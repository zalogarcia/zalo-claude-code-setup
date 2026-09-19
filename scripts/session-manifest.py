#!/usr/bin/env python3
"""Build the weekly Claude Code session manifest and pick the analysis sample.

Why this exists as a script and not as an agent's bash steps: on 2026-09-19 the
manifest agent had to return 671 session records through a structured output and
hit its output-token limit, so it folded 232 trivial sessions into ONE pseudo
record. The week's trivial count read 141 when the true figure was 373. A file
scan does not belong in an LLM's output budget. The agent now runs this script
and relays a summary that is a few KB whatever the week looks like.

Usage:
  python3 session-manifest.py --days 7 --cap 80 [--exclude <session-id>]
                              [--out <path>] [--projects <dir>] [--now YYYY-MM-DD]
                              [--seed <string>] [--census-share 0.5]

Writes the full unabridged manifest to --out (default
~/.claude/usage-data/manifest-<days>d-<generated_on>.json) and prints ONE line of
JSON to stdout: counts, the selected sample, the sampling record, and the ids it
did not select. Nothing is ever dropped without being counted.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

HOME = os.path.expanduser("~")
REPO_RE = re.compile(rb"/Users/[A-Za-z0-9_.-]+/dev/([A-Za-z0-9_.-]+)")
TS_RE = re.compile(rb'"timestamp"\s*:\s*"(\d{4}-\d{2}-\d{2})')
USER_RE = re.compile(rb'"type"\s*:\s*"user"')
# A trivial-session group this size or larger is a machine cluster: it is gisted
# by representatives and counted in full, never expanded into one agent each.
CLUSTER_MIN = 20
CLUSTER_REPRESENTATIVES = 2


def iso_day(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def kind_of(text):
    """A job-kind signature: the opening of the first typed message, digits
    masked and whitespace collapsed. Two scheduled runs of the same job share
    it; two different jobs in the same lane do not."""
    t = re.sub(r"\d+", "#", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t[:48]


def scan_file(path, now_ts):
    """One pass over a transcript. Returns the metadata the manifest needs."""
    lines = 0
    user_msgs = 0
    typed_msgs = 0
    first_msg = ""
    first_day = None
    last_day = None
    repos = {}
    try:
        size = os.path.getsize(path)
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    try:
        with open(path, "rb") as fh:
            for raw in fh:
                lines += 1
                m = TS_RE.search(raw)
                if m:
                    day = m.group(1).decode()
                    if first_day is None:
                        first_day = day
                    last_day = day
                for rm in REPO_RE.finditer(raw):
                    name = rm.group(1).decode()
                    if "." in name:  # /Users/zalo/dev/CLAUDE.md is not a repo
                        continue
                    repos[name] = repos.get(name, 0) + 1
                if not USER_RE.search(raw):
                    continue
                try:
                    rec = json.loads(raw)
                except Exception:
                    continue
                if rec.get("type") != "user":
                    continue
                if rec.get("isMeta") or rec.get("isSidechain"):
                    continue
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = [b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text"]
                    if not parts:
                        continue
                    text = "\n".join(parts)
                else:
                    continue
                user_msgs += 1
                head = text.lstrip()[:400]
                if "<command-name>" in head or "local-command" in head:
                    continue
                if head.startswith("Caveat:"):
                    continue
                typed_msgs += 1
                if not first_msg:
                    first_msg = head
    except OSError:
        return None

    parent = os.path.basename(os.path.dirname(path))
    project = parent
    if project.startswith("-Users-zalo-"):
        project = project[len("-Users-zalo-"):]
    elif project == "-Users-zalo":
        project = "home"
    fallback_day = iso_day(mtime)
    top_repos = sorted(repos.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {
        "id": os.path.basename(path)[: -len(".jsonl")],
        "path": path,
        "transcript_dir": project,
        "start": first_day or fallback_day,
        "last_activity": last_day or fallback_day,
        "lines": lines,
        "bytes": size,
        "user_msgs": user_msgs,
        "typed_msgs": typed_msgs,
        "first_msg_kind": kind_of(first_msg),
        "repos_touched": [name for name, _ in top_repos],
        "primary_repo": top_repos[0][0] if top_repos else "",
        "in_progress": (now_ts - mtime) < 180,
    }


def rank_key(s):
    """Band variable: transcript BYTES, the honest proxy for work volume.

    Not lines: in this corpus a 53MB session holds 447 lines and a 24MB one
    holds 2358, because one tool result is one very long line, so ranking by
    lines mis-sorts real sessions by orders of magnitude. Not typed user
    messages either: 250 of this week's 277 substantive sessions have exactly
    one, because a background worker gets one brief and then runs for an hour,
    so that key is a near total tie.

    This is the BAND variable, not the selection. The 2026-09-19 defect was not
    the variable, it was taking the top 80 and calling it a sample.
    """
    return (s.get("bytes", 0), s.get("typed_msgs", 0), s.get("lines", 0))


def draw(pool, k, seed):
    """Deterministic pseudo-random draw: the k smallest hashes of seed+id."""
    if k >= len(pool):
        return list(pool), []
    scored = sorted(
        pool,
        key=lambda s: hashlib.md5((seed + "|" + s["id"]).encode()).hexdigest(),
    )
    return scored[:k], scored[k:]


def select(substantive, cap, seed, census_share):
    """Stratified sample: census the deep band, random-sample the rest.

    Returns (selected, sampling record). Every stratum carries the weight
    population/drawn so a week-level estimate can be reconstructed from an
    unequal-probability sample instead of being read off a biased head.
    """
    ordered = sorted(substantive, key=rank_key, reverse=True)
    if not ordered:
        # Not a census. A census of nothing reads downstream as a complete week.
        return [], {
            "method": "empty",
            "cap": cap,
            "population": 0,
            "selected": 0,
            "coverage_pct": 0.0,
            "seed": seed,
            "strata": [],
            "bias_statement": (
                "EMPTY SCAN: no substantive session was found in the window. "
                "This is not a clean week, it is a scan that found nothing, and "
                "nothing downstream should read it as coverage."
            ),
        }
    if len(ordered) <= cap:
        return ordered, {
            "method": "census",
            "cap": cap,
            "population": len(ordered),
            "selected": len(ordered),
            "coverage_pct": 100.0 if ordered else 0.0,
            "seed": seed,
            "strata": [{"name": "all", "population": len(ordered),
                        "drawn": len(ordered), "weight": 1.0}],
            "bias_statement": (
                "Census: every substantive session in the window was analysed. "
                "No sampling bias."
            ),
        }

    third = max(1, len(ordered) // 3)
    bands = [
        ("deep", ordered[:third]),
        ("mid", ordered[third: 2 * third]),
        ("light", ordered[2 * third:]),
    ]
    deep_slots = min(len(bands[0][1]), max(1, int(round(cap * census_share))))
    rest_slots = cap - deep_slots
    rest_pop = len(bands[1][1]) + len(bands[2][1])
    mid_slots = int(round(rest_slots * (len(bands[1][1]) / rest_pop))) if rest_pop else 0
    mid_slots = min(mid_slots, len(bands[1][1]))
    light_slots = min(rest_slots - mid_slots, len(bands[2][1]))
    # any rounding remainder goes back to mid
    leftover = rest_slots - mid_slots - light_slots
    if leftover > 0:
        add = min(leftover, len(bands[1][1]) - mid_slots)
        mid_slots += add

    plan = {"deep": deep_slots, "mid": mid_slots, "light": light_slots}
    selected = []
    strata = []
    for name, pool in bands:
        k = plan[name]
        if name == "deep":
            taken = pool[:k]
        else:
            taken, _ = draw(pool, k, seed)
        selected.extend(taken)
        strata.append({
            "name": name,
            "population": len(pool),
            "drawn": len(taken),
            "weight": round(len(pool) / len(taken), 3) if taken else None,
            "band_bytes": [rank_key(pool[0])[0], rank_key(pool[-1])[0]] if pool else [],
            "draw": "census of the band" if name == "deep" else "seeded random",
        })
    pct = round(100.0 * len(selected) / len(ordered), 1)
    bias = (
        "STRATIFIED SAMPLE, NOT A CENSUS: {sel} of {pop} substantive sessions "
        "({pct}%). The deep band (the {d} largest transcripts by bytes) is a "
        "census and is over-represented by design, because "
        "defects concentrate there. The mid and light bands are seeded random "
        "draws at weights {wm} and {wl}. Multiply a mid or light band count by "
        "its weight before reading it as a week total, and never read a deep "
        "band rate as the week's rate."
    ).format(
        sel=len(selected), pop=len(ordered), pct=pct, d=strata[0]["drawn"],
        wm=strata[1]["weight"], wl=strata[2]["weight"],
    )
    return selected, {
        "method": "stratified",
        "cap": cap,
        "population": len(ordered),
        "selected": len(selected),
        "coverage_pct": pct,
        "seed": seed,
        "census_share": census_share,
        "strata": strata,
        "bias_statement": bias,
    }


def cluster_trivial(trivial, seed):
    """Group machine-generated trivial sessions so the count survives the gists.

    A project with CLUSTER_MIN or more trivial sessions in one week is a poller
    or scratch lane, not a week of conversations. Two representatives are gisted
    and the whole group is counted. The 2026-09-19 run folded 232 such sessions
    into a single excluded record and under-reported trivial by 232.
    """
    groups = {}
    for s in trivial:
        # Same lane, same size shape AND the same opening message. Lane plus
        # size alone put 112 mail-watch triage runs in one group with 3 reply
        # drafts and 2 unrelated jobs, and two representatives cannot represent
        # five kinds of job (found by the independent verifier, 2026-09-19).
        key = "%s ~%d0 lines | %s" % (
            s["transcript_dir"], s["lines"] // 10, s.get("first_msg_kind", ""),
        )
        groups.setdefault(key, []).append(s)
    to_gist = []
    clusters = []
    for name, members in sorted(groups.items()):
        if len(members) >= CLUSTER_MIN:
            reps, _ = draw(members, CLUSTER_REPRESENTATIVES, seed)
            to_gist.extend(reps)
            clusters.append({
                "group": name,
                "kind": members[0].get("first_msg_kind", ""),
                "count": len(members),
                "represented_by": [r["id"] for r in reps],
                "member_ids": [m["id"] for m in members],
            })
        else:
            to_gist.extend(members)
    return to_gist, clusters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--cap", type=int, default=80)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--projects", default=os.path.join(HOME, ".claude", "projects"))
    ap.add_argument("--now", default="")
    ap.add_argument("--seed", default="")
    ap.add_argument("--census-share", type=float, default=0.5)
    ap.add_argument("--summary-out", default="")
    a = ap.parse_args()

    now_ts = time.time()
    generated_on = a.now or date.today().strftime("%Y-%m-%d")
    window_end = generated_on
    window_start = (datetime.strptime(generated_on, "%Y-%m-%d").date()
                    - timedelta(days=a.days)).strftime("%Y-%m-%d")
    seed = a.seed or generated_on

    cutoff = now_ts - a.days * 86400
    candidates = []
    root = a.projects
    for entry in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, entry)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(d, fn)
            if not os.path.isfile(p):
                continue
            try:
                if os.path.getmtime(p) < cutoff:
                    continue
            except OSError:
                continue
            candidates.append(p)

    candidate_total = len(candidates)
    excluded = []
    sessions = []
    for p in candidates:
        sid = os.path.basename(p)[: -len(".jsonl")]
        if a.exclude and sid == a.exclude:
            excluded.append({"id": sid, "reason": "own-session"})
            continue
        rec = scan_file(p, now_ts)
        if rec is None:
            excluded.append({"id": sid, "reason": "unreadable"})
            continue
        rec["carried_over"] = rec["start"] < window_start
        sessions.append(rec)

    substantive = [s for s in sessions if s["user_msgs"] >= 3 or s["lines"] >= 100]
    sub_ids = {s["id"] for s in substantive}
    trivial = [s for s in sessions if s["id"] not in sub_ids]
    selected, sampling = select(substantive, a.cap, seed, a.census_share)
    sel_ids = {s["id"] for s in selected}
    not_selected_ids = [s["id"] for s in substantive if s["id"] not in sel_ids]
    stub_targets, clusters = cluster_trivial(trivial, seed)

    full = {
        "generated_on": generated_on,
        "window_start": window_start,
        "window_end": window_end,
        "days": a.days,
        "cap": a.cap,
        "candidate_total": candidate_total,
        "substantive": substantive,
        "trivial": trivial,
        "excluded": excluded,
        "selected_ids": sorted(sel_ids),
        "stub_target_ids": [s["id"] for s in stub_targets],
        # Full records, so a stub batch agent can slice this array by index and
        # never needs the workflow to carry trivial-session records in its own
        # output budget. That budget is what folded 232 sessions on 2026-09-19.
        "stub_targets": stub_targets,
        "trivial_clusters": clusters,
        "sampling": sampling,
    }
    out_path = a.out or os.path.join(
        HOME, ".claude", "usage-data",
        "manifest-%dd-%s.json" % (a.days, generated_on),
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(full, fh)

    # Read the file back: the returned counts must come from what landed on
    # disk, not from memory, or a short write reports itself as a full one.
    with open(out_path) as fh:
        back = json.load(fh)
    accounted = (len(back["substantive"]) + len(back["trivial"])
                 + len(back["excluded"]))
    summary = {
        "generated_on": generated_on,
        "window_start": window_start,
        "window_end": window_end,
        "days": a.days,
        "cap": a.cap,
        "manifest_path": out_path,
        "candidate_total": candidate_total,
        "accounted_total": accounted,
        "substantive_count": len(back["substantive"]),
        "trivial_count": len(back["trivial"]),
        "excluded": back["excluded"],
        "selected": [
            {k: s[k] for k in ("id", "path", "transcript_dir", "start",
                               "last_activity", "lines", "user_msgs",
                               "typed_msgs", "repos_touched", "primary_repo",
                               "in_progress", "carried_over")}
            for s in back["substantive"] if s["id"] in sel_ids
        ],
        "not_selected_ids": not_selected_ids,
        "stub_target_count": len(stub_targets),
        "trivial_clusters": [
            {k: c[k] for k in ("group", "kind", "count", "represented_by")}
            for c in clusters
        ],
        "sampling": sampling,
        "scan_seconds": round(time.time() - now_ts, 1),
    }
    text = json.dumps(summary)
    if a.summary_out:
        with open(a.summary_out, "w") as fh:
            fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
