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
     Plus the DRAFT REPORT (self-audit 2026-09-27, P3): workers write
     bg-reports/<runId>.draft.md before their verifier runs ($BG_REPORT_DRAFT,
     enforced by background-lane-guard), because 12 of 17 workers that lost
     their deliverable to a usage wall died inside the verifier. When a dead
     worker has no final report, `--report` writes that draft instead,
     labelled as a draft.
  4. SUBAGENT / WORKFLOW ARTIFACTS — completed workflow results and surviving
     per-agent transcripts.

Every worker also gets a PRODUCTION WRITES section (2026-09-29): each write
class tool call in its transcript and its subagents' transcripts (execute_sql
writes, migrations, edge deploys, GHL writes, git push, deploy CLIs, curl and
inline-code HTTP writes to a non-local host...), with the call's outcome. A
call with no result, because the worker died inside it, is listed first as
UNKNOWN. A dead worker's writes are work that already landed, so they also
rule out the "nothing salvageable" verdict.

Usage:
    python3 ~/.claude/scripts/bg-salvage.py                  # last 180 min
    python3 ~/.claude/scripts/bg-salvage.py --since 600      # last 10 h
    python3 ~/.claude/scripts/bg-salvage.py --dump <runId>   # workflow result -> /tmp
                                                             # (plus its agents' writes; a
                                                             # worker runId prints its writes)
    python3 ~/.claude/scripts/bg-salvage.py --report <lane>  # worker's full report -> /tmp
                                                             # (its draft, labelled, when
                                                             # it died without a final one)
    python3 ~/.claude/scripts/bg-salvage.py --writes <runId> # one run's PRODUCTION WRITES,
                                                             # any age (runId, lane or path)

Test fixture: python3 ~/.claude/scripts/bg-salvage.test.py
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


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
            log = Path(rec["log"]) if rec.get("log") else None
            if log:
                # Claim the log BEFORE the window check: an old live worker's
                # fresh log must not come back below as a pid-less orphan
                # reading "dead/finished" (2026-09-25).
                seen_logs.add(str(log))
            alive = pid_alive(rec.get("pid"))
            if started and started < cutoff and not alive:
                continue
            workers.append(
                {
                    "key": key,
                    "lane": rec.get("lane") or key.split("-")[0],
                    "pid": rec.get("pid"),
                    "alive": alive,
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
    has_result, result_error = False, False
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
                if kind == "result":
                    has_result = True
                    result_error = bool(rec.get("is_error"))
                    if isinstance(rec.get("result"), str):
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
        # A final report exists only when the run ENDED cleanly: a closing
        # result record that is not an error. A limit death ends on an error
        # result ("You've hit your session limit"), a killed worker on none.
        "final_ok": has_result and not result_error and bool(tail.strip()),
    }


def run_id_of(worker):
    """The bridge names a worker's files after its run log's basename."""
    log = worker.get("log")
    return Path(log).stem if log else worker["key"]


def draft_findings(worker):
    """bg-reports/<runId>.draft.md when it exists as a non-empty file."""
    for name in dict.fromkeys((run_id_of(worker), worker["key"])):
        p = BG_REPORTS / f"{name}.draft.md"
        try:
            st = p.stat()
        except OSError:
            continue
        if not p.is_file() or st.st_size == 0:
            continue
        return {"path": p, "size": st.st_size, "mtime": st.st_mtime}
    return None


def final_report_missing(t):
    return t is None or not t.get("final_ok")


def salvageable_draft(worker, t=None):
    """The draft, when this dead worker has one and no final report."""
    if worker.get("alive"):
        return None
    d = draft_findings(worker)
    if d and final_report_missing(t if t is not None else transcript_findings(worker)):
        return d
    return None


def draft_report_text(d, live=False):
    when = datetime.fromtimestamp(d["mtime"]).astimezone().isoformat(timespec="seconds")
    body = d["path"].read_text(encoding="utf-8", errors="replace")
    if live:
        head = ("DRAFT SO FAR, worker STILL RUNNING: this is the report it has "
                f"written so far ({when}), not a final one. Do not relaunch it.")
    else:
        head = ("DRAFT REPORT: this worker ended without a final report; below is the "
                f"last draft it wrote ({when}).")
    return head + "\n\n" + body, when, len(body)


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
# PRODUCTION WRITES: what the worker already did to live systems
# --------------------------------------------------------------------------
# WHY (2026-09-29). The Maya v10 worker (bg10) wrote the new prompt to the
# Delta production database with an execute_sql UPDATE, then died on a usage
# limit. This script reported its results and artifacts and said nothing
# about the write, so M relaunched it with a note saying nothing had reached
# production, and told Zalo the same. It had. Every worker now gets a
# PRODUCTION WRITES section: each write class tool call in its transcript and
# its subagents' transcripts, with the call's outcome, and a call that never
# got a result (the worker died inside it) listed first as UNKNOWN.
#
# "Is this SQL / database shell a write" is the unattended-write-guard's own
# classifier, imported read only the way its replay harness imports it, so the
# answer has one definition on this Mac; its shell tokenizer also feeds the
# deploy, push and HTTP rules below, which cover what that guard does not
# hold. When the guard cannot be loaded, plain regexes stand in; they
# over-flag rather than miss, and the section says it fell back.

_GUARD_SIBLING = Path(__file__).resolve().parent.parent / "hooks" / "unattended-write-guard.py"
WRITE_GUARD = _env_path(
    "BG_SALVAGE_WRITE_GUARD",
    _GUARD_SIBLING if _GUARD_SIBLING.is_file()
    else HOME / ".claude" / "hooks" / "unattended-write-guard.py",
)
_GUARD_STATE = {}


def write_guard():
    """The unattended-write-guard module, or None when it cannot be loaded."""
    if "mod" not in _GUARD_STATE:
        mod = None
        try:
            spec = importlib.util.spec_from_file_location("_bg_salvage_write_guard", str(WRITE_GUARD))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name in ("sql_write_reason", "bash_write_reason", "_scan", "_simple_commands", "_argv"):
                if not callable(getattr(mod, name, None)):
                    raise AttributeError(f"no {name}()")
        except (Exception, SystemExit) as e:  # a hook may exit at import
            _GUARD_STATE["err"] = f"{type(e).__name__}: {e}"[:160]
            mod = None
        _GUARD_STATE["mod"] = mod
    return _GUARD_STATE["mod"]


# ---- SQL ------------------------------------------------------------------
SQL_WRITE_VERB = re.compile(
    r"\b(UPDATE|INSERT|DELETE|UPSERT|MERGE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE)\b", re.I)
_ROW_LOCK = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?UPDATE\b", re.I)
_PLAN_ONLY = re.compile(r"\s*EXPLAIN\b(?![\s\S]*\bANALY[SZ]E\b)", re.I)


def _strip_sql_simple(sql):
    sql = re.sub(r"\$([A-Za-z_]\w*)?\$.*?\$\1\$", " '' ", sql, flags=re.S)
    sql = re.sub(r"'(?:[^']|'')*'", " '' ", sql)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r'"(?:[^"]|"")*"', " qident ", sql)


def sql_write(sql):
    """The write verb (or the guard's reason) when this SQL writes, else None.
    A write verb outside comments, string literals and quoted identifiers
    counts, as does anything the guard holds (a CTE UPDATE, a mutating
    function call); a row lock (FOR UPDATE) does not."""
    if not isinstance(sql, str) or not sql.strip():
        return None
    g = write_guard()
    stripped = None
    if g is not None:
        try:
            reason = g.sql_write_reason(sql)
            if reason:
                return reason
            if callable(getattr(g, "strip_sql", None)):
                stripped = g.strip_sql(sql)
        except Exception:
            stripped = None
    if stripped is None:
        stripped = _strip_sql_simple(sql)
    for stmt in _ROW_LOCK.sub(" ", stripped).split(";"):
        if _PLAN_ONLY.match(stmt):
            continue  # EXPLAIN without ANALYZE plans the statement, never runs it
        m = SQL_WRITE_VERB.search(stmt)
        if m:
            return m.group(1).upper()
    return None


# ---- URLs -----------------------------------------------------------------
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}
# POSTs that change nothing anyone relies on: a Telegram note to Zalo (the
# brief says so), a model call, an OAuth or Supabase sign-in token exchange.
_NOT_PRODUCTION_URLS = [re.compile(p, re.I) for p in (
    r"^https?://api\.telegram\.org/bot[^/\s]*/(send|get|edit|answer|copy|forward)",
    r"^https?://api\.openai\.com/v1/(chat|responses|completions|embeddings|audio|images|moderations)",
    r"^https?://api\.anthropic\.com/v1/messages",
    r"^https?://generativelanguage\.googleapis\.com/",
    r"^https?://oauth2\.googleapis\.com/token",
    r"/auth/v1/token\b",
    r"^https?://api\.elevenlabs\.io/v1/(text-to-speech|speech-to-text|sound-generation)",
    r"^https?://api\.segmind\.com/",
)]
# a {tok} / ${t} placeholder is part of the URL: the Telegram exemption needs
# the /sendDocument after bot{tok} (QA round 3)
_URL = re.compile(r"""https?://(?:\$?\{[^}\s]*\}|[^\s'"`<>)\]},;])+""")


def _host(url):
    u = str(url).strip().strip("'\"")
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", u):
        u = "http://" + u
    try:
        return (urlsplit(u).hostname or "").lower()
    except ValueError:
        return ""


def _url_exempt(url):
    """True when the URL is on this machine or on the not-production list."""
    h = _host(url)
    if h in _LOCAL_HOSTS or h.endswith(".localhost") or h.startswith("127."):
        return True
    u = str(url).strip().strip("'\"")
    return any(p.search(u) for p in _NOT_PRODUCTION_URLS)


# ---- Bash -----------------------------------------------------------------
_SHELLS = {"bash", "sh", "zsh", "dash"}
_OUT_REDIRS = {">", ">>", ">|", "&>", "&>>"}
_SSH_VALUE = set("bcDEeFIiJLlmOopQRSWw")


def _norm_path(p):
    p = os.path.expanduser(str(p).strip())
    return p[len("/private"):] if p.startswith("/private/tmp/") else p


def _ssh_text(args):
    """`ssh [opts] host cmd...` -> "cmd..." (fallback when the guard is absent)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            i += 2 if (len(a) == 2 and a[1] in _SSH_VALUE) else 1
            continue
        return " ".join(args[i + 1:])
    return ""


def _nested(words, bodies, g, depth, argv=None):
    """Commands a shell, eval or ssh runs from a quoted argument or stdin."""
    prog = os.path.basename(words[0])
    if prog in _SHELLS:
        for k in range(1, len(words)):
            a = words[k]
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                if k + 1 < len(words):
                    yield from _segments(words[k + 1], g, depth + 1)
                return
        for b in bodies:
            yield from _segments(b, g, depth + 1)
    elif prog == "eval":
        yield from _segments(" ".join(words[1:]), g, depth + 1)
    elif prog == "ssh":
        text = None
        if g is not None and argv is not None and callable(getattr(g, "_ssh_remote_command", None)):
            try:
                text = g._ssh_remote_command(argv)
            except Exception:
                text = None
        if text is None:
            text = _ssh_text(words[1:])
        if text:
            yield from _segments(text, g, depth + 1)
        for b in bodies:
            yield from _segments(b, g, depth + 1)


_FB_PREFIX = {"then", "do", "else", "elif", "if", "while", "until", "time", "exec", "command",
              "builtin", "nohup", "noglob", "!", "{", "}", "sudo", "env", "caffeinate", "nice",
              "xargs", "arch", "stdbuf", "doas"}


def _fb_strip(words):
    i = 0
    while i < len(words):
        w = words[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w) or w in _FB_PREFIX or (w.startswith("-") and i):
            i += 1
        elif w in ("timeout", "gtimeout"):
            i += 2
        elif w in ("npx", "bunx", "pnpx"):
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
        else:
            break
    return words[i:]


def _fallback_segments(command, depth):
    """Quote-aware split on ; & | ( ) < > per line, for when the guard's
    tokenizer is unavailable. Heredoc bodies come through as lines of their
    own, so this over-flags; it never under-flags a plain `git push`."""
    for line in command.splitlines():
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            toks = list(lex)
        except ValueError:
            toks = line.split()
        seg = []
        for t in toks + [";"]:
            if t and all(ch in "();<>|&" for ch in t):
                words = _fb_strip(seg)
                if words:
                    yield words, [], [], {}
                    yield from _nested(words, [], None, depth)
                seg = []
            else:
                seg.append(t)


def _segments(command, g, depth=0):
    """(argv words, stdin bodies, output redirect targets, NAME=value env) for
    every simple command the text runs, wrappers (sudo, timeout, npx, env ...)
    stripped. A bare `NAME=value` statement comes through with no words, so
    the caller can carry it to the commands after it."""
    if not isinstance(command, str) or not command.strip() or depth > 3:
        return
    if g is None:
        yield from _fallback_segments(command, depth)
        return
    subs = []
    for cmd in g._simple_commands(g._scan(command, subs)):
        argv, env = g._argv(cmd["words"])
        words = [w for w, _ in argv]
        if not words:
            if isinstance(env, dict) and env:
                yield [], [], [], env
            continue
        redirs = cmd.get("redirs") or []
        bodies = [t[2] for t in redirs if len(t) > 2 and t[0] in ("heredoc", "herestr")]
        outs = [t[2] for t in redirs if len(t) > 2 and t[0] == "redir" and t[1] in _OUT_REDIRS]
        yield words, bodies, outs, (env if isinstance(env, dict) else {})
        yield from _nested(words, bodies, g, depth, argv)
    for inner in subs:
        yield from _segments(inner, g, depth + 1)


def _nonflags(args):
    return [a for a in args if not a.startswith("-")]


def _flag_val(args, *names):
    """Value of `-X v`, `-Xv`, `--name v` or `--name=v`, else None."""
    for k, a in enumerate(args):
        for n in names:
            if a == n:
                return args[k + 1] if k + 1 < len(args) else ""
            if n.startswith("--") and a.startswith(n + "="):
                return a[len(n) + 1:]
            if not n.startswith("--") and a.startswith(n) and len(a) > len(n):
                return a[len(n):]
    return None


def _git_push(args):
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"):
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            break
    if i >= len(args) or args[i] != "push":
        return None
    rest = args[i + 1:]
    if {"-n", "--dry-run", "-h", "--help"} & set(rest):
        return None
    return "git push"


_GH_WRITES = {("pr", "merge"), ("workflow", "run"), ("workflow", "enable"), ("workflow", "disable"),
              ("run", "rerun"), ("run", "cancel"), ("release", "create"), ("release", "delete"),
              ("release", "upload"), ("release", "edit"), ("repo", "delete"), ("repo", "archive"),
              ("repo", "edit"), ("repo", "rename"), ("secret", "set"), ("secret", "delete"),
              ("variable", "set"), ("variable", "delete"), ("cache", "delete"),
              # a relaunch after an unlisted `gh pr create` opens a duplicate PR
              # (independent verifier: 46 real calls were unlisted)
              ("pr", "create"), ("pr", "close"), ("pr", "reopen"), ("pr", "comment"),
              ("pr", "review"), ("pr", "edit"), ("pr", "ready"), ("issue", "create"),
              ("issue", "close"), ("issue", "reopen"), ("issue", "comment"), ("issue", "edit"),
              ("issue", "delete"), ("label", "create"), ("label", "edit"), ("label", "delete")}


def _gh(args):
    if {"-h", "--help"} & set(args):
        return None
    nf = _nonflags(args)
    if tuple(nf[:2]) in _GH_WRITES:
        return "gh " + " ".join(nf[:2])
    if nf[:1] == ["api"]:
        method = _flag_val(args, "-X", "--method")
        if method is not None:
            return f"gh api {method.upper()}" if method.upper() not in ("GET", "HEAD", "") else None
        if any(a in ("-f", "-F", "--field", "--raw-field", "--input")
               or a.startswith(("--field=", "--raw-field=", "--input=")) for a in args):
            return "gh api POST"
    return None


_SUPABASE_REMOTE = {("functions", "deploy"), ("functions", "delete"), ("secrets", "set"),
                    ("secrets", "unset"), ("config", "push"), ("branches", "create"),
                    ("branches", "delete"), ("branches", "update"), ("branches", "pause"),
                    ("branches", "unpause"), ("postgres-config", "update"),
                    ("postgres-config", "delete"), ("domains", "activate"), ("domains", "create"),
                    ("domains", "delete"), ("domains", "reverify"), ("vanity-subdomains", "activate"),
                    ("vanity-subdomains", "delete"), ("network-restrictions", "update"),
                    ("ssl-enforcement", "update"), ("sso", "add"), ("sso", "remove"),
                    ("sso", "update"), ("projects", "create"), ("projects", "delete"),
                    ("orgs", "create"), ("storage", "cp"), ("storage", "mv"), ("storage", "rm")}


def _supabase(args, with_db):
    if {"-h", "--help", "--dry-run"} & set(args):
        return None
    nf = _nonflags(args)
    remote_db = "--linked" in args or any(a.startswith("--db-url") for a in args)
    for a, b in zip(nf, nf[1:]):
        if (a, b) in _SUPABASE_REMOTE:
            if a == "storage" and "--local" in args:
                return None
            return f"supabase {a} {b}"
        if with_db and ((a, b) in {("db", "push"), ("migration", "repair")} or (
                remote_db and (a, b) in {("db", "reset"), ("migration", "up"), ("migration", "down")})):
            return f"supabase {a} {b}"
    return None


_VERCEL_VALUE = {"--token", "-t", "--scope", "-S", "--cwd", "--local-config", "-A",
                 "--global-config", "-Q", "--team", "-T", "--build-env", "-b", "--env", "-e",
                 "--meta", "-m", "--regions", "--target"}
_VERCEL_DEPLOYS = {"deploy", "promote", "rollback", "redeploy", "remove", "rm"}
_VERCEL_NESTED = {"alias", "domains", "domain", "dns", "env", "certs", "cert", "project",
                  "projects", "integration", "secrets", "secret", "target", "targets", "blob",
                  "teams", "git", "webhooks"}
_VERCEL_NESTED_WRITES = {"set", "add", "rm", "remove", "create", "delete", "update", "put", "del",
                         "connect", "disconnect", "invite"}


def _vercel(args):
    if {"-h", "--help", "-v", "--version"} & set(args):
        return None
    nf, i = [], 0
    while i < len(args):
        a = args[i]
        if a in _VERCEL_VALUE:
            i += 2
            continue
        if not a.startswith("-"):
            nf.append(a)
        i += 1
    if not nf:
        return "vercel deploy" + (" --prod" if "--prod" in args else "")  # bare `vercel` deploys
    sub = nf[0]
    if sub in _VERCEL_DEPLOYS:
        return f"vercel {sub}"
    if sub in _VERCEL_NESTED and len(nf) > 1 and nf[1] in _VERCEL_NESTED_WRITES:
        return f"vercel {sub} {nf[1]}"
    if sub.startswith((".", "/", "~")):
        return "vercel deploy"  # `vercel ./dir` deploys the directory
    return None


_AWS_GLOBAL_VALUE = {"--region", "--profile", "--output", "--query", "--endpoint-url", "--color",
                     "--ca-bundle", "--cli-read-timeout", "--cli-connect-timeout",
                     "--cli-binary-format"}
_AWS_WRITE_OP = re.compile(
    r"^(put|create|delete|update|deploy|run|send|invoke|register|deregister|terminate|modify|set|stop|"
    r"start|execute|remove|add|tag|untag|rotate|cancel|reset|enable|disable|import|associate|"
    r"disassociate|replace|attach|detach|publish|reboot|restore|batch-write|batch-delete|"
    r"batch-put|copy|upload|restart|purge|change|force|admin-)")
_AWS_READS = {("logs", "start-query"), ("logs", "stop-query"), ("logs", "start-live-tail")}


def _aws(args):
    if "help" in args or "--help" in args:
        return None
    nf, i = [], 0
    while i < len(args):
        a = args[i]
        if a in _AWS_GLOBAL_VALUE:
            i += 2
            continue
        if not a.startswith("-"):
            nf.append(a)
        i += 1
    if len(nf) < 2:
        return None
    svc, op = nf[0], nf[1]
    if svc == "s3":
        if op in ("rm", "mv", "rb", "mb"):
            return f"aws s3 {op}"
        if op in ("cp", "sync") and len(nf) > 3 and nf[3].startswith("s3://"):
            return f"aws s3 {op} to {nf[3]}"
        return None
    if (svc, op) in _AWS_READS or not _AWS_WRITE_OP.match(op):
        return None
    return f"aws {svc} {op}"


_ASC_WRITE_WORDS = {"create", "update", "delete", "submit", "set", "add", "remove", "attach",
                    "detach", "upload", "cancel", "release", "expire", "invite", "revoke",
                    "publish", "modify", "replace", "reset", "approve", "reject", "enable",
                    "disable", "assign", "unassign"}


def _asc(args):
    if {"-h", "--help"} & set(args) or args[:1] == ["help"]:
        return None
    i, path = 0, []
    while i < len(args) and args[i].startswith("-"):
        i += 1 if "=" in args[i] else 2  # leading global flags take a value (--profile p)
    while i < len(args) and not args[i].startswith("-"):
        path.append(args[i])
        i += 1
    if "--confirm" in args:
        return "asc " + " ".join(path[:3]) + " --confirm"
    words = {w for p in path for w in p.lower().split("-")}
    return ("asc " + " ".join(path[:4])) if words & _ASC_WRITE_WORDS else None


_CAPGO_READS = {"list", "ls", "doctor", "info", "login", "help", "whoami", "currentbundle"}


def _capgo(args):
    if {"-h", "--help", "--version", "-V"} & set(args):
        return None
    nf = _nonflags(args)[:2]
    if not nf or any(v.lower() in _CAPGO_READS for v in nf):
        return None
    return "capgo " + " ".join(nf)


_DEPLOY_CLIS = {"wrangler": {"deploy", "publish", "delete", "rollback"},
                "fly": {"deploy", "destroy"}, "flyctl": {"deploy", "destroy"},
                "netlify": {"deploy"}, "firebase": {"deploy"}, "railway": {"up", "redeploy"},
                "eas": {"submit", "update"}}
_STRIPE_WRITES = {"create", "update", "delete", "post", "cancel", "refund", "trigger"}


# ---- inline code (node -e, python3 - <<EOF, a script the worker wrote) ------
_CODE_RUNNERS = {"node", "deno", "bun", "tsx", "ts-node", "python", "python3"}
# supabase-js is `.from('t')`, supabase-py is `.table('t')` / `.from_('t')`: matched
# per language, so a Python script that merely quotes a JS snippet is not a write.
_SBJS_WRITE = re.compile(
    r"""\.from\(\s*['"`]([\w.-]+)['"`]\s*\)[^;]{0,300}?\.(update|insert|upsert|delete)\s*\(""")
_SBPY_WRITE = re.compile(
    r"""\.(?:table|from_)\(\s*['"]([\w.-]+)['"]\s*\)[^;]{0,300}?\.(update|insert|upsert|delete)\s*\(""")
_STORAGE_WRITE = re.compile(r"""\.storage\s*\.from\([^)]*\)\s*\.(upload|remove|move|update|copy)\s*\(""")
_RPC = re.compile(r"""\.rpc\(\s*['"`]([\w.]+)['"`]""")
_HTTP_WRITE = re.compile(
    r"""\bmethod\s*[:=]\s*['"`](POST|PUT|PATCH|DELETE)['"`]"""
    r"""|\b(?:requests|httpx|axios)\s*\.\s*(post|put|patch|delete)\s*\("""
    r"""|\.request\(\s*['"](POST|PUT|PATCH|DELETE)['"]""", re.I)
# The method taken from a variable (argv, a config file, a helper's parameter):
# `{ method, body }`, `method: m`, `requests.request(method, url)` (QA round 2:
# an admin wrapper run as `node adm.mjs PATCH /admin/...` was invisible).
_METHOD_VAR = re.compile(r"""\bmethod\s*(?::|=(?!=))\s*(?![='"`\s])(?![^,}\n]*\.method\(\))"""
                         r"""|[{,]\s*method\s*[,}]""")
_METHOD_ARG = re.compile(r"""\.request\(\s*(?!['"`\s])[A-Za-z_]""")
# ... and only inside an HTTP options object or call, one that also carries
# headers or a body: not a request log line ({ url, method: r.method() }) and
# not a DevTools JSON-RPC message ({ id, method, params }), 351-run replay.
_HTTP_OPTS = re.compile(r"\b(?:headers|body|data|json)\b")


def _method_is_variable(code):
    if _METHOD_ARG.search(code):
        return True
    for m in _METHOD_VAR.finditer(code):
        start = max(code.rfind("{", 0, m.start() + 1), code.rfind("(", 0, m.start() + 1), 0)
        end = code.find("}", m.end())
        window = code[start:(end if end != -1 else m.end() + 200)][:400]
        if _HTTP_OPTS.search(window) and not re.search(r"\bparams\b|\bjsonrpc\b", window):
            return True
    return False
_HTTP_CALL = re.compile(r"""\bfetch\s*\(|\baxios\b|\bhttps?\.request\s*\(|\brequests\s*\.|\bhttpx\s*\."""
                        r"""|\burllib\.request\b|\bgot\s*\(|\bundici\b""")
_WRITE_METHOD_LITERAL = re.compile(r"""['"`](POST|PUT|PATCH|DELETE)['"`]""", re.I)
# A write through a client instance: requests.Session() -> s.post, httpx.Client()
# -> client.patch, axios.create() -> api.put (QA round 3). Only in code that
# makes HTTP calls, so an Express `app.post('/hook', h)` is not one.
_CLIENT_WRITE = re.compile(r"\b(?:session|sess|client|api|http|s)\s*\.\s*(post|put|patch|delete)\s*\(",
                           re.I)
_WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_RPC_WRITE_WORDS = {"SET", "INSERT", "UPDATE", "DELETE", "UPSERT", "CREATE", "DROP", "APPLY",
                    "RESET", "PURGE", "SYNC", "MARK", "RECORD", "ENQUEUE", "CLAIM", "ASSIGN",
                    "ARCHIVE", "ROTATE", "SEND", "ADD", "REMOVE", "SAVE", "CANCEL", "APPROVE",
                    "CREDIT", "DEBIT", "CHARGE", "REFUND", "GRANT", "REVOKE", "INCREMENT"}


def _is_runner(prog):
    return prog in _CODE_RUNNERS or re.fullmatch(r"python3\.\d+", prog) is not None


def _written_body(path, written):
    n = _norm_path(path)
    if n in written:
        return written[n]
    if not n.startswith("/"):
        tail = "/" + n.lstrip("./")
        hits = [v for k, v in written.items() if k.endswith(tail)]
        if hits:
            return hits[-1]
    return None


_SCRATCH_ROOTS = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")


def _script_body(path, written):
    """What a script the worker ran contains: the transcript's own copy (Write,
    Edit, a heredoc), else the file itself when it is a scratch file still on
    disk. Scratch only: a long-lived repo tool (mail_watch.py) carries write
    paths it takes only on some flags, and reading it would flag every read."""
    body = _written_body(path, written)
    if body is not None:
        return body
    p = _norm_path(path)
    try:
        if p.startswith("/tmp/") or os.path.realpath(p).startswith(_SCRATCH_ROOTS):
            if os.path.isfile(p) and os.path.getsize(p) <= 512_000:
                with open(p, encoding="utf-8", errors="replace") as f:
                    return f.read()
    except (OSError, ValueError):
        pass
    return None


# Runner flags whose value is the NEXT word: without this, `node -r
# dotenv/config x.mjs` read "dotenv/config" as the script (QA round 2).
_NODE_VALUE = {"-r", "--require", "--import", "--loader", "--experimental-loader", "--env-file",
               "--env-file-if-exists", "--input-type", "-C", "--conditions", "--title",
               "--disable-warning", "--watch-path"}
_RUNNER_VALUE = {
    "node": _NODE_VALUE,
    "tsx": _NODE_VALUE | {"--tsconfig"},
    "ts-node": {"-r", "--require", "-P", "--project", "-O", "--compiler-options", "-C",
                "--compiler", "--cwd", "--dir", "-I", "--ignore"},
    "deno": {"-c", "--config", "--import-map", "--location", "--seed", "--cert", "--lock", "-L",
             "--log-level"},
    "bun": {"-r", "--preload", "--require", "--import", "-c", "--config", "--env-file", "--cwd",
            "--tsconfig-override", "--conditions", "--main-fields", "-d", "--define", "-l",
            "--loader", "--port"},
    "python": {"-W", "-X", "-Q"},
}


def _code_of(prog, args, bodies, written):
    """[(where, code, script args)] this runner executes: -e/-c text, stdin,
    or a script whose body the transcript wrote earlier (Write tool or a
    heredoc), with the words the script was run with."""
    py = prog.startswith("python")
    value_flags = _RUNNER_VALUE["python" if py else prog] if (py or prog in _RUNNER_VALUE) else set()
    code_flags = ("-e", "--eval", "-p", "--print") + (("-c",) if py else ())
    out, script, i = [], None, 0
    while i < len(args):
        a = args[i]
        if a in code_flags and i + 1 < len(args):
            out.append((f"{prog} {a}", args[i + 1], args[i + 2:]))
            i += 2
            continue
        if a.startswith("--eval="):
            out.append((f"{prog} --eval", a[len("--eval="):], args[i + 1:]))
        elif a in ("run", "eval") and prog in ("deno", "bun") and script is None:
            if a == "eval" and i + 1 < len(args):
                out.append((f"{prog} eval", args[i + 1], args[i + 2:]))
                i += 2
                continue
        elif py and a == "-m":
            return []  # a module run (python3 -m http.server), not a script of the worker's
        elif a in value_flags:
            i += 2
            continue
        elif not a.startswith("-"):
            script = a
            break
        i += 1
    if out:
        return out
    if script is None:
        return [(f"{prog} stdin", b, []) for b in bodies]
    body = _script_body(script, written)
    return [(f"{prog} {script}", body, args[i + 1:])] if body else []


# A Postgres client, not a bare `.execute(`: sqlite test fixtures and the
# guard's own test data carry SQL literals too (200-run replay, 2026-09-29).
_DB_CLIENT = re.compile(r"""psycopg|asyncpg|\bnew\s+(?:pg\.)?(?:Pool|Client)\s*\("""
                        r"""|require\(\s*['"](?:pg|postgres)['"]\s*\)|from\s+['"](?:pg|postgres)['"]"""
                        r"""|\bpostgres\s*\(\s*(?:process\.env|['"`]postgres)""", re.I)
_SQLITE = re.compile(r"""\bsqlite3?\b|better-sqlite3|\bduckdb\b""", re.I)
_CONN_HOST = re.compile(r"""postgres(?:ql)?://(?:[^@/\s'"`]*@)?(\[[^\]]*\]|[^:/?\s'"`]+)""", re.I)
# Every literal of any length, left to right. A length floor let a short
# literal ('pg') fail to match, and its closing quote then paired with the
# SQL's opening one (QA round 2, 2026-09-29). An unclosed ' or " stops at the
# end of its line, so a stray apostrophe in a comment cannot swallow code.
_SQL_LITERAL = re.compile(
    r"'''([\s\S]*?)'''"
    r'|"""([\s\S]*?)"""'
    r"|`((?:[^`\\]|\\.)*)`"
    r"|'((?:[^'\\\n]|\\.)*)'"
    r'|"((?:[^"\\\n]|\\.)*)"')
_SQL_HEAD = re.compile(r"\s*(?:WITH|INSERT|UPDATE|DELETE|MERGE|UPSERT|ALTER|DROP|TRUNCATE|CREATE"
                       r"|GRANT|REVOKE)\b", re.I)


def _code_sql_write(code, env=None):
    """A write statement the code sends through a database client (pg,
    postgres.js, psycopg), unless every connection string in the code and
    its env is on this machine (the local scratch DB the rigs use)."""
    if not _DB_CLIENT.search(code) or _SQLITE.search(code):
        return None
    hosts = _CONN_HOST.findall(code)
    for v in (env or {}).values():
        hosts += _CONN_HOST.findall(str(v))
    if hosts and all(h.strip("[]").lower() in _LOCAL_HOSTS or h.startswith("127.") for h in hosts):
        return None
    for m in _SQL_LITERAL.finditer(code):
        text = next((x for x in m.groups() if x), "")
        if _SQL_HEAD.match(text):
            verb = sql_write(text)
            if verb:
                return f"SQL {verb}"
    return None


def _http_method(code, args):
    """The write method this code sends, or None: a literal one, else, when
    the method is a variable, the one the script was run with (`adm.mjs
    PATCH /x`), a write method named anywhere in the code, or, with neither,
    "(method from a variable)". A run with GET/HEAD and no write word is a read."""
    m = _HTTP_WRITE.search(code)
    if m:
        return next(x for x in m.groups() if x).upper()
    if not _HTTP_CALL.search(code):
        return None
    m = _CLIENT_WRITE.search(code)
    if m:
        return m.group(1).upper()
    if not _method_is_variable(code):
        return None
    words = [str(a).upper() for a in args or ()]
    hit = next((w for w in words if w in _WRITE_METHODS), None)
    if hit:
        return hit
    if {"GET", "HEAD", "OPTIONS"} & set(words):
        return None
    lit = _WRITE_METHOD_LITERAL.search(code)
    return lit.group(1).upper() if lit else "(method from a variable)"


def _code_write(code, python=False, env=None, args=()):
    m = (_SBPY_WRITE if python else _SBJS_WRITE).search(code)
    if m:
        return f"supabase-{'py' if python else 'js'} {m.group(2)} {m.group(1)}"
    m = _STORAGE_WRITE.search(code)
    if m:
        return f"supabase storage {m.group(1)}"
    for m in _RPC.finditer(code):
        first = re.split(r"_|(?<=[a-z])(?=[A-Z])", m.group(1).split(".")[-1])[0].upper()
        if first in _RPC_WRITE_WORDS:
            return f"supabase rpc {m.group(1)}"
    method = _http_method(code, args)
    if method:
        urls = _URL.findall(code)
        # a URL the run line hands the code (BASE_URL=https://prod node rig.cjs)
        # beats the code's own default (|| 'http://localhost:3000')
        env_urls = [str(v) for k, v in (env or {}).items()
                    if _URL.match(str(v)) and re.search(r"\b" + re.escape(k) + r"\b", code)]
        remote = [u for u in env_urls + urls if not _url_exempt(u)]
        if remote:
            return f"HTTP {method} {_host(remote[0]) or remote[0][:40]}"
        if not urls and not env_urls:
            return f"HTTP {method} (URL built at run time)"
    return _code_sql_write(code, env)


# ---- curl / wget ----------------------------------------------------------
_CURL_SHORT_VALUE = set("AbcCdDeEFHKmoPQrTuUwxXyYz")
_CURL_LONG_VALUE = {"--header", "--output", "--write-out", "--user", "--user-agent", "--referer",
                    "--max-time", "--connect-timeout", "--retry", "--retry-delay",
                    "--retry-max-time", "--cookie", "--cookie-jar", "--config", "--cacert",
                    "--capath", "--cert", "--key", "--resolve", "--proxy", "--range",
                    "--continue-at", "--limit-rate", "--interface", "--connect-to", "--output-dir",
                    "--oauth2-bearer", "--aws-sigv4", "--unix-socket", "--max-filesize",
                    "--speed-limit", "--speed-time", "--time-cond", "--trace", "--trace-ascii",
                    "--stderr", "--dump-header", "--etag-save", "--etag-compare", "--max-redirs",
                    "--proxy-user", "--socks5", "--socks5-hostname", "--dns-servers", "--noproxy",
                    "--local-port", "--keepalive-time", "--pinnedpubkey", "--preproxy",
                    "--proxy-header", "--request-target", "--service-name", "--tls-max",
                    "--variable", "--happy-eyeballs-timeout-ms", "--create-file-mode"}
_CURL_DATA_LONG = {"--data", "--data-raw", "--data-binary", "--data-urlencode", "--data-ascii",
                   "--json", "--form", "--form-string"}


def _curl(args):
    method, data, upload, get, urls, i = None, False, False, False, [], 0
    while i < len(args):
        a = args[i]
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if a == "--":
            urls.extend(args[i + 1:])
            break
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            takes = name in _CURL_LONG_VALUE or name in _CURL_DATA_LONG or name in (
                "--request", "--url", "--upload-file")
            if name == "--request":
                method = val if eq else nxt
            elif name in _CURL_DATA_LONG:
                data = True
            elif name == "--upload-file":
                upload = True
            elif name == "--url":
                urls.append(val if eq else nxt)
            elif name == "--get":
                get = True
            i += 2 if (takes and not eq) else 1
            continue
        if a.startswith("-") and len(a) > 1:
            j, consumed = 1, False
            while j < len(a):
                ch = a[j]
                if ch in _CURL_SHORT_VALUE:
                    val = a[j + 1:] or nxt
                    consumed = not a[j + 1:]
                    if ch == "X":
                        method = val
                    elif ch in "dF":
                        data = True
                    elif ch == "T":
                        upload = True
                    break
                if ch == "G":
                    get = True
                j += 1
            i += 2 if consumed else 1
            continue
        # a URL, host:port or $VAR, not the bare value of an unlisted flag ("5")
        if "://" in a or "." in a or ":" in a or "$" in a or a.startswith("localhost"):
            urls.append(a)
        i += 1
    if method:
        m = method.upper()
        if m in ("GET", "HEAD", "OPTIONS"):
            return None
    elif upload:
        m = "PUT"
    elif data and not get:
        m = "POST"
    else:
        return None
    remote = [u for u in urls if not _url_exempt(u)]
    if urls and not remote:
        return None
    return f"curl {m} " + (_host(remote[0]) or remote[0][:40] if remote else "(no URL)")


def _wget(args):
    if not any(a.startswith(("--post-data", "--post-file", "--body-data", "--body-file"))
               or re.match(r"--method=(POST|PUT|PATCH|DELETE)", a, re.I) for a in args):
        return None
    urls = _nonflags(args)
    remote = [u for u in urls if not _url_exempt(u)]
    if urls and not remote:
        return None
    return "wget write " + (_host(remote[0]) if remote else "(no URL)")


def _executed_script(words):
    """The file a command runs as a shell script: `bash f.sh`, `source f`,
    `. f`, or a path run directly (`./gw.sh`, `/tmp/x/gw.sh PATCH ...`)."""
    prog = os.path.basename(words[0])
    args = words[1:]
    if prog in _SHELLS:
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                return None  # `bash -c text`: _nested reads the text
            if a in ("-o", "+o", "-O", "+O"):
                i += 2
            elif a.startswith(("-", "+")):
                i += 1
            else:
                return a
        return None
    if words[0] in ("source", "."):
        return args[0] if args else None
    return words[0] if "/" in words[0] else None


_PKG_DEPLOY_WORDS = {"deploy", "publish", "release", "ship"}
_POSITIONAL = re.compile(r"\$\{([1-9])(?::?-([^}]*))?\}|\$([1-9])")
_LITERAL_ASSIGN = re.compile(
    r"""(?:^|[;\s])(?:local\s+|export\s+|readonly\s+)?([A-Za-z_]\w*)="""
    r"""(?:"([^"$`\\]*)"|'([^']*)'|([^\s;"'$`\\]*))(?=[;\s]|$)""", re.M)


def _bind_args(body, args):
    """The script as it ran with these arguments: $1..$9 (and ${3:-x}) become
    the command's own words, then a variable assigned one literal value
    becomes that value, so `sbapi.sh GET /x` with `M="$1" ... -X "$M"` reads
    as the GET it was, and `gw.sh POST /admin/...` as the POST."""
    def dq(v):
        return v.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")

    def pos(m):
        k = int(m.group(1) or m.group(3))
        if k <= len(args):
            return dq(args[k - 1])
        return dq(m.group(2) or "")

    body = _POSITIONAL.sub(pos, body)
    values = {}
    for m in _LITERAL_ASSIGN.finditer(body):
        values.setdefault(m.group(1), set()).add(next((x for x in m.groups()[1:] if x is not None), ""))
    for name, vals in values.items():
        if len(vals) == 1:
            v = dq(next(iter(vals)))
            body = re.sub(r"\$\{" + name + r"\}|\$" + name + r"\b", lambda _m, v=v: v, body)
    return body


def _argv_write(words, bodies, written, with_db, g=None, depth=0, env=None):
    """(label, text) when this one command writes to a live system, else None."""
    prog = os.path.basename(words[0])
    args = words[1:]
    seg = " ".join(words)
    label = None
    # A script the worker wrote and then ran (`/tmp/rail2otp/gw.sh PATCH
    # /admin/...`): its body is what writes (QA 2026-09-29: four admin-API
    # writes in bg-1790164291634 were invisible without this).
    script = _executed_script(words)
    if script is not None and depth < 3:
        body = _script_body(script, written)
        if body:
            shebang = body.lstrip()[:200].split("\n", 1)[0]
            run_args = args if prog not in _SHELLS and words[0] not in ("source", ".") \
                else args[args.index(script) + 1:] if script in args else []
            if shebang.startswith("#!") and re.search(r"python|node|deno|bun", shebang):
                what = _code_write(body, python="python" in shebang, env=env, args=run_args)
                found = [what] if what else []
            else:
                found = [h[0] for h in _bash_hits(_bind_args(body, run_args), written, g, depth + 1)]
            if found:
                what = "; ".join(dict.fromkeys(found))
                return f"{what} (in {script})", f"[{what}, in {script}] {seg}"
    nf_pkg = _nonflags(args)
    if prog in ("npm", "pnpm", "yarn", "bun") and nf_pkg and "--dry-run" not in args:
        name = nf_pkg[1] if nf_pkg[0] == "run" and len(nf_pkg) > 1 else nf_pkg[0]
        if re.split(r"[:_.-]", name)[0] in _PKG_DEPLOY_WORDS:
            return f"{prog} {'run ' if nf_pkg[0] == 'run' else ''}{name}", seg
    if prog == "git":
        label = _git_push(args)
    elif prog == "gh":
        label = _gh(args)
    elif prog == "supabase":
        label = _supabase(args, with_db)
    elif prog == "vercel":
        label = _vercel(args)
    elif prog == "aws":
        label = _aws(args)
    elif prog == "asc":
        label = _asc(args)
    elif prog == "capgo" or words[0].startswith("@capgo/cli"):
        label = _capgo(args)
    elif prog == "node" and args and "@capgo/cli" in args[0]:
        label = _capgo(args[1:])
    elif prog in _DEPLOY_CLIS:
        nf = _nonflags(args)
        if nf and nf[0] in _DEPLOY_CLIS[prog] and not {"-h", "--help"} & set(args):
            label = f"{prog} {nf[0]}"
    elif prog == "docker" and _nonflags(args)[:1] == ["push"]:
        label = "docker push"
    elif prog in ("npm", "pnpm", "yarn") and _nonflags(args)[:1] == ["publish"] and "--dry-run" not in args:
        label = f"{prog} publish"
    elif prog == "stripe" and set(_nonflags(args)) & _STRIPE_WRITES and "--help" not in args:
        label = "stripe " + " ".join(_nonflags(args)[:2])
    elif prog == "curl":
        label = _curl(args)
        if label:
            return label, seg
    elif prog == "wget":
        label = _wget(args)
        if label:
            return label, seg
    elif with_db and prog == "psql":
        if any(a in ("-f", "--file") or a.startswith("--file=") for a in args):
            label = "psql -f"
        else:
            texts = [v for v in (_flag_val(args, "-c", "--command"),) if v] + list(bodies)
            verb = next((v for v in map(sql_write, texts) if v), None)
            label = f"psql {verb}" if verb else None
    if label:
        return label, seg
    if _is_runner(prog):
        nf = _nonflags(args)
        if prog.startswith("python") and any(os.path.basename(a) == "mail_watch.py" for a in args) \
                and any(a == "--send-draft" or a.startswith("--send-draft=") for a in args) \
                and "--dry-run" not in args:
            return "mail_watch --send-draft", seg
        if nf and os.path.basename(nf[0]) == "schedule.mjs" and len(nf) > 1 \
                and nf[1] in ("add", "update", "remove"):
            return f"schedule.mjs {nf[1]}", seg
        if {"--dry-run", "--dryrun"} & set(args):
            return None  # the script's own dry run, like `git push --dry-run`
        for where, code, run_args in _code_of(prog, args, bodies, written):
            what = _code_write(code, python=prog.startswith("python"), env=env, args=run_args)
            if what:
                return f"{where}: {what}", f"[{where}: {what}] {seg}"
    return None


def _record_files(words, bodies, outs, written):
    """Remember what a heredoc wrote, so a later `node that-file` is read."""
    if not bodies:
        return
    prog = os.path.basename(words[0])
    targets = list(outs) if prog == "cat" else _nonflags(words[1:]) if prog == "tee" else []
    for t in targets:
        written[_norm_path(t)] = bodies[-1]


def _scan_bash(command, written, g, with_db, depth=0):
    hits, shell_env = [], {}
    for words, bodies, outs, env in _segments(command, g, depth):
        # `export BASE_URL=https://prod; node rig.cjs` and a bare `X=v;` statement
        # hold for the commands after them in this call
        if not words or words[0] == "export":
            for w in words[1:]:
                k, eq, v = w.partition("=")
                if eq and re.fullmatch(r"[A-Za-z_]\w*", k):
                    shell_env[k] = v
            shell_env.update(env)
            continue
        hit = _argv_write(words, bodies, written, with_db, g, depth, {**shell_env, **env})
        if hit and hit not in hits:
            hits.append(hit)
        _record_files(words, bodies, outs, written)
    return hits


def _bash_hits(command, written, g, depth=0):
    """Every (label, text) live-system write a shell command makes: the rules
    above per simple command, then the guard's database classifier."""
    if not isinstance(command, str) or not command.strip():
        return []
    guard_hit, db_checked = None, False
    if g is not None:
        try:
            reason = g.bash_write_reason(command)
            db_checked = True
            if reason:
                guard_hit = (reason, f"[{reason}] {command}")
        except Exception:
            db_checked = False
    try:
        hits = _scan_bash(command, written, g, not db_checked, depth)
    except Exception:
        hits = _scan_bash(command, written, None, True, depth)
    return hits + ([guard_hit] if guard_hit else [])


# A worker's own test file (tests/x.py, test_x.py, x.test.ts ...) run again
# and again: its fixtures carry write shapes. The verifier measured one worker
# at 74 such rows burying its real ones, so they are tagged and sorted last,
# never dropped.
_TEST_SCRIPT = re.compile(r"(?:^|[\s/])(?:tests?|__tests__)/|(?:^|[\s/])test_[\w.-]+\.py\b"
                          r"|[\w-]+\.(?:test|spec)\.(?:[cm]?[jt]sx?|py)\b|[\w-]+_test\.py\b")


def classify_bash(command, written):
    """(labels, text, test_only) for the live-system writes one shell command
    makes, or None. One row per tool call, every write in it named: `git push
    origin dev ; supabase functions deploy demo-chat ...`. test_only is True
    when every write in it comes from a test file's code."""
    hits = _bash_hits(command, written, write_guard())
    if not hits:
        return None
    return ("; ".join(h[0] for h in hits), " ; ".join(dict.fromkeys(h[1] for h in hits)),
            all(_TEST_SCRIPT.search(h[0]) for h in hits))


# ---- MCP tools ------------------------------------------------------------
_MCP_SKIP_SERVERS = {"playwright", "claude_ai_Claude_Docs", "context7"}
_MCP_WRITE_WORDS = {"send", "create", "update", "delete", "deploy", "publish", "merge", "push",
                    "apply", "remove", "upload", "post", "put", "patch", "set", "write", "insert",
                    "cancel", "pause", "restore", "reset", "rebase", "fork", "add", "execute",
                    "run", "trigger", "archive", "move", "modify", "edit", "submit", "schedule",
                    "book", "refund", "charge", "reply", "forward", "trash"}
_GHL_READS = {"get", "search", "lookup", "list", "export", "find", "describe", "count", "check",
              "fetch", "read", "retrieve", "query", "verify", "validate", "preview"}


def _mcp_detail(inp, text_key=None):
    bits = []
    for k, v in inp.items():
        if k == text_key:
            continue
        key = "project" if k == "project_id" else k
        if isinstance(v, (str, int, float, bool)) and str(v).strip():
            if isinstance(v, str) and len(v) > 80:
                continue  # a body or a file; the statement carries what matters
            bits.append(f"{key}={v}")
        elif isinstance(v, list):
            bits.append(f"{key}=[{len(v)} item(s)]")
    if text_key and isinstance(inp.get(text_key), str):
        bits.append(inp[text_key])
    return "  ".join(bits)


def classify_call(name, inp, written):
    """(tool label, detail[, test file only]) when this tool call writes to a
    live system."""
    if name == "Bash":
        hit = classify_bash(inp.get("command"), written)
        return ("Bash", hit[1], hit[2]) if hit else None
    if not name.startswith("mcp__"):
        return None
    parts = name.split("__", 2)
    server, tool = (parts[1], parts[2]) if len(parts) == 3 else ("", name)
    if server == "supabase" and tool == "execute_sql":
        return ("execute_sql", _mcp_detail(inp, "query")) if sql_write(inp.get("query")) else None
    if server == "leadconnector" and tool == "execute_operation":
        method = str(inp.get("method") or "").upper()
        op = str(inp.get("operationId") or inp.get("operation_id") or inp.get("operation") or "")
        if method:
            is_write = method not in ("GET", "HEAD", "OPTIONS")
        else:
            words = re.split(r"[-_./\s]+|(?<=[a-z])(?=[A-Z])", op.strip())
            is_write = (words[0].lower() if op.strip() else "") not in _GHL_READS
        if not is_write:
            return None
        params = inp.get("params")
        return "ghl", (f"op={op or '?'}  location={inp.get('locationId') or '?'}"
                       + (f"  reason={inp['reason']}" if inp.get("reason") else "")
                       + (f"  params={json.dumps(params, separators=(',', ':'))}" if params else ""))
    if server in _MCP_SKIP_SERVERS:
        return None
    if re.split(r"[_-]", tool)[0].lower() not in _MCP_WRITE_WORDS:
        return None
    label = tool if server == "supabase" else f"{server}.{tool}"
    return label, _mcp_detail(inp, "query" if "query" in inp else None)


# ---- secrets --------------------------------------------------------------
_VAL = r"""(?:'[^']*'|"[^"]*"|[^\s'"&;,]+)"""
_REDACTIONS = [
    (re.compile(r"sbp_[A-Za-z0-9]{6,}"), "sbp_[REDACTED]"),
    (re.compile(r"sb_secret_[A-Za-z0-9_\-]{4,}"), "sb_secret_[REDACTED]"),
    (re.compile(r"\b(sk|rk)_(live|test)_[A-Za-z0-9]{6,}"), r"\1_\2_[REDACTED]"),
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_\-]{6,}"), "sk-[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}(?:\.[A-Za-z0-9_\-]*){0,2}"), "[REDACTED_JWT]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}"), "[REDACTED_TG_TOKEN]"),
    # not `demo-gptlive-token --project-ref ...`: the word must stand alone
    # a credential carries a digit or is a $VAR; "Basic Monthly" is a plan name
    (re.compile(r"(?i)(?<![\w-])(Bearer|Basic|Token)\s+(?!\[REDACTED)(?=[A-Za-z0-9._~+/=\-${}]*[\d$])"
                r"[A-Za-z0-9._~+/=\-${}]{6,}"), r"\1 [REDACTED]"),
    (re.compile(r"\bpit-[0-9a-fA-F-]{20,}"), "pit-[REDACTED]"),
    # the key may be JSON-quoted: {"twilio_auth_token":"..."} (QA round 2)
    (re.compile(r"""(?i)(TELEGRAM_BOT_TOKEN["']?\s*[=:]\s*)""" + _VAL), r"\1[REDACTED]"),
    (re.compile(r"""(?i)(password["']?\s*[=:]\s*)""" + _VAL), r"\1[REDACTED]"),
    # any name ENDING in a secret word: twilio_auth_token = '...', ghl_api_key: ...
    (re.compile(r"(?i)(\b\w*(?:api[_-]?key|apikey|secret|token|service[_-]?role(?:[_-]?key)?|"
                r"""private[_-]?key|secret[_-]?access[_-]?key|passwd|pwd)["']?\s*[=:]\s*)""" + _VAL),
     r"\1[REDACTED]"),
    # `aws ssm put-parameter --value`, `secretsmanager --secret-string` (verifier)
    (re.compile(r"(?i)(--(?:token|password|api-key|apikey|secret|auth-token|value|secret-string)"
                r"(?:\s+|=))" + _VAL), r"\1[REDACTED]"),
    (re.compile(r"(?i)(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+@"), r"\1[REDACTED]@"),
    # user:password@ in any URL (https://AC...:<auth token>@api.twilio.com)
    (re.compile(r"""(?i)(\b[a-z][a-z0-9+.-]*://[^:/@\s'"]+:)[^@\s/'"]+@"""), r"\1[REDACTED]@"),
    (re.compile(r"((?:^|\s)(?:-u|--user)(?:\s+|=)[^\s:'\"]+):[^\s'\"]+"), r"\1:[REDACTED]"),
    (re.compile(r"(?i)(vault\.create_secret\(\s*)(?:'(?:[^']|'')*'|\$(\w*)\$[\s\S]*?\$\2\$)"),
     r"\1'[REDACTED]'"),
    (re.compile(r"(?i)(vault\.update_secret\(\s*[^,()]+,\s*)'(?:[^']|'')*'"), r"\1'[REDACTED]'"),
]
# A statement that names a secret column far from its value (INSERT INTO t
# (tenant_id, twilio_auth_token) VALUES (...)): its token-shaped SQL literals
# go, 16+ characters with a digit. The row's identity stays readable (QA
# round 3): a UUID, a "quoted"."table" (double quotes are identifiers), and a
# literal compared to a non-secret column (location_id = 've9EPM428h8v...').
_SECRET_NAME = re.compile(r"(?i)\b\w*(?:api[_-]?key|apikey|secret|token|password|passwd|pwd|"
                          r"service[_-]?role(?:[_-]?key)?|private[_-]?key)\b")
_TOKEN_LITERAL = re.compile(
    r"'(?![0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')"
    r"(?=[A-Za-z0-9_\-+/=]*\d)[A-Za-z0-9_\-+/=]{16,}'")
_COMPARED_TO = re.compile(r"""(\w+)["']?\s*(?:=|:)\s*$""")


def _token_literal(m):
    k = _COMPARED_TO.search(m.string[max(0, m.start() - 80):m.start()])
    if k and not _SECRET_NAME.fullmatch(k.group(1)):
        return m.group(0)
    return "'[REDACTED]'"


def redact(text):
    for pat, repl in _REDACTIONS:
        text = pat.sub(repl, text)
    if _SECRET_NAME.search(text):
        text = _TOKEN_LITERAL.sub(_token_literal, text)
    return text


def one_line(text, limit=160):
    s = " ".join(redact(str(text)).split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


# ---- transcripts ----------------------------------------------------------
_KNOWN_TYPES = {"system", "assistant", "user", "result", "rate_limit_event", "stream_event",
                "tool_progress", "summary", "attachment", "thread.started", "turn.started",
                "turn.completed", "item.started", "item.updated", "item.completed"}
# `{"error": null, "data": ...}` is a SUCCESS envelope: only a non-empty error
# fails. So is the harness's "Error: result (N characters ...) exceeds maximum
# allowed tokens": the call ran, only its output was too long to show.
_FAIL_HEAD = re.compile(
    r'\A\s*(?:\{\s*"error"\s*:\s*(?!null\b|false\b|""|\[\s*\]|\{\s*\})'
    r'|error\b(?!:\s*result\s*\([\d,]+\s*characters)|fatal:|failed\b)', re.I)
_FAIL_ANY = re.compile(r"Failed to run sql query|! \[(?:remote )?rejected\]|error: failed to push",
                       re.I)


def _result_text(res):
    c = res.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(str(b.get("text") or "") for b in c if isinstance(b, dict))
    return ""


def _outcome(res):
    if res is None:
        return "unknown"
    item = res.get("codex_item")
    if item is not None:
        status = str(item.get("status") or "").lower()
        code = item.get("exit_code")
        if status in ("failed", "declined", "error") or item.get("error") or (
                isinstance(code, int) and code != 0):
            return "error"
        return "ok"
    if res.get("is_error"):
        return "error"
    text = _result_text(res)
    return "error" if _FAIL_HEAD.search(text) or _FAIL_ANY.search(text[:20000]) else "ok"


def _epoch(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _apply_edit(inp, written):
    """Keep the transcript's copy of a script current through Edit/MultiEdit."""
    fp = inp.get("file_path")
    if not isinstance(fp, str) or _norm_path(fp) not in written:
        return
    key = _norm_path(fp)
    edits = inp.get("edits") if isinstance(inp.get("edits"), list) else [inp]
    for e in edits:
        if not isinstance(e, dict):
            continue
        old, new = e.get("old_string"), e.get("new_string")
        if isinstance(old, str) and isinstance(new, str) and old:
            written[key] = written[key].replace(old, new, -1 if e.get("replace_all") else 1)


def scan_transcripts(paths):
    """Every write class tool call in these transcripts, paired with its result.
    Claude stream JSON and Claude Code transcripts (tool_use / tool_result
    blocks) and Codex exec logs (command_execution / mcp_tool_call items)."""
    calls, order, results, recognised = {}, [], {}, False
    for path in paths:
        try:
            f = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for n, line in enumerate(f):
                hot = "tool_use" in line or "tool_result" in line or '"item.' in line
                if not hot and (recognised or n > 40):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                kind = rec.get("type")
                if kind in _KNOWN_TYPES:
                    recognised = True
                msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
                content = msg.get("content")
                if kind == "assistant" and isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            cid = b.get("id")
                            if not isinstance(cid, str) or not cid:
                                cid = f"{path}:{n}:{len(order)}"
                            if cid not in calls:
                                calls[cid] = {"name": str(b.get("name") or ""),
                                              "input": b.get("input"), "ts": rec.get("timestamp")}
                                order.append(cid)
                elif kind == "user" and isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result" \
                                and isinstance(b.get("tool_use_id"), str):
                            results[b["tool_use_id"]] = b
                elif isinstance(kind, str) and kind.startswith("item.") and isinstance(rec.get("item"), dict):
                    item = rec["item"]
                    if item.get("type") not in ("command_execution", "mcp_tool_call"):
                        continue
                    cid = f"{path}#{item.get('id')}"
                    if cid not in calls:
                        if item["type"] == "command_execution":
                            name, inp = "Bash", {"command": item.get("command")}
                        else:
                            name = f"mcp__{item.get('server')}__{item.get('tool')}"
                            inp = item.get("arguments")
                            if isinstance(inp, str):
                                try:
                                    inp = json.loads(inp)
                                except ValueError:
                                    inp = {}
                        calls[cid] = {"name": name, "input": inp, "ts": None}
                        order.append(cid)
                    if kind == "item.completed":
                        results[cid] = {"codex_item": item}
    written, writes, failures = {}, [], 0
    for seq, cid in enumerate(order):
        c = calls[cid]
        inp = c["input"] if isinstance(c["input"], dict) else {}
        if c["name"] == "Write":
            fp, body = inp.get("file_path"), inp.get("content")
            if isinstance(fp, str) and isinstance(body, str):
                written[_norm_path(fp)] = body
            continue
        if c["name"] in ("Edit", "MultiEdit"):
            _apply_edit(inp, written)
            continue
        try:
            hit = classify_call(c["name"], inp, written)
        except Exception:
            failures += 1
            continue
        if hit:
            test = len(hit) > 2 and bool(hit[2])
            writes.append({"id": cid, "seq": seq, "tool": hit[0], "test": test,
                           "detail": one_line(("(test file) " if test else "") + hit[1]),
                           "outcome": _outcome(results.get(cid)), "epoch": _epoch(c["ts"])})
    return {"writes": writes, "scanned": len(order), "recognised": recognised or bool(order),
            "unclassified": failures}


def _session_id(log):
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f):
                if n > 50:
                    break
                m = re.search(r'"session_id"\s*:\s*"([0-9a-fA-F-]{36})"', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def subagent_transcripts(session_id):
    """The subagent and workflow-agent transcripts of one worker session."""
    if not session_id or not PROJECTS.is_dir():
        return []
    out = []
    for d in PROJECTS.glob(f"*/{session_id}/subagents"):
        out.extend(sorted(p for p in d.rglob("*.jsonl") if p.is_file()))
    return out


_WRITES_CACHE = {}


def worker_writes(log):
    """PRODUCTION WRITES scan of one worker: its run log plus its subagents'
    transcripts. None when there is no run log to read."""
    if not log or not Path(log).is_file():
        return None
    key = str(log)
    if key not in _WRITES_CACHE:
        try:
            subs = subagent_transcripts(_session_id(log))
            scan = scan_transcripts([Path(log)] + subs)
            scan.update(log=Path(log), subagent_files=len(subs))
        except Exception as e:  # one bad log must not take the whole salvage run down
            scan = {"failed": f"{type(e).__name__}: {e}"[:160], "log": Path(log), "writes": []}
        _WRITES_CACHE[key] = scan
    return _WRITES_CACHE[key]


_OUTCOME_LABEL = {"unknown": "UNKNOWN", "ok": "ok", "error": "error"}


def format_writes(scan, partial=False):
    """The PRODUCTION WRITES block as lines: header flush left, rows indented 2."""
    tag = " (PARTIAL VIEW, worker STILL RUNNING)" if partial else ""
    if scan is None:
        return [f"PRODUCTION WRITES{tag}: NOT CHECKED, no run log to read -- check the live "
                "systems by hand before saying nothing reached production"]
    if scan.get("failed"):
        return [f"PRODUCTION WRITES{tag}: NOT CHECKED, the scan failed ({scan['failed']}) -- read "
                f"{scan.get('log', 'the run log')} by hand before saying nothing reached production"]
    if not scan["recognised"]:
        return [f"PRODUCTION WRITES{tag}: NOT CHECKED, run log format not recognised "
                f"({scan.get('log', '?')}) -- read it by hand before saying nothing reached production"]
    n, m = len(scan["writes"]), scan["scanned"]
    subs = scan.get("subagent_files") or 0
    extra = f", incl. {subs} subagent transcript(s)" if subs else ""
    notes = []
    if write_guard() is None:
        notes.append(f"  (write-guard classifiers not loaded: {_GUARD_STATE.get('err', '?')}; "
                     "regex fallback used, which over-flags)")
    if scan.get("unclassified"):
        notes.append(f"  ({scan['unclassified']} tool call(s) could not be classified; "
                     "read them in the transcript)")
    if not n:
        return [f"PRODUCTION WRITES{tag}: none seen (0 of {m} tool calls scanned{extra})"] + notes
    out = [f"PRODUCTION WRITES{tag} ({n} of {m} tool calls scanned{extra}):"] + notes
    unknown = sum(1 for w in scan["writes"] if w["outcome"] == "unknown")
    if unknown and partial:
        out.append(f"  (!! {unknown} call(s) have NO result yet: on a live worker that is the "
                   "call it is inside right now)")
    elif unknown:
        out.append(f"  !! {unknown} write(s) have NO result: the worker died inside the call, "
                   "so it may or may not have landed. Check these FIRST.")
    rows = sorted(scan["writes"], key=lambda w: (w["outcome"] != "unknown", bool(w.get("test")),
                                                 -(w["epoch"] or 0), -w["seq"]))
    tests = sum(1 for w in rows if w.get("test"))
    if tests:
        out.append(f"  ({tests} row(s) come from the worker's own test files; they are listed last)")
    for w in rows:
        when = (datetime.fromtimestamp(w["epoch"]).strftime("%H:%M:%S")
                if w["epoch"] is not None else "--:--:--")
        out.append(f"  {_OUTCOME_LABEL[w['outcome']]:<8} {when}  {w['tool']:<11}  {w['detail']}")
    if any(w["outcome"] == "error" and w["tool"] == "Bash" for w in rows):
        out.append("  (an error on a multi-step Bash command does not prove its write step failed)")
    out.append("  -> Read the live row, audit log or git state before saying nothing reached production.")
    return out


def resolve_run_log(ident, workers):
    """A run log from a path, a runId, a worker key or a lane, any age."""
    p = Path(os.path.expanduser(ident))
    if p.is_file():
        return p
    for cand in (RUNS / f"{ident}.jsonl", RUNS / f"{ident}.log", RUNS / ident):
        if cand.is_file():
            return cand
    # exact key, then exact lane (workers are newest first), then a substring
    # only when it carries a run's 13-digit timestamp: `bg` never lands on bg18
    for test in (lambda w: ident == w["key"], lambda w: ident == w["lane"],
                 lambda w: re.search(r"\d{13}", ident) and ident in w["key"]):
        for w in workers:
            if w.get("log") and test(w):
                return Path(w["log"])
    if RUNS.is_dir() and ident:
        hits = [q for q in RUNS.glob("*.jsonl") if q.stem.startswith(ident + "-")]
        if hits:
            return max(hits, key=lambda q: q.stat().st_mtime)
    return None


def _live_log(log, workers):
    return any(w["alive"] and w.get("log") and str(w["log"]) == str(log) for w in workers)


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
    ap.add_argument("--writes", metavar="RUN_ID", help="print one run's PRODUCTION WRITES (any age; "
                    "runId, worker key, lane or run log path)")
    args = ap.parse_args()
    cutoff = time.time() - args.since * 60

    runs = find_workflow_runs(cutoff)
    workers = load_workers(cutoff)

    if args.writes:
        log = resolve_run_log(args.writes, workers)
        if not log:
            print(f"no run log for '{args.writes}'", file=sys.stderr)
            return 1
        print(f"=== PRODUCTION WRITES: {log} ===")
        for line in format_writes(worker_writes(log), partial=_live_log(log, workers)):
            print(line)
        return 0

    if args.dump:
        for r in runs:
            if args.dump in r["run_id"]:
                data = json.loads(r["path"].read_text())
                out = Path(f"/tmp/salvage-{r['run_id']}.json")
                out.write_text(json.dumps(data.get("result"), indent=1))
                print(f"wrote {out} ({out.stat().st_size} bytes)")
                # The workflow's agents can write to production as well.
                agents = PROJECTS / r["project"] / r["session"] / "subagents" / "workflows" / r["run_id"]
                files = sorted(agents.glob("*.jsonl")) if agents.is_dir() else []
                scan = scan_transcripts(files) if files else None
                if scan is not None:
                    scan["log"] = agents
                for line in format_writes(scan):
                    print(line)
                return 0
        log = resolve_run_log(args.dump, workers)
        if log:
            # A worker runId, not a workflow: show what it wrote to production.
            print(f"no workflow run '{args.dump}'; {log.name} is a worker run log "
                  "(its report: --report). Its production writes:")
            for line in format_writes(worker_writes(log), partial=_live_log(log, workers)):
                print(line)
            return 0
        print(f"run {args.dump} not found in the last {args.since}m", file=sys.stderr)
        return 1

    if args.report:
        for w in workers:
            if args.report in w["key"] or args.report == w["lane"]:
                t = transcript_findings(w)
                d = draft_findings(w)
                if d and final_report_missing(t) and w.get("alive"):
                    # A LIVE worker has not ended: its draft is work in
                    # progress, never "ended without a final report" (QA
                    # 2026-09-27; the 09-25 learned mistake was a live
                    # worker read as dead and a second one sent onto its job).
                    text, when, chars = draft_report_text(d, live=True)
                    out = Path(f"/tmp/salvage-report-{w['key']}.md")
                    out.write_text(text)
                    print(f"wrote {out} (DRAFT so far, {chars} chars, last written {when}; "
                          "the worker is STILL RUNNING, do not relaunch it)")
                    for line in format_writes(worker_writes(w.get("log")), partial=True):
                        print(line)
                    return 0
                if d and final_report_missing(t):
                    text, when, chars = draft_report_text(d)
                    out = Path(f"/tmp/salvage-report-{w['key']}.md")
                    out.write_text(text)
                    print(f"wrote {out} (DRAFT report, {chars} chars, last written {when}; "
                          "the worker ended without a final report)")
                    for line in format_writes(worker_writes(w.get("log"))):
                        print(line)
                    return 0
                if not t:
                    continue
                out = Path(f"/tmp/salvage-report-{w['key']}.md")
                out.write_text(t["full"])
                print(f"wrote {out} ({len(t['full'])} chars, {t['turns']} assistant turns in the log)")
                for line in format_writes(worker_writes(w.get("log")), partial=bool(w.get("alive"))):
                    print(line)
                return 0
        print(f"no transcript for '{args.report}' in the last {args.since}m", file=sys.stderr)
        return 1

    print(f"=== BG SALVAGE — last {args.since} min ===\n")

    found_any = False
    writers = []  # (worker, scan) for every dead worker that wrote to a live system

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

        if w["alive"]:
            # A live worker is not salvage: its log can carry a rate_limit_event
            # it rode out, and a short last turn is just the step it is on.
            print("    STILL RUNNING: this worker is alive, do NOT relaunch or dispatch a second "
                  "writer onto its target; wait for its report (bg.mjs ps shows it)")
            for line in format_writes(worker_writes(w.get("log")), partial=True):
                print("    " + line)
            continue

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

        d = draft_findings(w)
        if d and final_report_missing(t):
            found_any = True
            print(f"    SOURCE 3 DRAFT REPORT  {d['path']}  {d['size']}B  "
                  f"(last written {human_age(d['mtime'])})")
            print("      <-- SALVAGEABLE: the worker ended without a final report; "
                  "this is the last draft it wrote")
            print(f"      recover with: python3 ~/.claude/scripts/bg-salvage.py --report {w['key']}")
        elif d:
            print(f"    SOURCE 3 DRAFT REPORT  {d['path']}  (superseded by the final report above)")

        scan = worker_writes(w.get("log"))
        for line in format_writes(scan):
            print("    " + line)
        if scan and scan.get("writes"):
            # A write that landed is finished work: a from-scratch relaunch
            # would run it again.
            found_any = True
            writers.append((w, scan))

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
    live = [w for w in workers if w["alive"]]
    if live:
        print("STILL RUNNING, do NOT relaunch (wait for their reports):")
        for w in live:
            print(f"  [{w['key']}]  pid={w['pid']}")
    if writers:
        print("PRODUCTION WRITES already made by these workers: do NOT say nothing reached "
              "production, and do not relaunch a step that already landed. Read the live row, "
              "audit log or git state first:")
        for w, scan in writers:
            outcomes = [x["outcome"] for x in scan["writes"]]
            print(f"  [{w['key']}]  {len(outcomes)} write(s): {outcomes.count('unknown')} UNKNOWN, "
                  f"{outcomes.count('ok')} ok, {outcomes.count('error')} error   "
                  f"(python3 ~/.claude/scripts/bg-salvage.py --writes {run_id_of(w)})")
    if found_any:
        print("WORK SURVIVED. Do NOT re-run from scratch — read the sources above first:")
        for r in salvageable_runs:
            print(f"  python3 ~/.claude/scripts/bg-salvage.py --dump {r['run_id']}")
        for w in workers:
            if w["alive"]:
                continue
            t = transcript_findings(w)
            if t or salvageable_draft(w, t):
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
