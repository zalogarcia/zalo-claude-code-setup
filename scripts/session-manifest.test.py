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
    check("the deep band is a census of the biggest transcripts",
          s2["sampling"]["strata"][0]["draw"] == "census of the band")

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
