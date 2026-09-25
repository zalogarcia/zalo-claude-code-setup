#!/usr/bin/env python3
"""Behaviour suite for bg-salvage.py — built around a FAKE DEAD-WORKER LAYOUT.

Run: python3 ~/.claude/scripts/bg-salvage.test.py

The bug this guards against (audit 2026-08-28, P2): the script printed
"nothing salvageable" while finished work sat on disk. So the central assertion
is inverted from the usual shape — for each of the four sources, planting work
in ONLY that source must flip the verdict away from "nothing salvageable", and
only a genuinely empty machine may produce it.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SCRIPT = os.path.expanduser("~/.claude/scripts/bg-salvage.py")
NOTHING = "Nothing salvageable found"
SURVIVED = "WORK SURVIVED"

passed = failed = 0
_dirs = []


def check(label, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS | {label}")
    else:
        failed += 1
        print(f"FAIL | {label}{(' — ' + detail) if detail else ''}")


class Layout:
    """A fake dead worker: bridge dir, run log, dev dir, output roots, projects."""

    def __init__(self, brief="", started_min_ago=10, with_log=True, log_text=None,
                 pid=999999, extra_records=()):
        self.root = tempfile.mkdtemp(prefix="bg-salvage-test-")
        _dirs.append(self.root)
        self.bridge = os.path.join(self.root, "bridge")
        self.runs = os.path.join(self.bridge, "runs")
        self.dev = os.path.join(self.root, "dev")
        self.out = os.path.join(self.root, "out")
        self.projects = os.path.join(self.root, "projects")
        for d in (self.bridge, self.runs, self.dev, self.out, self.projects):
            os.makedirs(d, exist_ok=True)
        self.started_ms = int((time.time() - started_min_ago * 60) * 1000)
        log_path = os.path.join(self.runs, "bg9-%d.jsonl" % (self.started_ms // 1000))
        inflight = {
            "bg9-%d-4242" % self.started_ms: {
                "pid": pid,  # 999999 is deliberately dead; os.getpid() is alive
                "lane": "bg9",
                "startedAt": str(self.started_ms),
                "log": log_path,
                "task": brief,
            }
        }
        with open(os.path.join(self.bridge, "bg-inflight.json"), "w") as f:
            json.dump(inflight, f)
        open(os.path.join(self.bridge, "bg-results.jsonl"), "w").close()
        self.log_path = log_path
        if with_log:
            with open(log_path, "w") as f:
                if log_text:
                    f.write(json.dumps({"type": "assistant", "message": {
                        "content": [{"type": "text", "text": log_text}]}}) + "\n")
                else:
                    f.write(json.dumps({"type": "system", "subtype": "init"}) + "\n")
                for rec in extra_records:
                    f.write(json.dumps(rec) + "\n")

    def env(self):
        return dict(
            os.environ,
            BG_SALVAGE_BRIDGE_DIR=self.bridge,
            BG_SALVAGE_DEV_DIR=self.dev,
            BG_SALVAGE_PROJECTS_DIR=self.projects,
            BG_SALVAGE_OUTPUT_ROOTS=self.out,
        )

    def make_repo(self, name, dirty=False, seed_stale=False):
        repo = os.path.join(self.dev, name)
        os.makedirs(repo, exist_ok=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        if seed_stale:
            # Otherwise the fixture's own seed commit is newer than the fake
            # worker and trips the "commits since the worker started" arm,
            # which has nothing to do with what the case is testing.
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "2026-01-02T03:04:05"
        for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", repo, *args], capture_output=True, env=env)
        open(os.path.join(repo, "seed.txt"), "w").write("seed\n")
        subprocess.run(["git", "-C", repo, "add", "seed.txt"], capture_output=True, env=env)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "seed"], capture_output=True, env=env)
        if dirty:
            open(os.path.join(repo, "handler.ts"), "w").write("x" * 500)
        return repo

    def make_worktree(self, repo, name, branch, dirty=False, commit=False, stale=False):
        """A linked worktree of `repo`, the shape a brief means by 'work in a
        worktree off origin/main'. `stale` backdates its commit so the
        freshness gate must drop it."""
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        seed = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                              capture_output=True, text=True, env=env).stdout.strip()
        subprocess.run(["git", "-C", repo, "update-ref", "refs/remotes/origin/main", seed],
                       capture_output=True, env=env)
        wt = os.path.join(self.dev, name)
        subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "-b", branch, wt],
                       capture_output=True, env=env)
        if commit:
            open(os.path.join(wt, "feature.ts"), "w").write("y" * 400)
            cenv = dict(env)
            if stale:
                old = "2026-01-02T03:04:05"
                cenv["GIT_AUTHOR_DATE"] = old
                cenv["GIT_COMMITTER_DATE"] = old
            subprocess.run(["git", "-C", wt, "add", "feature.ts"], capture_output=True, env=cenv)
            subprocess.run(["git", "-C", wt, "commit", "-qm", "the salvageable commit"],
                           capture_output=True, env=cenv)
        if dirty:
            open(os.path.join(wt, "wip.ts"), "w").write("z" * 300)
        return wt

    def make_orphan(self, key, task_text):
        """A worker whose bg-inflight record is already gone: only a run log
        and a written report survive. This is every FINISHED worker."""
        log = os.path.join(self.runs, f"{key}.jsonl")
        with open(log, "w") as f:
            f.write(json.dumps({"type": "system", "subtype": "init"}) + "\n")
        reports = os.path.join(self.bridge, "bg-reports")
        os.makedirs(reports, exist_ok=True)
        with open(os.path.join(reports, f"{key}.md"), "w") as f:
            f.write(f"# Background worker report: {key}\n\n- status: failed\n\n## Task\n\n{task_text}\n")
        return log

    def make_fresh_output(self, name="render-01.png"):
        p = os.path.join(self.out, name)
        open(p, "wb").write(b"\x89PNG" + b"0" * 200)
        return p

    def make_workflow(self, result_bytes=5000, status="completed"):
        d = os.path.join(self.projects, "-proj", "sess", "workflows")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "wf_abc123.json")
        json.dump({"runId": "wf_abc123", "workflowName": "qa-audit", "status": status,
                   "agentCount": 58, "durationMs": 1200000,
                   "result": {"findings": ["x" * result_bytes]}}, open(p, "w"))
        return p

    def make_subagents(self, n=4):
        d = os.path.join(self.projects, "-proj", "sess", "subagents", "workflows", "wf_zzz")
        os.makedirs(d, exist_ok=True)
        for i in range(n):
            open(os.path.join(d, f"agent-{i}.jsonl"), "w").write("{}\n" * 200)
        return d

    def run(self, *extra):
        p = subprocess.run(
            [sys.executable, SCRIPT, "--since", "180", *extra],
            capture_output=True, text=True, env=self.env(),
        )
        return p.returncode, p.stdout, p.stderr


def main():
    # 1. Truly empty machine: "nothing salvageable" is allowed.
    L = Layout(brief="# TASK\nDo a thing in ~/dev/nonexistent-repo.")
    rc, out, err = L.run()
    check("1a: exits 0 on an empty layout", rc == 0, err[:200])
    check("1b: an empty layout DOES say nothing salvageable", NOTHING in out)
    check("1c: all four sources are named in the verdict",
          "git working tree" in out and "worker transcript" in out)

    # 2. SOURCE 1 — uncommitted work in a repo the brief names.
    L = Layout(brief="# TASK\nImplement the handler in ~/dev/delta-agents.")
    L.make_repo("delta-agents", dirty=True)
    rc, out, _ = L.run()
    check("2a: dirty working tree flips the verdict", SURVIVED in out and NOTHING not in out)
    check("2b: names the repo and the dirty file", "delta-agents" in out and "handler.ts" in out)

    # 2c. a repo the brief does NOT name is not scanned (no false alarms).
    L = Layout(brief="# TASK\nWork only in ~/dev/zalo-os.")
    L.make_repo("delta-agents", dirty=True)
    rc, out, _ = L.run()
    check("2c: unnamed repo's dirt does not flip the verdict", NOTHING in out)

    # 2d. a bare repo NAME in the brief counts, not just a full path.
    L = Layout(brief="# TASK\nFix the gateway in the delta-agents monorepo.")
    L.make_repo("delta-agents", dirty=True)
    rc, out, _ = L.run()
    check("2d: bare repo name in the brief is matched", SURVIVED in out)

    # 3. SOURCE 2 — fresh deliverables and nothing else.
    L = Layout(brief="# TASK\nRender the frames.")
    L.make_fresh_output("render-01.png")
    L.make_fresh_output("render-02.png")
    rc, out, _ = L.run()
    check("3a: fresh output files flip the verdict", SURVIVED in out and NOTHING not in out)
    check("3b: names the files", "render-01.png" in out)

    # 3c. files OLDER than the worker start are not credited to it.
    L = Layout(brief="# TASK\nRender the frames.", started_min_ago=5)
    p = L.make_fresh_output("stale.png")
    old = time.time() - 3600
    os.utime(p, (old, old))
    rc, out, _ = L.run()
    check("3c: pre-existing files do not flip the verdict", NOTHING in out)

    # 4. SOURCE 3 — the worker's own transcript (the 4000-char-cap fix).
    big = "FULL REPORT\n" + ("x" * 9000)
    L = Layout(brief="# TASK\nAudit something.", log_text=big)
    rc, out, _ = L.run()
    check("4a: a final assistant turn flips the verdict", SURVIVED in out and NOTHING not in out)
    check("4b: flags that the 4000-char handback truncated it",
          "truncated at 4000" in out and f"full text is {len(big)}" in out)
    check("4c: prints the --report recovery command", "--report" in out)

    key = json.load(open(os.path.join(L.bridge, "bg-inflight.json")))
    key = list(key)[0]
    rc, out, err = L.run("--report", key)
    check("4d: --report writes the FULL report out", rc == 0 and "wrote /tmp/salvage-report-" in out)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    check("4e: the written report is the full length, not 4000 chars",
          bool(written) and os.path.getsize(written) == len(big))
    if written and os.path.exists(written):
        os.remove(written)

    # 5. SOURCE 4 — workflow result / subagent transcripts.
    L = Layout(brief="# TASK\nRun the audit workflow.")
    L.make_workflow()
    rc, out, _ = L.run()
    check("5a: a finished workflow result flips the verdict", SURVIVED in out and NOTHING not in out)
    check("5b: prints the --dump command", "--dump wf_abc123" in out)

    L = Layout(brief="# TASK\nRun the audit workflow.")
    L.make_subagents(4)
    rc, out, _ = L.run()
    check("5c: surviving subagent transcripts flip the verdict", SURVIVED in out and NOTHING not in out)

    # 6. The regression that started it all: work in git ONLY, with an empty
    #    workflow dir and an empty /tmp — exactly the v1 blind spot.
    L = Layout(brief="# TASK — fix wu-6\nWork in ~/dev/delta-agents. No workflow.")
    L.make_repo("delta-agents", dirty=True)
    rc, out, _ = L.run()
    check("6: the v1 blind spot (git-only work) is no longer 'nothing salvageable'",
          NOTHING not in out)

    # 7. MALFORMED inputs must not crash the script.
    L = Layout(brief="# TASK\nx")
    open(os.path.join(L.bridge, "bg-inflight.json"), "w").write("{ not json")
    rc, out, err = L.run()
    check("7a: corrupt bg-inflight.json still exits 0", rc == 0, err[:200])

    L = Layout(brief="# TASK\nx")
    with open(os.path.join(L.bridge, "bg-inflight.json"), "w") as f:
        json.dump({"weird": ["not", "a", "dict"], "empty": {}}, f)
    rc, out, err = L.run()
    check("7b: unexpected bg-inflight shapes still exit 0", rc == 0, err[:200])

    L = Layout(brief="# TASK\nx")
    with open(L.log_path, "w") as f:
        f.write("not json at all\n{\"type\":\"assistant\"}\n")
    rc, out, err = L.run()
    check("7c: a corrupt run log still exits 0", rc == 0, err[:200])

    L = Layout(brief="# TASK\nx", with_log=False)
    rc, out, err = L.run()
    check("7d: a missing run log still exits 0", rc == 0, err[:200])

    L = Layout(brief="# TASK\nx")
    shutil.rmtree(L.bridge)
    rc, out, err = L.run()
    check("7e: a missing bridge dir still exits 0", rc == 0, err[:200])

    # 8. --dump on an unknown run id fails loudly rather than silently.
    L = Layout(brief="# TASK\nx")
    rc, out, err = L.run("--dump", "wf_nope")
    check("8: --dump of an unknown run exits non-zero", rc != 0 and "not found" in err)

    # 9. WORKTREES (2026-09-21): a brief that says "work in a worktree off
    # origin/main" leaves the salvageable tree in a sibling directory the brief
    # never names. bg-1790035092718 left 34 files there and read as clean.
    L = Layout(brief="# TASK\nWork in a worktree off origin/main. Repo: ~/dev/delta-agents.")
    repo = L.make_repo("delta-agents")
    L.make_worktree(repo, "delta-agents-noor", "fix/greeting", dirty=True)
    rc, out, _ = L.run()
    check("9a: a dirty worktree flips the verdict", SURVIVED in out and NOTHING not in out)
    check("9b: the worktree is labelled as one, not as the checkout",
          "[worktree delta-agents-noor]" in out and "wip.ts" in out)

    # 9c. committed-then-died: a clean tree ahead of its upstream is still work.
    L = Layout(brief="# TASK\nWork in a worktree. Repo: ~/dev/delta-agents.")
    repo = L.make_repo("delta-agents")
    L.make_worktree(repo, "delta-agents-noor", "fix/greeting", commit=True)
    rc, out, _ = L.run()
    check("9c: a clean worktree AHEAD of upstream flips the verdict",
          SURVIVED in out and NOTHING not in out)
    check("9d: says which branch and shows the commit",
          "fix/greeting" in out and "the salvageable commit" in out)

    # 9e. the noise gate: an old worktree is not this worker's work. Without
    # this, one dead worker listed all 16 delta-agents worktrees.
    L = Layout(brief="# TASK\nWork in a worktree. Repo: ~/dev/delta-agents.")
    repo = L.make_repo("delta-agents", seed_stale=True)
    L.make_worktree(repo, "delta-agents-old", "feat/august", commit=True, stale=True)
    rc, out, _ = L.run()
    check("9e: a STALE worktree does not flip the verdict", NOTHING in out, out[-400:])

    # 9f. a repo with no worktrees prints exactly what it printed before.
    L = Layout(brief="# TASK\nImplement the handler in ~/dev/delta-agents.")
    L.make_repo("delta-agents", dirty=True)
    rc, out, _ = L.run()
    check("9f: no worktrees means no worktree lines", "[worktree" not in out)

    # 10. BRIEF RECOVERY: a finished worker's bg-inflight record is gone, so
    # SOURCE 1 resolved ZERO repos and printed "clean" anyway. That sentence is
    # what sent an hour of finished work to be re-run from scratch.
    L = Layout(brief="# TASK\nnothing here")
    repo = L.make_repo("delta-agents", dirty=True)
    L.make_orphan("bg7-99999999", "# TASK\nFix the gateway in ~/dev/delta-agents.")
    rc, out, _ = L.run()
    check("10a: the brief is recovered from the written report",
          SURVIVED in out and "handler.ts" in out)
    check("10b: no false 'clean' for the orphan worker",
          "clean (no dirty tree" not in out.split("bg7-99999999")[-1].split("SOURCE 2")[0])

    # 10c. when no repo can be resolved, say so instead of saying clean.
    L = Layout(brief="")
    L.make_orphan("bg7-88888888", "")
    rc, out, _ = L.run()
    check("10c: an unresolvable brief says NOT CHECKED, never clean",
          "NOT CHECKED" in out and "clean (no dirty tree" not in out, out[-400:])

    # 11. A LIVE worker is never a relaunch candidate (2026-09-25): a
    # rate_limit_event anywhere in a still-running worker's log flagged it
    # "died on a usage/rate limit", the verdict listed it under "Relaunch ONLY
    # the remainder", and M dispatched a second writer onto the same film
    # while the first was alive and finishing it.
    L = Layout(brief="# TASK\nBuild the film.", log_text="Waiting on the 4K render.",
               pid=os.getpid(), extra_records=[{"type": "rate_limit_event"}])
    rc, out, _ = L.run()
    live_key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    verdict = out.split("--- VERDICT ---")[-1]
    check("11a: a live worker is marked STILL RUNNING", "STILL RUNNING" in out, out[-600:])
    check("11b: a live worker is never flagged as died on a limit",
          "died on a usage/rate limit" not in out, out[-600:])
    check("11c: the verdict does not offer a live worker for relaunch",
          f"--report {live_key}" not in verdict and "do NOT relaunch" in verdict, verdict)

    # 11e. the real 2026-09-25 shape: the live worker STARTED long before the
    # salvage window, so its bg-inflight record was skipped and its fresh run
    # log came back as a pid-less "dead/finished" orphan.
    L = Layout(brief="# TASK\nBuild the film.", log_text="Waiting on the 4K render.",
               pid=os.getpid(), started_min_ago=600,
               extra_records=[{"type": "rate_limit_event"}])
    os.utime(L.log_path, None)  # the log is fresh even though the worker is old
    rc, out, _ = L.run()
    check("11e: a live worker older than the window is STILL RUNNING, not an orphan",
          "STILL RUNNING" in out and "dead/finished" not in out
          and "died on a usage/rate limit" not in out, out[-700:])

    # 11d. the same log on a DEAD worker still reads as died on a limit.
    L = Layout(brief="# TASK\nBuild the film.", log_text="Waiting on the 4K render.",
               extra_records=[{"type": "rate_limit_event"}])
    rc, out, _ = L.run()
    check("11d: a dead worker with a limit event is still flagged",
          "died on a usage/rate limit" in out and "STILL RUNNING" not in out, out[-600:])

    for d in _dirs:
        shutil.rmtree(d, ignore_errors=True)
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
