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
    """Stratified sample: census the top `cap * census_share`, random-sample the rest.

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
        for s in ordered:
            s["band"] = "all"
            s["weight"] = 1.0
        return ordered, {
            "method": "census",
            "cap": cap,
            "population": len(ordered),
            "selected": len(ordered),
            "coverage_pct": 100.0 if ordered else 0.0,
            "seed": seed,
            "strata": [{"name": "all", "population": len(ordered),
                        "drawn": len(ordered), "weight": 1.0, "draw": "census"}],
            "bias_statement": (
                "Census: every substantive session in the window was analysed. "
                "No sampling bias."
            ),
        }

    # The deep band is EXACTLY the slots it gets, so it really is a census.
    # 2026-09-27: the band was the top third (99 sessions) but only its top 40
    # were taken, under the label "census of the band" at weight 2.475. That
    # is a size-skewed head, not a census and not a random draw, so no weight
    # could expand it. Now: the top `deep_slots` by rank are the deep band and
    # all of them are analysed (weight 1.0); everything below is split in half
    # by rank into mid and light, and each half is a seeded random draw.
    deep_slots = min(len(ordered), max(1, int(round(cap * census_share))))
    rest = ordered[deep_slots:]
    half = (len(rest) + 1) // 2
    bands = [
        ("deep", ordered[:deep_slots]),
        ("mid", rest[:half]),
        ("light", rest[half:]),
    ]
    rest_slots = cap - deep_slots
    rest_pop = len(rest)
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
            taken = list(pool)
        else:
            taken, _ = draw(pool, k, seed)
        stratum = {
            "name": name,
            "population": len(pool),
            "drawn": len(taken),
            "weight": round(len(pool) / len(taken), 3) if taken else None,
            "band_bytes": [rank_key(pool[0])[0], rank_key(pool[-1])[0]] if pool else [],
            # Derived from what was drawn, never from the band's name.
            "draw": draw_label(len(pool), len(taken)),
        }
        for s in pool:
            s["band"] = name
        for s in taken:
            s["weight"] = stratum["weight"]
        selected.extend(taken)
        strata.append(stratum)
    pct = round(100.0 * len(selected) / len(ordered), 1)
    return selected, {
        "method": "stratified",
        "cap": cap,
        "population": len(ordered),
        "selected": len(selected),
        "coverage_pct": pct,
        "seed": seed,
        "census_share": census_share,
        "strata": strata,
        "bias_statement": bias_statement(strata, len(selected), len(ordered), pct),
    }


def draw_label(population, drawn):
    """The one place a stratum's draw is named, from the counts alone."""
    if population == 0:
        return "empty"
    if drawn == population:
        return "census"
    if drawn == 0:
        return "not sampled"
    return "seeded random"


def bias_statement(strata, selected, population, pct):
    """Built from the stratum records, so it cannot call a draw a census."""
    parts = [
        "STRATIFIED SAMPLE, NOT A CENSUS: {sel} of {pop} substantive sessions "
        "({pct}%).".format(sel=selected, pop=population, pct=pct)
    ]
    for st in strata:
        if st["draw"] == "census" and st["name"] == "deep":
            parts.append(
                "The {n} band (the {p} largest transcripts by bytes) is a census, "
                "every one analysed at weight 1.0, and is over-represented by "
                "design because defects concentrate there.".format(n=st["name"], p=st["population"])
            )
        elif st["draw"] == "census":
            # Only the deep band is the largest by design; a smaller band drawn
            # in full (population = cap + 1) is simply complete.
            parts.append(
                "The {n} band ({p} sessions) was analysed in full, every one at "
                "weight 1.0.".format(n=st["name"], p=st["population"])
            )
        elif st["draw"] == "seeded random":
            parts.append(
                "The {n} band is a seeded random draw of {d} of {p} at weight {w}.".format(
                    n=st["name"], d=st["drawn"], p=st["population"], w=st["weight"])
            )
        elif st["draw"] == "not sampled":
            parts.append(
                "The {n} band ({p} sessions) was NOT sampled; nothing about it is "
                "in this run.".format(n=st["name"], p=st["population"])
            )
    random_bands = [st["name"] for st in strata if st["draw"] == "seeded random"]
    if random_bands:
        parts.append(
            "The {b} {verb} seeded random: multiply a count there by its weight "
            "before reading it as a week total, and never read a band analysed "
            "in full as the week's rate.".format(
                b=" and ".join(random_bands) + (" bands" if len(random_bands) > 1 else " band"),
                verb="are" if len(random_bands) > 1 else "is",
            )
        )
    return " ".join(parts)


# A stratum's weight is population/drawn rounded to 3 places, so an honest
# weight is within half a unit of the exact ratio (plus float slack).
WEIGHT_TOLERANCE = 0.0005 + 1e-9


def check_sampling(sampling, selected):
    """Every way the sampling record can contradict the sample it describes.

    Returns a list of plain sentences; empty means consistent. The workflow's
    Verify stage runs the same checks on what the relay delivered, so a
    contradiction is caught here AND after the relay (2026-09-27: a stratum
    labelled census had drawn 40 of 99, and only the LLM verifier noticed).
    """
    errs = []
    method = sampling.get("method")
    strata = sampling.get("strata") or []
    if method == "census":
        if len(selected) != sampling.get("population"):
            errs.append("census of %s sessions delivered %d records"
                        % (sampling.get("population"), len(selected)))
        return errs
    if method != "stratified":
        return errs
    if not strata:
        return ["a stratified sample with no strata cannot be weighted"]
    if sum(st.get("drawn") or 0 for st in strata) != sampling.get("selected"):
        errs.append("strata drew %d but the record says %s selected"
                    % (sum(st.get("drawn") or 0 for st in strata), sampling.get("selected")))
    if sum(st.get("population") or 0 for st in strata) != sampling.get("population"):
        errs.append("strata cover %d sessions but the population is %s"
                    % (sum(st.get("population") or 0 for st in strata), sampling.get("population")))
    by_name = {}
    for st in strata:
        name, pop, drawn, w = st.get("name"), st.get("population"), st.get("drawn"), st.get("weight")
        by_name[name] = st
        label = str(st.get("draw") or "")
        expected = draw_label(pop or 0, drawn or 0)
        if label != expected:
            errs.append("the %s stratum is labelled %r but drew %s of %s, which is %r"
                        % (name, label, drawn, pop, expected))
        if drawn:
            want = round(pop / drawn, 3)
            # Compared with the exact ratio, half a unit either way: Python
            # rounds 137/16 = 8.5625 half-to-even (8.562), JS half-up (8.563),
            # and both are honest (QA 2026-09-27).
            if not isinstance(w, (int, float)) or abs(w - pop / drawn) > WEIGHT_TOLERANCE:
                errs.append("the %s stratum has weight %s, but %s of %s means %s"
                            % (name, w, drawn, pop, want))
        elif w is not None:
            errs.append("the %s stratum drew nothing but carries weight %s" % (name, w))
    counts = {}
    # Per-record problems are grouped by kind: 80 identical sentences bury
    # the one stratum error that matters.
    per_kind = {}

    def note(kind, rec):
        per_kind.setdefault(kind, []).append(str(rec.get("id"))[:8])

    for rec in selected:
        band = rec.get("band")
        if band not in by_name:
            note("no valid band, so it cannot be weighted", rec)
            continue
        counts[band] = counts.get(band, 0) + 1
        w = by_name[band].get("weight")
        if not isinstance(rec.get("weight"), (int, float)) or w is None or abs(rec["weight"] - w) > 0.001:
            note("a weight that disagrees with its stratum", rec)
        if not isinstance(rec.get("bytes"), int):
            note("no bytes", rec)
    for kind, ids in per_kind.items():
        errs.append("%d of %d selected records carry %s (first: %s)"
                    % (len(ids), len(selected), kind, ", ".join(ids[:3])))
    for name, st in by_name.items():
        if counts.get(name, 0) != (st.get("drawn") or 0):
            errs.append("the %s stratum says %s drawn but %d selected records name it"
                        % (name, st.get("drawn"), counts.get(name, 0)))
    stripped = str(sampling.get("bias_statement") or "").replace("NOT A CENSUS", "")
    census_bands = [n for n, st in by_name.items() if st.get("draw") == "census"]
    if re.search(r"\bis a census\b", stripped) and not census_bands:
        errs.append("the bias statement says census but no stratum is one")
    for n in by_name:
        if n not in census_bands and re.search(r"\b%s band\b[^.]*?\bis a census\b" % re.escape(str(n)), stripped):
            errs.append("the bias statement calls the %s band a census" % n)
    return errs


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
            # bytes, band and weight travel with every record: without them no
            # facet can say which stratum it came from, and the synthesis
            # weighting rule is not executable from the facets file (09-27).
            {k: s.get(k) for k in ("id", "path", "transcript_dir", "start",
                                   "last_activity", "lines", "bytes", "band",
                                   "weight", "user_msgs", "typed_msgs",
                                   "repos_touched", "primary_repo",
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
    # Checked on what was read back off the file, the same way the counts are.
    errors = check_sampling(sampling, summary["selected"])
    summary["sampling_check"] = {"ok": not errors, "errors": errors}
    text = json.dumps(summary)
    if a.summary_out:
        with open(a.summary_out, "w") as fh:
            fh.write(text)
    print(text)
    if errors:
        # Loud and non-zero: the workflow's manifest agent turns a non-zero
        # exit into script_error, so a self-contradicting sample never feeds
        # an 80-agent analysis wave as if it were honest.
        sys.stderr.write("SAMPLING SELF-CHECK FAILED: %s\n" % "; ".join(errors))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
