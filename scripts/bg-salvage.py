#!/usr/bin/env python3
"""
bg-salvage — what did a dead background worker actually finish?

WHY THIS EXISTS (2026-07-30). Four background workers died on usage limits in one
morning. Three were re-fired from scratch. Two of them had ALREADY COMPLETED their
entire 167-agent workflow (20 and 28 minutes of analysis) and died only at the
write-up step — the results sat intact in the workflow JSON the whole time.
Re-running from zero threw away ~50 minutes of finished compute, twice.

WHY IT WAS REBUILT (14-day audit 2026-08-28, P2). v1 answered "nothing
salvageable" ELEVEN times across 8 sessions while real finished work sat on
disk: 14 completed PNGs (d883c1c0 x3), 8 modified files in the repo (d2acf79d),
556 lines of a wu-6 handler plus a Redis helper uncommitted (86f27a8d x2), 6 of
12 action-billing units (fedeb0ce), 3.3 GB of completed video analysis
(db7a7487 x2), ~99K of findings in a subagents dir (1b80865d), and a COMMITTED
fix already in the tree (210038ff). Sessions that ignored the verdict recovered
the work; sessions that trusted it re-fired from scratch.

The bug was scope: v1 looked at workflow JSON and /tmp only. It never looked at
the git working tree, the deliverable directories, or the dead worker's own
transcript. This version checks FOUR sources and states each one's result
separately, so a bare "nothing salvageable" is only ever printed when all four
came back empty.

  1. GIT WORKING TREE — uncommitted changes and fresh commits in every repo the
     worker's brief names (this is the single biggest miss class).
  2. FRESH OUTPUT FILES — files newer than the worker's start time under the
     paths its brief names, plus /tmp and ~/Documents/Zalo Content.
  3. WORKER TRANSCRIPT — the run log's final assistant turn. The full report
     survives here even when the 4000-char Telegram handback truncated it, so
     this doubles as the fix for the bg-worker-report-4000-char-cap gap.
  4. SUBAGENT / WORKFLOW ARTIFACTS — completed workflow results and surviving
     per-agent transcripts.

Usage:
    python3 ~/.claude/scripts/bg-salvage.py                  # last 180 min
    python3 ~/.claude/scripts/bg-salvage.py --since 600      # last 10 h
    python3 ~/.claude/scripts/bg-salvage.py --dump <runId>   # workflow result -> /tmp
    python3 ~/.claude/scripts/bg-salvage.py --report <lane>  # worker's full report -> /tmp

Test fixture: python3 ~/.claude/scripts/bg-salvage.test.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def _env_path(var, default):
    v = os.environ.get(var)
    return Path(os.path.expanduser(v)) if v else default


HOME = Path.home()
PROJECTS = _env_path("BG_SALVAGE_PROJECTS_DIR", HOME / ".claude" / "projects")
BRIDGE = _env_path("BG_SALVAGE_BRIDGE_DIR", HOME / "dev" / "claude-telegram-bridge")
DEV = _env_path("BG_SALVAGE_DEV_DIR", HOME / "dev")
BG_RESULTS = BRIDGE / "bg-results.jsonl"
BG_INFLIGHT = BRIDGE / "bg-inflight.json"
BG_REPORTS = BRIDGE / "bg-reports"
RUNS = BRIDGE / "runs"

_roots_env = os.environ.get("BG_SALVAGE_OUTPUT_ROOTS")
OUTPUT_ROOTS = (
    [Path(os.path.expanduser(p)) for p in _roots_env.split(":") if p.strip()]
    if _roots_env
    else [Path("/tmp"), HOME / "Documents" / "Zalo Content", HOME / "Downloads"]
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".next", "dist", "build", ".venv"}
MAX_WALK_DEPTH = 3
MAX_FILES_PER_SOURCE = 20
LIMIT_SIGNALS = ("usage limit", "session limit", "weekly limit", "reached your", "rate limit")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def human_age(ts):
    mins = (time.time() - ts) / 60
    return f"{mins:.0f}m ago" if mins < 90 else f"{mins / 60:.1f}h ago"


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def _git(repo, *args):
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout if p.returncode == 0 else ""


# --------------------------------------------------------------------------
# worker discovery
# --------------------------------------------------------------------------
def load_workers(cutoff):
    """Every background worker seen since cutoff, from bg-inflight.json (which
    carries the brief, the pid and the start time) plus any orphan run log."""
    workers = []
    seen_logs = set()
    try:
        inflight = json.loads(BG_INFLIGHT.read_text())
    except (OSError, json.JSONDecodeError):
        inflight = {}
    if isinstance(inflight, dict):
        for key, rec in inflight.items():
            if not isinstance(rec, dict):
                continue
            try:
                started = float(rec.get("startedAt") or 0) / 1000.0
            except (TypeError, ValueError):
                started = 0.0
            if started and started < cutoff:
                continue
            log = Path(rec["log"]) if rec.get("log") else None
            if log:
                seen_logs.add(str(log))
            workers.append(
                {
                    "key": key,
                    "lane": rec.get("lane") or key.split("-")[0],
                    "pid": rec.get("pid"),
                    "alive": pid_alive(rec.get("pid")),
                    "started": started or cutoff,
                    "log": log,
                    "brief": str(rec.get("task") or ""),
                }
            )
    if RUNS.is_dir():
        for log in RUNS.glob("*.jsonl"):
            try:
                st = log.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff or str(log) in seen_logs:
                continue
            workers.append(
                {
                    "key": log.stem,
                    "lane": log.stem.split("-")[0],
                    "pid": None,
                    "alive": False,
                    "started": st.st_mtime,
                    "log": log,
                    "brief": recover_brief(log.stem),
                }
            )
    return sorted(workers, key=lambda w: w["started"], reverse=True)


def recover_brief(key):
    """The brief for a worker whose bg-inflight.json record is already gone.

    A worker's record leaves bg-inflight.json the moment it finishes or dies,
    and it takes the brief with it. Without a brief SOURCE 1 resolves ZERO
    repos and then prints "clean" anyway, which is exactly how an hour of
    finished work on a git worktree read as nothing salvageable (2026-09-21,
    worker bg-1790035092718). The brief survives in two places after the
    record is gone: the written report, and the results log.
    """
    try:
        text = (BG_REPORTS / f"{key}.md").read_text()
    except OSError:
        text = ""
    m = re.search(r"^## Task[ \t]*$(.*)", text, re.M | re.S) if text else None
    if m and m.group(1).strip():
        return m.group(1)
    try:
        lines = BG_RESULTS.read_text().splitlines()
    except OSError:
        return ""
    for line in reversed(lines[-300:]):
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        if key in str(rec.get("reportPath") or ""):
            return str(rec.get("prompt") or "")
    return ""


# --------------------------------------------------------------------------
# SOURCE 1 — git working tree
# --------------------------------------------------------------------------
def known_repos():
    repos = {}
    for base in (DEV, HOME / ".claude"):
        if base.name == ".claude" and (base / ".git").exists():
            repos[".claude"] = base
            continue
        if not base.is_dir():
            continue
        try:
            entries = list(base.iterdir())
        except OSError:
            continue
        for p in entries:
            if (p / ".git").exists():
                repos[p.name] = p
    return repos


def repos_named_in(brief):
    """Repos the brief actually names — by path or by bare folder name."""
    repos = known_repos()
    hits = {}
    if not brief:
        return hits
    for m in re.finditer(r"(?:~|/Users/[A-Za-z0-9_.-]+)/dev/([A-Za-z0-9_.-]+)", brief):
        name = m.group(1)
        if name in repos:
            hits[name] = repos[name]
    if re.search(r"(?:~|/Users/[A-Za-z0-9_.-]+)/\.claude\b", brief) and ".claude" in repos:
        hits[".claude"] = repos[".claude"]
    for name, path in repos.items():
        if name == ".claude":
            continue
        if re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", brief):
            hits[name] = path
    return hits


def worktrees_of(repo):
    """The LINKED worktrees of a repo, never the primary checkout.

    Briefs routinely tell a worker to work in a worktree off origin/main, so
    the salvageable tree is a sibling directory the brief never names and
    repos_named_in() therefore never resolves.
    """
    out = []
    porcelain = _git(repo, "worktree", "list", "--porcelain")
    try:
        primary = Path(repo).resolve()
    except OSError:
        primary = Path(repo)
    for line in porcelain.splitlines():
        if not line.startswith("worktree "):
            continue
        p = Path(line[len("worktree "):].strip())
        try:
            resolved = p.resolve()
        except OSError:
            resolved = p
        if resolved == primary or not p.is_dir():
            continue
        out.append(p)
    return out


def ahead_commits(repo):
    """Commits on HEAD that its upstream does not have.

    A worker that COMMITTED and then died leaves a clean tree, which today's
    dirty-tree check calls clean. Applied to linked worktrees only: a worktree
    exists because somebody made it for a job, whereas unpushed commits on a
    primary checkout are the normal resting state of most repos here and would
    make the common case noisier for no gain.
    """
    for rev in ("@{upstream}..HEAD", "origin/main..HEAD", "origin/master..HEAD"):
        out = [l for l in _git(repo, "log", rev, "--oneline", "-20").splitlines() if l.strip()]
        if out:
            return out
    return []


def worktree_touched_since(repo, started, dirty):
    """Did anything in this worktree move after the worker started?

    Without this gate the worktree arms turn one dead worker into a listing of
    every worktree the repo has ever had: delta-agents alone carries 16, all
    ahead of their upstream, none of them the work being salvaged. A worktree
    only counts when its newest commit, or one of its dirty paths, is younger
    than the worker.
    """
    ts = _git(repo, "log", "-1", "--format=%ct").strip()
    try:
        if ts and float(ts) >= started:
            return True
    except ValueError:
        pass
    for line in dirty[:40]:
        rel = line[3:].strip().strip('"')
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        try:
            if (Path(repo) / rel).stat().st_mtime >= started:
                return True
        except OSError:
            continue
    return False


def git_findings(worker):
    """Uncommitted changes and commits made since the worker started."""
    out = []
    targets = []
    for name, repo in sorted(repos_named_in(worker["brief"]).items()):
        targets.append((name, repo, False))
        for wt in worktrees_of(repo):
            targets.append((f"{name} [worktree {wt.name}]", wt, True))
    for name, repo, is_worktree in targets:
        porcelain = [l for l in _git(repo, "status", "--porcelain").splitlines() if l.strip()]
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(worker["started"]))
        commits = [
            l for l in _git(repo, "log", "--since", since, "--oneline", "-20").splitlines()
            if l.strip()
        ]
        if is_worktree and not worktree_touched_since(repo, worker["started"], porcelain):
            continue
        ahead = ahead_commits(repo) if is_worktree else []
        if not porcelain and not commits and not ahead:
            continue
        insertions = _git(repo, "diff", "--shortstat").strip().splitlines()
        out.append(
            {
                "repo": name,
                "path": repo,
                "dirty": porcelain,
                "commits": commits,
                "ahead": ahead,
                "branch": _git(repo, "branch", "--show-current").strip(),
                "worktree": is_worktree,
                "shortstat": insertions[0].strip() if insertions else "",
            }
        )
    return out


# --------------------------------------------------------------------------
# SOURCE 2 — fresh output files
# --------------------------------------------------------------------------
# Roots too broad to walk: scanning these would report the whole machine as
# "salvageable" and make the verdict meaningless again, in the opposite
# direction. A brief naming a path INSIDE them is still scanned.
TOO_BROAD = {Path("/"), Path("/Users"), Path("/home"), HOME, DEV, HOME / "Documents"}


def brief_dirs(brief):
    """Directories the brief names that actually exist on disk.

    A path that does not exist contributes NOTHING — falling back to its parent
    walked all of ~/dev when a brief named a repo that was never created.
    """
    dirs = set()
    if not brief:
        return dirs
    for m in re.finditer(r"(?:~|/Users/[A-Za-z0-9_.-]+)(?:/[A-Za-z0-9_.\- ]+)+", brief):
        raw = m.group(0).strip().rstrip(".,;:`'\")")
        p = Path(os.path.expanduser(raw))
        try:
            if p.is_dir():
                cand = p
            elif p.is_file():
                cand = p.parent
            else:
                continue
        except OSError:
            continue
        if cand.resolve() in {t.resolve() for t in TOO_BROAD if t.exists()}:
            continue
        dirs.add(cand)
    return dirs


def _walk_fresh(root, cutoff, budget):
    hits = []
    root = Path(root)
    if not root.is_dir():
        return hits
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if len(Path(dirpath).parts) - base_depth >= MAX_WALK_DEPTH:
            dirnames[:] = []
        for fn in filenames:
            if fn.startswith("."):
                continue
            p = Path(dirpath) / fn
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime >= cutoff and st.st_size > 0:
                hits.append((p, st.st_mtime, st.st_size))
                if len(hits) >= budget:
                    return hits
    return hits


def fresh_output_findings(worker):
    """Files written after the worker started, under the paths its brief names
    plus the standard deliverable roots."""
    cutoff = worker["started"]
    roots = list(brief_dirs(worker["brief"])) + OUTPUT_ROOTS
    seen, out = set(), []
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        hits = _walk_fresh(root, cutoff, MAX_FILES_PER_SOURCE)
        if hits:
            out.append({"root": root, "files": sorted(hits, key=lambda h: h[1], reverse=True)})
    return out


# --------------------------------------------------------------------------
# SOURCE 3 — the worker's own transcript
# --------------------------------------------------------------------------
def transcript_findings(worker):
    """Final assistant turn from the worker's run log. This is where a report
    that the 4000-char Telegram handback truncated survives in full."""
    log = worker.get("log")
    if not log or not Path(log).is_file():
        return None
    texts, died = [], False
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = rec.get("type")
                if kind == "result" and isinstance(rec.get("result"), str):
                    texts.append(rec["result"])
                elif kind == "assistant":
                    msg = rec.get("message") or {}
                    for block in msg.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text") or ""
                            if t.strip():
                                texts.append(t)
                elif kind == "rate_limit_event":
                    died = True
    except OSError:
        return None
    if not texts:
        return None
    tail = texts[-1]
    if not died:
        died = any(s in tail.lower() for s in LIMIT_SIGNALS)
    return {
        "log": Path(log),
        "turns": len(texts),
        "chars": len(tail),
        "truncated_handback": len(tail) > 4000,
        "limit_signal": died,
        "preview": tail[:600],
        "full": tail,
    }


# --------------------------------------------------------------------------
# SOURCE 4 — workflow results and subagent transcripts
# --------------------------------------------------------------------------
def find_workflow_runs(cutoff):
    runs = []
    if not PROJECTS.exists():
        return runs
    for wf in PROJECTS.glob("*/*/workflows/wf_*.json"):
        try:
            st = wf.stat()
        except OSError:
            continue
        if st.st_mtime < cutoff:
            continue
        try:
            data = json.loads(wf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        result = data.get("result")
        runs.append(
            {
                "path": wf,
                "run_id": data.get("runId") or wf.stem,
                "name": data.get("workflowName") or "?",
                "status": data.get("status") or "?",
                "agents": data.get("agentCount") or 0,
                "minutes": round((data.get("durationMs") or 0) / 60000, 1),
                "result_bytes": len(json.dumps(result)) if result else 0,
                "session": wf.parent.parent.name,
                "project": wf.parent.parent.parent.name,
                "mtime": st.st_mtime,
                "error": (str(data.get("error"))[:120] if data.get("error") else ""),
            }
        )
    return sorted(runs, key=lambda r: r["mtime"], reverse=True)


def count_agent_transcripts(project, session, run_id):
    d = PROJECTS / project / session / "subagents" / "workflows" / run_id
    if not d.is_dir():
        return 0, 0
    n = size = 0
    for p in d.iterdir():
        try:
            size += p.stat().st_size
        except OSError:
            continue
        n += 1
    return n, size


def loose_subagent_dirs(cutoff):
    """Subagent transcripts not attached to a workflow run (plain Agent calls)."""
    out = []
    if not PROJECTS.exists():
        return out
    for d in PROJECTS.glob("*/*/subagents"):
        best, n, size = 0, 0, 0
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime >= cutoff:
                n += 1
                size += st.st_size
                best = max(best, st.st_mtime)
        if n:
            out.append({"dir": d, "files": n, "bytes": size, "mtime": best})
    return sorted(out, key=lambda x: x["mtime"], reverse=True)


# --------------------------------------------------------------------------
# recent outcomes (context, not a salvage source)
# --------------------------------------------------------------------------
def recent_bg_outcomes(n=6):
    if not BG_RESULTS.exists():
        return []
    out = []
    try:
        lines = [l for l in BG_RESULTS.read_text(errors="replace").splitlines() if l.strip()]
    except OSError:
        return []
    for line in lines[-n:]:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        res = rec.get("result") or ""
        out.append(
            {
                "ts": rec.get("ts", ""),
                "task": (rec.get("prompt") or "")[:70].replace("\n", " "),
                "died_on_limit": any(s in res.lower() for s in LIMIT_SIGNALS),
                "result_chars": len(res),
            }
        )
    return out


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=180, help="minutes to look back")
    ap.add_argument("--dump", metavar="RUN_ID", help="write a workflow run's result to /tmp")
    ap.add_argument("--report", metavar="LANE_OR_KEY", help="write a worker's full final report to /tmp")
    args = ap.parse_args()
    cutoff = time.time() - args.since * 60

    runs = find_workflow_runs(cutoff)
    workers = load_workers(cutoff)

    if args.dump:
        for r in runs:
            if args.dump in r["run_id"]:
                data = json.loads(r["path"].read_text())
                out = Path(f"/tmp/salvage-{r['run_id']}.json")
                out.write_text(json.dumps(data.get("result"), indent=1))
                print(f"wrote {out} ({out.stat().st_size} bytes)")
                return 0
        print(f"run {args.dump} not found in the last {args.since}m", file=sys.stderr)
        return 1

    if args.report:
        for w in workers:
            if args.report in w["key"] or args.report == w["lane"]:
                t = transcript_findings(w)
                if not t:
                    continue
                out = Path(f"/tmp/salvage-report-{w['key']}.md")
                out.write_text(t["full"])
                print(f"wrote {out} ({len(t['full'])} chars, {t['turns']} assistant turns in the log)")
                return 0
        print(f"no transcript for '{args.report}' in the last {args.since}m", file=sys.stderr)
        return 1

    print(f"=== BG SALVAGE — last {args.since} min ===\n")

    found_any = False

    # ---- per-worker: sources 1, 2, 3 --------------------------------------
    print("WORKERS")
    if not workers:
        print("  (none seen in this window)")
    for w in workers:
        state = "ALIVE" if w["alive"] else "dead/finished"
        print(f"\n  [{w['key']}]  lane={w['lane']}  pid={w['pid']}  {state}  started {human_age(w['started'])}")
        if w["brief"]:
            print(f"    brief: {w['brief'].strip().splitlines()[0][:90]}")

        git = git_findings(w)
        if git:
            found_any = True
            for g in git:
                print(f"    SOURCE 1 GIT  {g['repo']} ({g['path']})")
                if g["dirty"]:
                    print(f"      <-- SALVAGEABLE: {len(g['dirty'])} uncommitted path(s)"
                          + (f"  [{g['shortstat']}]" if g["shortstat"] else ""))
                    for line in g["dirty"][:12]:
                        print(f"        {line}")
                    if len(g["dirty"]) > 12:
                        print(f"        ... and {len(g['dirty']) - 12} more")
                if g["commits"]:
                    print(f"      <-- SALVAGEABLE: {len(g['commits'])} commit(s) since the worker started")
                    for line in g["commits"][:8]:
                        print(f"        {line}")
                if g.get("ahead"):
                    branch = g.get("branch") or "detached HEAD"
                    print(f"      <-- SALVAGEABLE: worktree on {branch}, "
                          f"{len(g['ahead'])} commit(s) its upstream does not have")
                    for line in g["ahead"][:8]:
                        print(f"        {line}")
        elif repos_named_in(w["brief"]):
            print("    SOURCE 1 GIT  clean (no dirty tree, no new commits in the repos this brief names)")
        else:
            print("    SOURCE 1 GIT  NOT CHECKED: no repo resolved from this worker's brief"
                  + ("" if w["brief"] else " (brief unavailable)")
                  + " -- check by hand before re-running")

        fresh = fresh_output_findings(w)
        if fresh:
            found_any = True
            for f in fresh:
                print(f"    SOURCE 2 FILES  {f['root']}  <-- {len(f['files'])} file(s) newer than the worker start")
                for p, mt, size in f["files"][:8]:
                    print(f"        {p}  {size}B  ({human_age(mt)})")
                if len(f["files"]) > 8:
                    print(f"        ... and {len(f['files']) - 8} more")
        else:
            print("    SOURCE 2 FILES  none newer than the worker start")

        t = transcript_findings(w)
        if t:
            found_any = True
            flags = []
            if t["truncated_handback"]:
                flags.append(f"handback was truncated at 4000 chars, full text is {t['chars']}")
            if t["limit_signal"]:
                flags.append("died on a usage/rate limit")
            print(f"    SOURCE 3 TRANSCRIPT  {t['log']}")
            print(f"      <-- SALVAGEABLE: final turn is {t['chars']} chars"
                  + (f" ({'; '.join(flags)})" if flags else ""))
            print(f"      recover with: python3 ~/.claude/scripts/bg-salvage.py --report {w['key']}")
            preview = t["preview"].strip().splitlines()[:6]
            for line in preview:
                print(f"        | {line[:110]}")
        else:
            print("    SOURCE 3 TRANSCRIPT  no assistant output in the run log")

    # ---- source 4: workflows + subagents ----------------------------------
    print("\nSOURCE 4 — WORKFLOW RUNS")
    if not runs:
        print("  (none — no workflow launched in this window)")
    salvageable_runs = []
    for r in runs:
        n_agents, agent_bytes = count_agent_transcripts(r["project"], r["session"], r["run_id"])
        flag = ""
        if r["result_bytes"] > 2000:
            flag = "  <-- SALVAGEABLE: finished result on disk"
            salvageable_runs.append(r)
        elif r["status"] == "completed":
            flag = "  <-- completed (small/empty result — read journal.jsonl before re-running)"
        elif n_agents > 1:
            flag = f"  <-- PARTIAL: {n_agents} agent transcripts ({agent_bytes}B) survived"
            salvageable_runs.append(r)
        print(
            f"  {r['run_id']}  {r['name']}\n"
            f"    status={r['status']}  agents={r['agents']}  {r['minutes']}min  "
            f"result={r['result_bytes']}B  transcripts={n_agents}  ({human_age(r['mtime'])}){flag}"
        )
        if r["error"]:
            print(f"    error: {r['error']}")
    if salvageable_runs:
        found_any = True

    loose = loose_subagent_dirs(cutoff)
    print("\nSOURCE 4b — SUBAGENT TRANSCRIPTS")
    if not loose:
        print("  (none touched in this window)")
    for d in loose[:6]:
        found_any = True
        print(f"  {d['dir']}  {d['files']} file(s), {d['bytes']}B  ({human_age(d['mtime'])})")

    print("\nRECENT BG OUTCOMES")
    outcomes = recent_bg_outcomes()
    if not outcomes:
        print("  (none)")
    for o in outcomes:
        mark = "DIED-ON-LIMIT" if o["died_on_limit"] else "returned"
        print(f"  {o['ts']}  [{mark}, {o['result_chars']}ch]  {o['task']}")

    # ---- verdict ----------------------------------------------------------
    print("\n--- VERDICT ---")
    if found_any:
        print("WORK SURVIVED. Do NOT re-run from scratch — read the sources above first:")
        for r in salvageable_runs:
            print(f"  python3 ~/.claude/scripts/bg-salvage.py --dump {r['run_id']}")
        for w in workers:
            if transcript_findings(w):
                print(f"  python3 ~/.claude/scripts/bg-salvage.py --report {w['key']}")
        print("  git status / git diff in the repos flagged under SOURCE 1")
        print("Relaunch ONLY the remainder.")
    else:
        print("Nothing salvageable found in ANY of the four sources "
              "(git working tree, fresh output files, worker transcript, "
              "workflow/subagent artifacts) — a fresh relaunch is justified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
