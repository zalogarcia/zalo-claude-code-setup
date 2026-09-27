#!/usr/bin/env python3
"""Tests for session-manifest.py, the weekly audit's scan and sampling step.

Run:  python3 ~/.claude/scripts/session-manifest.test.py

What this gates (2026-09-19 defects):
  - nothing is dropped: substantive + trivial + excluded == candidates scanned
  - the returned counts are read back OFF THE FILE, so a short write shows up
  - a machine lane is clustered and COUNTED in full, never folded into one record
  - selection is stratified with published weights and a bias statement, and a
    census says so instead of pretending to be a sample
  - the same seed picks the same sessions (a weekly number you cannot reproduce
    is not a measurement)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "session-manifest.py")

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ok   %s" % name)
    else:
        failed += 1
        print("  FAIL %s%s" % (name, " :: %s" % detail if detail else ""))


def write_session(root, group, sid, user_msgs, extra_lines=0, repo="delta-agents",
                  opening="do the thing"):
    d = os.path.join(root, group)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "%s.jsonl" % sid)
    rows = []
    rows.append(json.dumps({"type": "queue-operation", "timestamp": "2026-09-14T10:00:00.000Z"}))
    for i in range(user_msgs):
        rows.append(json.dumps({
            "type": "user", "timestamp": "2026-09-16T10:0%d:00.000Z" % (i % 10),
            "message": {"content": [{"type": "text", "text": "%s in /Users/zalo/dev/%s" % (opening, repo)}]},
        }))
    for i in range(extra_lines):
        rows.append(json.dumps({
            "type": "assistant", "timestamp": "2026-09-17T11:00:00.000Z",
            "message": {"content": [{"type": "text", "text": "x" * 20}]},
        }))
    with open(p, "w") as fh:
        fh.write("\n".join(rows) + "\n")
    return p


def run(root, out, **kw):
    cmd = [sys.executable, SCRIPT, "--projects", root, "--out", out, "--now", "2026-09-19"]
    for k, v in kw.items():
        cmd += ["--" + k.replace("_", "-"), str(v)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("script exited %d: %s" % (r.returncode, r.stderr[-800:]))
    return json.loads(r.stdout.strip().splitlines()[-1])


print("session-manifest.py")

with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "projects")
    # 6 substantive conversations of increasing size
    for i in range(6):
        write_session(root, "-Users-zalo-dev", "1000000%d-0000-4000-8000-00000000000%d" % (i, i),
                      user_msgs=5, extra_lines=100 * (i + 1))
    # 25 identical machine-lane transcripts: the devi-watch shape
    for i in range(25):
        write_session(root, "-Users-zalo-dev-claude-telegram-bridge-devi-watch-scratch",
                      "2000%04d-0000-4000-8000-000000000000" % i, user_msgs=1)
    # 4 short human sessions in another lane: below the cluster threshold
    for i in range(4):
        write_session(root, "-Users-zalo-dev-second-brain",
                      "3000%04d-0000-4000-8000-000000000000" % i, user_msgs=1)
    out = os.path.join(tmp, "manifest.json")

    s = run(root, out, days=7, cap=80)
    full = json.load(open(out))

    check("every candidate is accounted for",
          s["accounted_total"] == s["candidate_total"] == 35,
          "%s vs %s" % (s["accounted_total"], s["candidate_total"]))
    check("substantive and trivial split on the documented rule",
          s["substantive_count"] == 6 and s["trivial_count"] == 29,
          "%s / %s" % (s["substantive_count"], s["trivial_count"]))
    check("the counts returned are read back off the file",
          len(full["substantive"]) == s["substantive_count"]
          and len(full["trivial"]) == s["trivial_count"])
    check("a machine lane is clustered, not expanded one agent per session",
          any(c["count"] == 25 for c in s["trivial_clusters"]),
          json.dumps(s["trivial_clusters"]))
    check("the clustered lane keeps its true count in the trivial total",
          s["trivial_count"] == 29)
    check("only representatives are queued for gisting",
          s["stub_target_count"] == 2 + 4,
          str(s["stub_target_count"]))
    check("every clustered member id is on disk, so the cluster is not a fold",
          sum(len(c["member_ids"]) for c in full["trivial_clusters"]) == 25)
    check("a below-threshold lane is not clustered",
          all("second-brain" not in c["group"] for c in s["trivial_clusters"]))
    check("a full-coverage run calls itself a census",
          s["sampling"]["method"] == "census" and s["sampling"]["coverage_pct"] == 100.0)
    check("a census says it has no sampling bias",
          "No sampling bias" in s["sampling"]["bias_statement"])
    check("repos are attributed from the transcript, not the directory slug",
          full["substantive"][0]["primary_repo"] == "delta-agents",
          full["substantive"][0]["primary_repo"])
    check("last_activity is separate from start",
          full["substantive"][0]["start"] == "2026-09-14"
          and full["substantive"][0]["last_activity"] == "2026-09-17")

    # --- sampling path -------------------------------------------------------
    s2 = run(root, out, days=7, cap=3)
    check("a capped run draws exactly the cap", len(s2["selected"]) == 3, str(len(s2["selected"])))
    check("a capped run calls itself stratified", s2["sampling"]["method"] == "stratified")
    check("the bias statement leads with the fact that it is not a census",
          s2["sampling"]["bias_statement"].startswith("STRATIFIED SAMPLE, NOT A CENSUS"),
          s2["sampling"]["bias_statement"][:80])
    check("every stratum publishes a population, a draw and a weight",
          all(st["population"] and st["drawn"] is not None and "draw" in st
              for st in s2["sampling"]["strata"]),
          json.dumps(s2["sampling"]["strata"]))
    check("the sessions not analysed are named",
          len(s2["not_selected_ids"]) == 3, json.dumps(s2["not_selected_ids"]))
    check("selected plus not-selected equals the substantive population",
          len(s2["selected"]) + len(s2["not_selected_ids"]) == s2["substantive_count"])
    deep = s2["sampling"]["strata"][0]
    check("the deep band is a real census: drawn equals population, weight 1.0",
          deep["draw"] == "census" and deep["drawn"] == deep["population"]
          and deep["weight"] == 1.0, json.dumps(deep))

    s3 = run(root, out, days=7, cap=3)
    check("the same seed picks the same sessions",
          [x["id"] for x in s2["selected"]] == [x["id"] for x in s3["selected"]])
    s4 = run(root, out, days=7, cap=3, seed="other-seed")
    check("a different seed can pick differently in the random bands",
          [x["id"] for x in s4["selected"]] != [] )

    # --- exclusion -----------------------------------------------------------
    own = full["substantive"][0]["id"]
    s5 = run(root, out, days=7, cap=80, exclude=own)
    check("the audit's own session is excluded by id and recorded",
          any(e["id"] == own and e["reason"] == "own-session" for e in s5["excluded"]))
    check("an exclusion still reconciles against the candidate total",
          s5["accounted_total"] == s5["candidate_total"] == 35)
    check("the excluded session is not analysed",
          own not in [x["id"] for x in s5["selected"]])

# --- 2026-09-27 P1: the deep band was labelled census while taking the top 40 of 99 ---
def stratum_invariants(summary):
    """Every way a stratum record can contradict what was drawn."""
    errs = []
    sampling = summary["sampling"]
    for st in sampling["strata"]:
        if st["draw"] == "census" and not (st["drawn"] == st["population"] and st["weight"] == 1.0):
            errs.append("census label on %s but drawn %s of %s, weight %s"
                        % (st["name"], st["drawn"], st["population"], st["weight"]))
        if st["weight"] not in (None, 1.0) and st["draw"] != "seeded random":
            errs.append("weight %s on %s without a seeded draw" % (st["weight"], st["name"]))
        if st["draw"] == "seeded random" and not (0 < st["drawn"] < st["population"]):
            errs.append("seeded draw on %s with drawn %s of %s" % (st["name"], st["drawn"], st["population"]))
    stripped = sampling["bias_statement"].replace("NOT A CENSUS", "")
    census = [st["name"] for st in sampling["strata"] if st["draw"] == "census"]
    if re.search(r"\bis a census\b", stripped) and not census:
        errs.append("bias statement says census but no stratum is one")
    for st in sampling["strata"]:
        if st["draw"] != "census" and re.search(r"\b%s band\b[^.]*?\bis a census\b" % st["name"], stripped):
            errs.append("bias statement calls the %s band a census" % st["name"])
    return errs


with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "projects")
    # 30 substantive sessions, cap 6, census share 0.5: 3 deep slots against a
    # 10-session third, the exact shape of 2026-09-27 (40 slots, 99-session third).
    for i in range(30):
        write_session(root, "-Users-zalo-dev", "6000%04d-0000-4000-8000-000000000000" % i,
                      user_msgs=5, extra_lines=10 * (i + 1))
    out = os.path.join(tmp, "manifest.json")
    s8 = run(root, out, days=7, cap=6)
    full8 = json.load(open(out))
    errs = stratum_invariants(s8)
    check("no stratum label contradicts its draw (census means drawn == population)",
          not errs, "; ".join(errs))
    deep8 = s8["sampling"]["strata"][0]
    ranked = sorted(full8["substantive"], key=lambda x: (x["bytes"], x["typed_msgs"], x["lines"]),
                    reverse=True)
    top_ids = {x["id"] for x in ranked[:deep8["drawn"]]}
    deep_ids = {x["id"] for x in s8["selected"] if x.get("band") == "deep"}
    check("the deep band IS the top-k by the rank key, and all of it is analysed",
          deep8["population"] == deep8["drawn"] == 3 and deep_ids == top_ids,
          "%s / %s" % (json.dumps(deep8), sorted(deep_ids)))
    check("the other bands are seeded random draws with weight population/drawn",
          all(st["draw"] == "seeded random" and st["weight"] == round(st["population"] / st["drawn"], 3)
              for st in s8["sampling"]["strata"][1:] if st["drawn"]),
          json.dumps(s8["sampling"]["strata"]))
    check("strata partition the population exactly",
          sum(st["population"] for st in s8["sampling"]["strata"]) == 30
          and sum(st["drawn"] for st in s8["sampling"]["strata"]) == len(s8["selected"]) == 6)
    check("every selected record carries bytes, band and weight",
          all(isinstance(x.get("bytes"), int) and x.get("band") and isinstance(x.get("weight"), float)
              for x in s8["selected"]),
          json.dumps([{k: x.get(k) for k in ("id", "bytes", "band", "weight")} for x in s8["selected"]])[:400])
    check("each selected record's weight is its stratum's weight",
          all(x.get("weight") == {st["name"]: st["weight"] for st in s8["sampling"]["strata"]}.get(x.get("band"))
              for x in s8["selected"]))
    check("every substantive record in the file names its band",
          all(x.get("band") in ("deep", "mid", "light") for x in full8["substantive"]))
    check("the script publishes its own sampling self-check, and it passes",
          s8.get("sampling_check", {}).get("ok") is True, json.dumps(s8.get("sampling_check")))
    check("the bias statement does not call a sampled band a census",
          "deep band (the 3 largest" in s8["sampling"]["bias_statement"]
          and "mid and light bands are seeded random" in s8["sampling"]["bias_statement"],
          s8["sampling"]["bias_statement"])
    # the capped 6-session corpus from above also satisfies every invariant
    for cap in (2, 3, 4, 5):
        sx = run(root, out, days=7, cap=cap)
        e = stratum_invariants(sx)
        check("invariants hold at cap %d" % cap, not e and sx.get("sampling_check", {}).get("ok"), "; ".join(e))

# --- the self-check fails loudly on a contradiction ---------------------------
import importlib.util
_spec = importlib.util.spec_from_file_location("session_manifest", SCRIPT)
sm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sm)
bad = {
    "method": "stratified", "population": 298, "selected": 80,
    "strata": [
        {"name": "deep", "population": 99, "drawn": 40, "weight": 2.475, "draw": "census of the band"},
        {"name": "mid", "population": 99, "drawn": 20, "weight": 4.95, "draw": "seeded random"},
        {"name": "light", "population": 100, "drawn": 20, "weight": 5.0, "draw": "seeded random"},
    ],
    "bias_statement": "STRATIFIED SAMPLE, NOT A CENSUS: 80 of 298. The deep band (the 40 largest transcripts by bytes) is a census.",
}
bad_sel = ([{"id": "d%d" % i, "band": "deep", "weight": 2.475, "bytes": 1} for i in range(40)]
           + [{"id": "m%d" % i, "band": "mid", "weight": 4.95, "bytes": 1} for i in range(20)]
           + [{"id": "l%d" % i, "band": "light", "weight": 5.0, "bytes": 1} for i in range(20)])
check_sampling = getattr(sm, "check_sampling", lambda *a: ["check_sampling is missing"])
errs = check_sampling(bad, bad_sel)
check("the 2026-09-27 record (census label, 40 of 99) is caught by the self-check",
      any("deep" in e and "census" in e for e in errs), json.dumps(errs))
good = dict(bad, strata=[
    {"name": "deep", "population": 40, "drawn": 40, "weight": 1.0, "draw": "census"},
    {"name": "mid", "population": 129, "drawn": 20, "weight": 6.45, "draw": "seeded random"},
    {"name": "light", "population": 129, "drawn": 20, "weight": 6.45, "draw": "seeded random"},
], bias_statement="STRATIFIED SAMPLE, NOT A CENSUS: 80 of 298. The deep band (the 40 largest) is a census.")
good_sel = ([{"id": "d%d" % i, "band": "deep", "weight": 1.0, "bytes": 1} for i in range(40)]
            + [{"id": "m%d" % i, "band": "mid", "weight": 6.45, "bytes": 1} for i in range(20)]
            + [{"id": "l%d" % i, "band": "light", "weight": 6.45, "bytes": 1} for i in range(20)])
check("an honest record passes the self-check", check_sampling(good, good_sel) == [],
      json.dumps(check_sampling(good, good_sel)))
check("a record whose weight disagrees with its stratum is caught",
      check_sampling(good, good_sel[:-1] + [dict(good_sel[-1], weight=5.0)]) != [])
check("a selected record with no band is caught",
      check_sampling(good, good_sel[:-1] + [{"id": "x", "bytes": 1}]) != [])
check("band counts that disagree with drawn are caught",
      check_sampling(good, good_sel[:-1]) != [])

# --- a lane holding two different jobs is not one cluster -------------------
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "projects")
    for i in range(22):
        write_session(root, "-Users-zalo-dev", "4000%04d-0000-4000-8000-000000000000" % i,
                      user_msgs=1, opening="you triage inbound email for a solo business owner")
    for i in range(3):
        write_session(root, "-Users-zalo-dev", "5000%04d-0000-4000-8000-000000000000" % i,
                      user_msgs=1, opening="you are drafting a reply email on behalf of zalo")
    out = os.path.join(tmp, "manifest.json")
    s6 = run(root, out, days=7, cap=80)
    kinds = [c["kind"] for c in s6["trivial_clusters"]]
    check("the big repeated job is clustered",
          any(c["count"] == 22 for c in s6["trivial_clusters"]),
          json.dumps(s6["trivial_clusters"]))
    check("a different job in the same lane and size band is NOT swallowed by it",
          len(s6["trivial_clusters"]) == 1 and s6["stub_target_count"] == 2 + 3,
          "%d clusters, %d stub targets" % (len(s6["trivial_clusters"]), s6["stub_target_count"]))
    check("the cluster names the job kind its representatives stand for",
          kinds and "triage inbound email" in kinds[0], json.dumps(kinds))
    check("nothing is lost by clustering",
          s6["accounted_total"] == s6["candidate_total"] == 25)

# --- an empty scan is not a census -----------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "projects")
    os.makedirs(os.path.join(root, "-Users-zalo-dev"))
    out = os.path.join(tmp, "manifest.json")
    s7 = run(root, out, days=7, cap=80)
    check("an empty scan reports zero candidates", s7["candidate_total"] == 0)
    check("an empty scan does NOT call itself a census",
          s7["sampling"]["method"] == "empty", s7["sampling"]["method"])
    check("an empty scan says so where a human reads it",
          s7["sampling"]["bias_statement"].startswith("EMPTY SCAN"),
          s7["sampling"]["bias_statement"][:60])

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
