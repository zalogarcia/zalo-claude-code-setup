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

# The script next to this suite, so a worktree tests its own copy, not the live one.
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bg-salvage.py")
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

    @property
    def run_id(self):
        """The bridge names a worker's files after its run log's basename."""
        return os.path.basename(self.log_path)[: -len(".jsonl")]

    def make_draft(self, text, run_id=None, age_s=None):
        """bg-reports/<runId>.draft.md, the file BG_REPORT_DRAFT points at."""
        reports = os.path.join(self.bridge, "bg-reports")
        os.makedirs(reports, exist_ok=True)
        p = os.path.join(reports, f"{run_id or self.run_id}.draft.md")
        with open(p, "w") as f:
            f.write(text)
        if age_s is not None:
            t = time.time() - age_s
            os.utime(p, (t, t))
        return p

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


# --------------------------------------------------------------------------
# 13. PRODUCTION WRITES (2026-09-29): the Maya v10 worker (bg10) wrote the new
# prompt to the Delta production database with an execute_sql UPDATE, then
# died on a usage limit. The salvage listing said nothing about the write, so
# M relaunched it saying nothing had reached production, and told Zalo so.
# --------------------------------------------------------------------------
SID = "96d09d99-14a5-4e7d-9648-f8a56f5e5a41"
PROD = "prodrefabcdefghijklm"


def use(tid, name, inp, ts="2026-09-29T17:57:50.271Z"):
    return {"type": "assistant", "timestamp": ts, "session_id": SID,
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def result(tid, text="done", is_error=False):
    return {"type": "user", "session_id": SID,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                     "content": text, "is_error": is_error}]}}


def sql(tid, query, ts="2026-09-29T17:57:50.271Z"):
    return use(tid, "mcp__supabase__execute_sql", {"project_id": PROD, "query": query}, ts)


def bash(tid, command, ts="2026-09-29T17:40:00.000Z"):
    return use(tid, "Bash", {"command": command, "description": "x"}, ts)


def section(out):
    """The PRODUCTION WRITES block of the (first) worker in a listing."""
    if "PRODUCTION WRITES" not in out:
        return ""
    body = out.split("PRODUCTION WRITES", 1)[1]
    lines = ["PRODUCTION WRITES" + body.splitlines()[0]]
    for line in body.splitlines()[1:]:
        if not line.startswith("      "):
            break
        lines.append(line.strip())
    return "\n".join(lines)


def writes_of(*records, **kw):
    L = Layout(brief="# TASK\nShip the Maya prompt.", log_text="Working.",
               extra_records=list(records), **kw)
    rc, out, err = L.run()
    return L, rc, out, err, section(out)


def production_writes():
    # 13a. execute_sql UPDATE that succeeded: flagged ok, with the project.
    L, rc, out, err, s = writes_of(
        sql("t1", "WITH upd AS (UPDATE tenant_agents SET config = jsonb_set(config, '{soul}', "
                  "to_jsonb($o1$new prompt$o1$)) WHERE id = 'a9e10000' RETURNING id) SELECT * FROM upd;"),
        result("t1", '{"result":"[{\\"id\\":\\"a9e10000\\"}]"}'))
    check("13a: a succeeded execute_sql UPDATE is flagged ok with its project",
          "PRODUCTION WRITES (1 of 1 tool calls scanned)" in s
          and any(l.startswith("ok") and "execute_sql" in l and f"project={PROD}" in l
                  and "UPDATE tenant_agents" in l for l in s.splitlines()),
          (s or out[-900:]) + err[-300:])

    # 13b. a plain SELECT is not a write.
    L, rc, out, err, s = writes_of(
        sql("t1", "SELECT id, updated_at, created_at FROM tenant_agents WHERE status = 'UPDATE' "
                  "-- DELETE nothing\n FOR UPDATE SKIP LOCKED"),
        result("t1", "[]"))
    check("13b: a SELECT (verbs only in literals, comments, identifiers, FOR UPDATE) is not flagged",
          "PRODUCTION WRITES: none seen (0 of 1 tool calls scanned)" in out, (s or out[-900:]) + err[-300:])

    # 13c. apply_migration that errored.
    L, rc, out, err, s = writes_of(
        use("t1", "mcp__supabase__apply_migration",
            {"project_id": PROD, "name": "add_soul_v10", "query": "ALTER TABLE t ADD COLUMN x int;"}),
        result("t1", "Error: permission denied for table t", is_error=True))
    check("13c: an errored apply_migration is flagged error with its name",
          "(1 of 1 tool calls scanned)" in s
          and any(l.startswith("error") and "apply_migration" in l and "name=add_soul_v10" in l
                  for l in s.splitlines()), (s or out[-900:]) + err[-300:])

    # 13d. git push with NO tool_result (the worker died inside the call):
    # UNKNOWN, and printed before an earlier write that did succeed.
    L, rc, out, err, s = writes_of(
        sql("t1", "UPDATE tenant_agents SET is_active = true WHERE id = 'a';",
            ts="2026-09-29T17:10:00.000Z"),
        result("t1", "[]"),
        bash("t2", "cd ~/dev/delta-agents && git push origin feat/maya-v10",
             ts="2026-09-29T17:20:00.000Z"))
    lines = s.splitlines()
    unk = next((i for i, l in enumerate(lines) if l.startswith("UNKNOWN")), -1)
    ok = next((i for i, l in enumerate(lines) if l.startswith("ok")), -1)
    check("13d: a git push with no result is UNKNOWN and listed before the ok write",
          unk >= 0 and ok >= 0 and unk < ok and "git push origin feat/maya-v10" in lines[unk]
          and "(2 of 2 tool calls scanned)" in s, s or out[-900:])
    check("13d2: an UNKNOWN write gets its own loud warning line",
          "NO result" in s, s)

    # 13e. supabase functions deploy.
    L, rc, out, err, s = writes_of(
        bash("t1", "cd ~/dev/delta-agents && supabase functions deploy demo-chat "
                   "--project-ref abc --no-verify-jwt --use-api"),
        result("t1", "Deployed Functions on project abc: demo-chat"))
    check("13e: supabase functions deploy is flagged",
          any(l.startswith("ok") and "supabase functions deploy demo-chat" in l
              for l in s.splitlines()), s or out[-900:])

    # 13f. curl POST to localhost is not a production write.
    L, rc, out, err, s = writes_of(
        bash("t1", "curl -sS -X POST http://localhost:8787/webhook -d '{\"a\":1}' "
                   "-H 'Content-Type: application/json'; curl -s --json '{}' 127.0.0.1:3000/api"),
        result("t1", "{}"))
    check("13f: curl POST to localhost is not flagged",
          "PRODUCTION WRITES: none seen (0 of 1 tool calls scanned)" in out, s or out[-900:])

    # 13g. curl POST to a remote host is.
    L, rc, out, err, s = writes_of(
        bash("t1", "curl -sS -X POST https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json "
                   "--data-urlencode To=+15550001111"),
        result("t1", "{}"))
    check("13g: curl POST to a remote host is flagged",
          "(1 of 1 tool calls scanned)" in s and "api.twilio.com" in s, s or out[-900:])

    # 13h. secrets in a flagged statement are redacted.
    secrets = ["sbp_0123456789abcdef0123", "sk-ant-api03-SECRETSECRETSECRET",
               "sb_secret_ABCDEFGHIJKLMNOP", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZSJ9.sig",
               "hunter2hunter2"]
    L, rc, out, err, s = writes_of(
        bash("t1", "curl -X PATCH https://x.supabase.co/rest/v1/demos -H 'Authorization: Bearer "
                   "sbp_0123456789abcdef0123' -H 'apikey: sb_secret_ABCDEFGHIJKLMNOP' "
                   "-d 'k=sk-ant-api03-SECRETSECRETSECRET&jwt=eyJhbGciOiJIUzI1NiJ9."
                   "eyJyb2xlIjoic2VydmljZSJ9.sig&password=hunter2hunter2'"),
        result("t1", "{}"))
    check("13h: secrets in a printed statement are redacted",
          "REDACTED" in s and not any(x in out for x in secrets), s or out[-900:])

    # 13i. zero writes: the "none seen" line always carries the denominator.
    L, rc, out, err, s = writes_of(
        use("t1", "Read", {"file_path": "/tmp/x"}), result("t1", "x"),
        bash("t2", "git status && grep -rn 'git push' . && echo 'supabase functions deploy'"),
        result("t2", "clean"))
    check("13i: zero writes prints 'none seen (0 of M' with the scanned count",
          "PRODUCTION WRITES: none seen (0 of 2 tool calls scanned)" in out, s or out[-900:])

    # 13j. statements are truncated to 160 characters, on one line.
    long_q = "UPDATE tenant_agents SET config = config ||\n '{}'::jsonb WHERE id IN (" + \
             ", ".join(f"'{i:04d}'" for i in range(200)) + ");"
    L, rc, out, err, s = writes_of(sql("t1", long_q), result("t1", "[]"))
    row = next((l for l in s.splitlines() if l.startswith("ok")), "")
    stmt = row.split(f"project={PROD}", 1)[-1].strip() if row else ""
    check("13j: each statement is cut to 160 characters on one line",
          bool(row) and len(stmt) <= 160 and "\n" not in stmt and "UPDATE tenant_agents" in stmt,
          row)

    # 13k. a LIVE worker gets the section too, labelled as a partial view.
    L, rc, out, err, s = writes_of(
        sql("t1", "DELETE FROM tenant_messages WHERE id = 'x';"), pid=os.getpid())
    check("13k: a live worker's writes are listed as a PARTIAL VIEW",
          "STILL RUNNING" in out and "PARTIAL VIEW" in s and "execute_sql" in s, s or out[-900:])

    # 13l. the verdict names the dead worker that wrote, and a write alone is
    # never "nothing salvageable" (a relaunch would redo it).
    L = Layout(brief="# TASK\nShip it.", extra_records=[
        sql("t1", "UPDATE tenant_agents SET is_active = false;"), result("t1", "[]")])
    rc, out, _ = L.run()
    verdict = out.split("--- VERDICT ---")[-1]
    check("13l: the verdict lists the writer and never says nothing salvageable",
          "PRODUCTION WRITES" in verdict and NOTHING not in out and "bg9-" in verdict, verdict)

    # 13m. --writes <runId> prints the block for one run log; --report and
    # --dump <worker runId> print it too.
    L = Layout(brief="# TASK\nShip it.", log_text="Done.", extra_records=[
        sql("t1", "INSERT INTO audit_log (a) VALUES (1);"), result("t1", "[]")])
    rc, out, err = L.run("--writes", L.run_id)
    check("13m: --writes <runId> prints the PRODUCTION WRITES block",
          rc == 0 and "(1 of 1 tool calls scanned)" in out and "INSERT INTO audit_log" in out,
          out + err)
    rc, out, err = L.run("--dump", L.run_id)
    check("13m2: --dump <worker runId> prints the PRODUCTION WRITES block",
          rc == 0 and "INSERT INTO audit_log" in out, out + err)
    key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    rc, out, err = L.run("--report", key)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    check("13m3: --report also prints the PRODUCTION WRITES block",
          rc == 0 and "INSERT INTO audit_log" in out, out + err)
    if written and os.path.exists(written):
        os.remove(written)

    # 13n. a subagent's writes count: its transcript lives under the worker's
    # session in the projects dir.
    L = Layout(brief="# TASK\nShip it.", extra_records=[
        use("a1", "Agent", {"prompt": "apply it"}), result("a1", "applied")])
    sub = os.path.join(L.projects, "-Users-zalo-dev", SID, "subagents")
    os.makedirs(sub, exist_ok=True)
    with open(os.path.join(sub, "agent-abc.jsonl"), "w") as f:
        f.write(json.dumps(sql("s1", "UPDATE demos SET prompt = 'x';")) + "\n")
        f.write(json.dumps(result("s1", "[]")) + "\n")
    rc, out, _ = L.run()
    s = section(out)
    check("13n: a write made by a subagent of the worker is listed",
          "UPDATE demos" in s and "(1 of 2 tool calls scanned" in s, s or out[-900:])

    # 13o. GHL: a delete operation is a write, a get is not.
    L, rc, out, err, s = writes_of(
        use("g1", "mcp__leadconnector__execute_operation",
            {"operationId": "get-calendars", "locationId": "loc1", "reason": "read"}),
        result("g1", "{}"),
        use("g2", "mcp__leadconnector__execute_operation",
            {"operationId": "delete-contact-from-workflow", "locationId": "loc1",
             "params": {"path": {"contactId": "c1"}}, "reason": "stop the nurture"}),
        result("g2", "{}"))
    check("13o: a GHL delete operation is flagged and a get is not",
          "(1 of 2 tool calls scanned)" in s and "delete-contact-from-workflow" in s
          and "get-calendars" not in s, s or out[-900:])

    # 13p. inline code that writes through supabase-js, and a script the
    # worker wrote with the Write tool then ran.
    L, rc, out, err, s = writes_of(
        bash("b1", "cd /tmp && node --input-type=module <<'EOF'\nconst c = createClient(u, k);\n"
                   "const d = await c.from('demos').update({ prompt: p }).eq('id', ID);\nEOF"),
        result("b1", "ok"),
        use("w1", "Write", {"file_path": "/tmp/rig.mjs",
                            "content": "await client.from('prompt_versions').insert({a: 1});\n"}),
        result("w1", "written"),
        bash("b2", "node /tmp/rig.mjs"), result("b2", "ok"))
    check("13p: supabase-js writes in inline code and in a Written script are flagged",
          "(2 of 3 tool calls scanned)" in s and "update" in s and "insert" in s, s or out[-900:])

    # 13q. text that only MENTIONS a write is not one: a heredoc body written
    # to a file, a grep pattern, an echo, a Telegram notification.
    L, rc, out, err, s = writes_of(
        bash("b1", "cat > /tmp/steps.md <<'EOF'\ngit push origin main\nsupabase functions deploy x\nEOF"),
        result("b1", ""),
        bash("b2", "grep -rnE 'git push|gh pr merge' ~/.claude/hooks | head; echo \"git push later\""),
        result("b2", ""),
        bash("b3", "curl -s -X POST \"https://api.telegram.org/bot${TOKEN}/sendMessage\" "
                   "--data-urlencode chat_id=1 --data-urlencode text=done"),
        result("b3", "{}"))
    check("13q: heredoc text, grep patterns, echo and Telegram sends are not flagged",
          "PRODUCTION WRITES: none seen (0 of 3 tool calls scanned)" in out, s or out[-900:])

    # 13r. without the guard module the scan still flags (regex fallback) and
    # says it fell back.
    L = Layout(brief="# TASK\nShip it.", extra_records=[
        bash("b1", "git push origin main"),
        sql("s1", "UPDATE t SET a = 1;"), result("s1", "[]")])
    env = dict(L.env(), BG_SALVAGE_WRITE_GUARD=os.path.join(L.root, "missing-guard.py"))
    p = subprocess.run([sys.executable, SCRIPT, "--since", "180"],
                       capture_output=True, text=True, env=env)
    s = section(p.stdout)
    check("13r: with no guard module the fallback still flags git push and UPDATE",
          p.returncode == 0 and "(2 of 2 tool calls scanned)" in s and "git push origin main" in s
          and "fallback" in s, s or p.stdout[-900:] + p.stderr[-400:])

    # 13s. a Codex exec log: command_execution items are scanned too.
    L = Layout(brief="# TASK\nShip it.", with_log=False)
    codex_log = os.path.join(L.runs, "codex-1790000000000.log")
    with open(codex_log, "w") as f:
        for rec in (
            {"type": "thread.started", "thread_id": "x"},
            {"type": "item.started", "item": {"id": "item_1", "type": "command_execution",
                                              "command": "/bin/zsh -lc 'git status'",
                                              "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution",
                                                "command": "/bin/zsh -lc 'git status'",
                                                "exit_code": 0, "status": "completed"}},
            {"type": "item.started", "item": {"id": "item_2", "type": "command_execution",
                                              "command": "/bin/zsh -lc 'gh pr merge 12 --squash'",
                                              "status": "in_progress"}},
        ):
            f.write(json.dumps(rec) + "\n")
    rc, out, err = L.run("--writes", codex_log)
    check("13s: a Codex exec log is scanned; a call with no completion is UNKNOWN",
          rc == 0 and "(1 of 2 tool calls scanned)" in out and "UNKNOWN" in out
          and "gh pr merge 12" in out, out + err)

    # 13t. false positives the 200-run replay found (2026-09-29): a plan-only
    # EXPLAIN, a script's own --dry-run, capgo's currentBundle read, Python
    # that merely quotes a supabase-js line, and an edge function whose name
    # ends in "token" (the redactor ate the --project-ref flag after it).
    L, rc, out, err, s = writes_of(
        sql("t1", "EXPLAIN WITH d AS (DELETE FROM x RETURNING 1) SELECT * FROM d"), result("t1", "[]"),
        use("w1", "Write", {"file_path": "/tmp/apply.mjs",
                            "content": "await c.from('demos').update({a: 1});"}),
        result("w1", "written"),
        bash("b1", "node /tmp/apply.mjs --dry-run"), result("b1", "would update 1 row"),
        bash("b2", "npx -y @capgo/cli@8 channel currentBundle production"), result("b2", "1.0.18"),
        bash("b3", "python3 - <<'EOF'\nprint(\"x.from('demos').update({a:1})\")\nEOF"),
        result("b3", ""))
    check("13t: EXPLAIN, a --dry-run script, a capgo read and quoted JS are not flagged",
          "PRODUCTION WRITES: none seen (0 of 5 tool calls scanned)" in out, s or out[-900:])
    L, rc, out, err, s = writes_of(
        bash("b1", "supabase functions deploy demo-gptlive-token --project-ref dqzx --no-verify-jwt"),
        result("b1", "Deployed"))
    check("13t2: a function named *-token keeps its --project-ref in the printed statement",
          "demo-gptlive-token --project-ref dqzx" in s, s or out[-900:])

    # 14. QA round 1 (2026-09-29).
    # 14a. HIGH: a shell script the worker wrote, then ran. bg-1790164291634
    # made four admin-API writes through /tmp/rail2otp/gw.sh, all invisible.
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/ship.sh",
                            "content": "#!/bin/bash\nset -e\ngit push origin dev\n"}),
        result("w1", "written"),
        bash("b1", "chmod +x /tmp/bgsalv-fixture/ship.sh && bash /tmp/bgsalv-fixture/ship.sh"),
        result("b1", ""),
        bash("b2", "cat > /tmp/bgsalv-fixture/gw.sh <<'EOF'\ncurl -sS -X \"$1\" \"https://api.x.app$2\"\n"
                   "EOF\nchmod +x /tmp/bgsalv-fixture/gw.sh"), result("b2", ""),
        bash("b3", "/tmp/bgsalv-fixture/gw.sh PATCH /admin/tenants/t1/alerts/a1"), result("b3", "{}"))
    check("14a: a worker-written shell script that is run is scanned (bash f.sh, ./f.sh)",
          "(2 of 4 tool calls scanned)" in s and "in /tmp/bgsalv-fixture/ship.sh" in s
          and "gw.sh PATCH /admin/tenants/t1/alerts/a1" in s, s or out[-900:])

    # 14b. two writes in one Bash call are both named, in one row.
    L, rc, out, err, s = writes_of(
        bash("b1", "git push origin dev && supabase functions deploy demo-chat --project-ref abc"),
        result("b1", "ok"))
    row = next((l for l in s.splitlines() if l.startswith("ok")), "")
    check("14b: every write in one Bash call is listed on its row",
          "(1 of 1 tool calls scanned)" in s and "git push origin dev" in row
          and "supabase functions deploy demo-chat" in row, s or out[-900:])

    # 14c. {"error": null, ...} is a success envelope, not an error.
    L, rc, out, err, s = writes_of(
        bash("b1", "curl -sS -X POST https://api.operatorbase.app/v1/demos -d '{}'"),
        result("b1", '{"error":null,"id":"demo_123","ok":true}'))
    check("14c: a write whose body says {\"error\":null} is ok, not error",
          any(l.startswith("ok") for l in s.splitlines()), s or out[-900:])

    # 14d. secrets in columns named *_token / *_api_key are redacted; a plan
    # named "Basic Monthly" is left alone.
    L, rc, out, err, s = writes_of(
        sql("t1", "UPDATE tenant_settings SET twilio_auth_token = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6', "
                  "ghl_api_key = 'pit-0f6e3c2a-1111-2222-3333-444455556666', plan = 'Basic Monthly';"),
        result("t1", "[]"))
    check("14d: column-named secrets are redacted and prose after Basic is kept",
          "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" not in out and "pit-0f6e3c2a-1111" not in out
          and "Basic Monthly" in s, s or out[-900:])

    # 14e. SQL sent from a written pg / psycopg script is a write, unless its
    # connection string is local (the scratch DB rigs use 127.0.0.1:54322).
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/apply.mjs",
                            "content": "const pool = new Pool({connectionString: process.env.DATABASE_URL});\n"
                                       "await pool.query(`UPDATE tenant_agents SET a = 1 WHERE id = $1`, [id]);\n"}),
        result("w1", "written"),
        bash("b1", "node /tmp/bgsalv-fixture/apply.mjs"), result("b1", "UPDATE 1"),
        bash("b2", "DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres "
                   "node /tmp/bgsalv-fixture/apply.mjs"), result("b2", "UPDATE 1"))
    check("14e: SQL from a pg script is flagged; the same script on a local DB is not",
          "(1 of 3 tool calls scanned)" in s and "SQL UPDATE" in s, s or out[-900:])

    # 14f. an Edit that adds the write to a Written script is tracked.
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/rig.mjs", "content": "// TODO\n"}),
        result("w1", "written"),
        use("e1", "Edit", {"file_path": "/tmp/bgsalv-fixture/rig.mjs", "old_string": "// TODO",
                           "new_string": "await c.from('demos').update({a: 1});"}),
        result("e1", "edited"),
        bash("b1", "node /tmp/bgsalv-fixture/rig.mjs"), result("b1", "ok"))
    check("14f: an Edit after a Write is applied before the script is judged",
          "supabase-js update demos" in s, s or out[-900:])

    # 14g. a malformed tool id never takes the whole salvage run down.
    L = Layout(brief="# TASK\nShip it.", extra_records=[
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": ["not", "a", "string"], "name": "Bash",
             "input": {"command": "git push origin main"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": {"x": 1}, "content": "ok"}]}}])
    rc, out, err = L.run()
    check("14g: a list or dict tool id does not crash the listing",
          rc == 0 and "--- VERDICT ---" in out and "git push origin main" in section(out),
          (out + err)[-900:])

    # 14h. --writes <lane> means that lane, never a key that merely contains it.
    L = Layout(brief="# TASK\nx", extra_records=[
        sql("t1", "UPDATE lane_bg9 SET a = 1;"), result("t1", "[]")])
    with open(os.path.join(L.runs, "bg90-1790000000001.jsonl"), "w") as f:
        f.write(json.dumps(sql("t9", "UPDATE lane_bg90 SET a = 1;")) + "\n")
    rc, out, err = L.run("--writes", "bg9")
    check("14h: --writes bg9 resolves lane bg9, not a bg90 run that contains the string",
          rc == 0 and "lane_bg9 " in out and "lane_bg90" not in out, out + err)

    # 14i. `npm run deploy` is a deploy; a localhost curl with a valued flag
    # outside the known list is still local.
    L, rc, out, err, s = writes_of(
        bash("b1", "cd ~/dev/gym-tracker && npm run deploy"), result("b1", "ok"),
        bash("b2", "curl --max-redirs 5 -X POST http://localhost:1974/api/x -d a=1"), result("b2", "{}"))
    check("14i: npm run deploy is flagged and a localhost curl with --max-redirs is not",
          "(1 of 2 tool calls scanned)" in s and "npm run deploy" in s, s or out[-900:])
    # 14j. the script runs with ITS arguments: a GET through a method-taking
    # wrapper is a read, the same wrapper's POST is a write (sbapi.sh, gw.sh).
    wrapper = ("#!/bin/bash\nset -u\nMETHOD=$1; P=$2; BODY=${3:-}\n"
               "curl -sS -X \"$METHOD\" \"https://api.supabase.com/v1${P}\" --data \"$BODY\"\n")
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/sbapi.sh", "content": wrapper}),
        result("w1", "written"),
        bash("b1", "/tmp/bgsalv-fixture/sbapi.sh GET /projects/x/functions"), result("b1", "200"),
        bash("b2", "/tmp/bgsalv-fixture/sbapi.sh POST /projects/x/secrets '[{}]'"), result("b2", "201"))
    check("14j: a GET through a method-taking wrapper is a read, its POST a write",
          "(1 of 3 tool calls scanned)" in s and "sbapi.sh POST /projects/x/secrets" in s
          and "GET /projects/x/functions" not in s, s or out[-900:])

    # 14k. SQL literals in sqlite code are local, not production writes.
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/t.py",
                            "content": "import sqlite3\ndb = sqlite3.connect(p)\n"
                                       "db.execute(\"CREATE TABLE loads (id INTEGER)\")\n"}),
        result("w1", "written"),
        bash("b1", "python3 /tmp/bgsalv-fixture/t.py"), result("b1", "ok"))
    check("14k: sqlite SQL in a script is not a production write",
          "PRODUCTION WRITES: none seen (0 of 2 tool calls scanned)" in out, s or out[-900:])

    # QA round 2 (2026-09-29): four false negatives and a mislabelled outcome.
    # 15a. a short literal ('pg') before the SQL on the same line must not
    # pair its closing quote with the SQL's opening quote.
    L, rc, out, err, s = writes_of(
        bash("b1", "DATABASE_URL=postgres://postgres:pw@db.abc.supabase.co:5432/postgres node -e "
                   "\"const {Client}=require('pg');const c=new Client(process.env.DATABASE_URL);"
                   "await c.query('UPDATE t SET a=1')\""), result("b1", "UPDATE 1"))
    check("15a: pg SQL after a short literal on the same line is flagged",
          "(1 of 1 tool calls scanned)" in s and "SQL UPDATE" in s, s or out[-900:])

    # 15b. a runner flag that takes a value does not swallow the script path.
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/apply.mjs",
                            "content": "await c.from('demos').update({a: 1}).eq('id', id);\n"}),
        result("w1", "written"),
        use("w2", "Write", {"file_path": "/tmp/bgsalv-fixture/s.py",
                            "content": "import requests\nrequests.post('https://api.acme-vendor.com/v1/a', json={})\n"}),
        result("w2", "written"),
        bash("b1", "node -r dotenv/config /tmp/bgsalv-fixture/apply.mjs"), result("b1", "ok"),
        bash("b2", "node --import tsx /tmp/bgsalv-fixture/apply.mjs"), result("b2", "ok"),
        bash("b3", "python3 -W ignore /tmp/bgsalv-fixture/s.py"), result("b3", "ok"))
    rows = s.splitlines()
    check("15b: node -r x / --import x / python3 -W x still read the script",
          "(3 of 5 tool calls scanned)" in s
          and sum("supabase-js update demos" in l for l in rows) == 2
          and any("HTTP POST api.acme-vendor.com" in l for l in rows), s or out[-900:])

    # 15c. the HTTP method comes from argv, and a localhost-default base URL
    # is pointed at production by the run line's env.
    adm = ("const [,, method, path, body] = process.argv;\n"
           "await fetch('https://api.operatorbase.app' + path, {method, body});\n")
    rig = ("const BASE = process.env.BASE_URL || 'http://localhost:3000';\n"
           "await fetch(BASE + '/api/chat', {method: 'POST', body: '{}'});\n")
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/adm.mjs", "content": adm}),
        result("w1", "written"),
        use("w2", "Write", {"file_path": "/tmp/bgsalv-fixture/tc.cjs", "content": rig}),
        result("w2", "written"),
        bash("b1", "node /tmp/bgsalv-fixture/adm.mjs PATCH /admin/tenants/t1 '{\"a\":1}'"),
        result("b1", "{}"),
        bash("b2", "node /tmp/bgsalv-fixture/adm.mjs GET /admin/tenants/t1"), result("b2", "{}"),
        bash("b3", "BASE_URL=https://api.operatorbase.app node /tmp/bgsalv-fixture/tc.cjs"),
        result("b3", "{}"),
        bash("b4", "export BASE_URL=https://api.operatorbase.app; node /tmp/bgsalv-fixture/tc.cjs"),
        result("b4", "{}"),
        bash("b5", "node /tmp/bgsalv-fixture/tc.cjs"), result("b5", "{}"))
    rows = s.splitlines()
    # the same rule must not fire on a request log line or a DevTools message,
    # and must fire on a config-driven method (the GHL rails: r.method || 'GET')
    L2, _, out2, _, s2 = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/log.mjs",
                            "content": "page.on('request', (r) => log.push({ url: r.url(), method: r.method(), "
                                       "body: r.postData() }));\nawait fetch('https://x.acme-vendor.com/a');\n"
                                       "ws.send(JSON.stringify({ id, method, params }));\n"}),
        result("w1", "written"),
        use("w2", "Write", {"file_path": "/tmp/bgsalv-fixture/rail.mjs",
                            "content": "for (const r of reqs) await fetch(base + r.path, { method: r.method || 'GET', "
                                       "headers, body: JSON.stringify(r.body) });\n"
                                       "const base = 'https://backend.leadconnectorhq.com';\n"}),
        result("w2", "written"),
        bash("b1", "node /tmp/bgsalv-fixture/log.mjs"), result("b1", "ok"),
        bash("b2", "node /tmp/bgsalv-fixture/rail.mjs reqs.json"), result("b2", "ok"))
    check("15c2: a request log and a DevTools message are not writes; a config-driven method is",
          "(1 of 4 tool calls scanned)" in s2
          and "HTTP (method from a variable) backend.leadconnectorhq.com" in s2, s2 or out2[-900:])
    check("15c: an argv method and an env base URL are read; the GET and the local run are not",
          "(3 of 7 tool calls scanned)" in s
          and any("HTTP PATCH api.operatorbase.app" in l for l in rows)
          and sum("HTTP POST api.operatorbase.app" in l for l in rows) == 2
          and "adm.mjs GET" not in s, s or out[-900:])

    # 15d. secrets in JSON bodies, INSERT value lists, https userinfo and
    # vault.create_secret are redacted.
    L, rc, out, err, s = writes_of(
        bash("b1", "curl -X POST https://api.acme-vendor.com/a -d '{\"api_key\":\"abc123def456ghi789\","
                   "\"twilio_auth_token\":\"0123456789abcdef0123456789abcdef\"}'"), result("b1", "{}"),
        sql("t1", "INSERT INTO i (t, twilio_auth_token) VALUES "
                  "('00000000-0000-4000-8000-00000000a9e1', 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6');"),
        result("t1", "[]"),
        bash("b2", "curl -X POST https://ACa1b2c3:fedcba9876543210fedcba9876543210@api.twilio.com/2010/x"),
        result("b2", "{}"),
        sql("t2", "SELECT vault.create_secret('supersecretvalue0123456789', 'twilio', 'desc');"),
        result("t2", "[]"))
    check("15d: JSON-body, INSERT, https userinfo and vault secrets are redacted",
          "(4 of 4 tool calls scanned)" in s
          and not any(x in out for x in ("abc123def456ghi789", "0123456789abcdef0123456789abcdef",
                                         "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
                                         "fedcba9876543210fedcba9876543210",
                                         "supersecretvalue0123456789"))
          and "00000000-0000-4000-8000-00000000a9e1" in s, s or out[-900:])

    # 15e. the tool-output overflow envelope means the call RAN: a landed
    # UPDATE ... RETURNING * must not read as failed.
    L, rc, out, err, s = writes_of(
        sql("t1", "UPDATE demos SET a = 1 RETURNING *;"),
        result("t1", "Error: result (300,148 characters across 1 line) exceeds maximum allowed "
                     "tokens. Output has been saved to /Users/x/tool-results/t1.txt"))
    check("15e: an overflowed result of a write is ok, not error",
          any(l.startswith("ok") and "UPDATE demos" in l for l in s.splitlines()), s or out[-900:])

    # QA round 3 (2026-09-29).
    # 16a. a POST through a client instance (requests.Session, httpx.Client,
    # axios.create) is a write; an Express route handler is not.
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/s1.py",
                            "content": "import requests\ns = requests.Session()\n"
                                       "s.post('https://api.acme-vendor.com/v1/a', json={})\n"}),
        result("w1", "written"),
        use("w2", "Write", {"file_path": "/tmp/bgsalv-fixture/s2.mjs",
                            "content": "const api = axios.create({ baseURL: 'https://api.acme-vendor.com' });\n"
                                       "await api.patch('/v1/b', { a: 1 });\n"}),
        result("w2", "written"),
        use("w3", "Write", {"file_path": "/tmp/bgsalv-fixture/srv.mjs",
                            "content": "app.post('/hook', h);\nconst r = await fetch('https://api.acme-vendor.com/v1/c');\n"}),
        result("w3", "written"),
        bash("b1", "python3 /tmp/bgsalv-fixture/s1.py"), result("b1", "ok"),
        bash("b2", "node /tmp/bgsalv-fixture/s2.mjs"), result("b2", "ok"),
        bash("b3", "node /tmp/bgsalv-fixture/srv.mjs"), result("b3", "ok"))
    check("16a: session/client-instance writes are flagged; an Express route is not",
          "(2 of 6 tool calls scanned)" in s and "HTTP POST api.acme-vendor.com" in s
          and "HTTP PATCH api.acme-vendor.com" in s and "srv.mjs" not in s, s or out[-900:])

    # 16b. naming a secret column must not blank the row's identity: a quoted
    # table name or a location id compared with = stays readable.
    L, rc, out, err, s = writes_of(
        sql("t1", "UPDATE \"public\".\"tenant_settings_v2\" SET twilio_auth_token = "
                  "'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6' WHERE location_id = 've9EPM428h8vShlRW1KT';"),
        result("t1", "[]"))
    check("16b: a secret column's value is redacted, the table and the row id are not",
          "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" not in out and "tenant_settings_v2" in s
          and "ve9EPM428h8vShlRW1KT" in s, s or out[-900:])

    # 16c. a Telegram send made from code is not a production write.
    L, rc, out, err, s = writes_of(
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/tg.py",
                            "content": "import requests\nrequests.post(f\"https://api.telegram.org/bot{tok}"
                                       "/sendDocument\", files=f)\n"}),
        result("w1", "written"),
        bash("b1", "python3 /tmp/bgsalv-fixture/tg.py"), result("b1", "ok"))
    check("16c: a Telegram sendDocument from Python is not flagged",
          "PRODUCTION WRITES: none seen (0 of 2 tool calls scanned)" in out, s or out[-900:])

    # Independent verifier (2026-09-29).
    # 17a. opening a PR or commenting on an issue is a write (46 real
    # `gh pr create` calls were unlisted); viewing one is not.
    L, rc, out, err, s = writes_of(
        bash("b1", "gh pr create --title x --body y --base dev"), result("b1", "https://github.com/o/r/pull/7"),
        bash("b2", "gh issue comment 5 --body z"), result("b2", "ok"),
        bash("b3", "gh pr view 7 --json state"), result("b3", "{}"))
    check("17a: gh pr create and gh issue comment are flagged, gh pr view is not",
          "(2 of 3 tool calls scanned)" in s and "gh pr create" in s and "gh issue comment" in s,
          s or out[-900:])

    # 17b. a CloudFormation deploy is a write.
    L, rc, out, err, s = writes_of(
        bash("b1", "aws cloudformation deploy --template-file t.yml --stack-name s"), result("b1", "ok"))
    check("17b: aws cloudformation deploy is flagged", "(1 of 1 tool calls scanned)" in s, s or out[-900:])

    # 17c. an AWS secret key, an SSM --value and a `Token` auth header are redacted.
    L, rc, out, err, s = writes_of(
        bash("b1", "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY1 aws s3 cp f s3://b/f"),
        result("b1", "ok"),
        bash("b2", "aws ssm put-parameter --name /da/fcm --value 'Zq9v8Kp2Lm4Nw7Rt1Yb3' --overwrite"),
        result("b2", "ok"),
        bash("b3", "curl -X POST https://api.acme-vendor.com/x -H 'Authorization: Token key_1a2b3c4d5e6f7g8h'"),
        result("b3", "{}"))
    check("17c: AWS secret keys, --value and Token credentials are redacted, the names are not",
          "(3 of 3 tool calls scanned)" in s and "/da/fcm" in s
          and not any(x in out for x in ("wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY1", "Zq9v8Kp2Lm4Nw7Rt1Yb3",
                                         "key_1a2b3c4d5e6f7g8h")), s or out[-900:])

    # 17d. a worker-written test file run over and over is still listed, but
    # tagged and sorted after the real writes so one real write stays visible.
    L, rc, out, err, s = writes_of(
        bash("b0", "git push origin dev", ts="2026-09-29T17:00:00.000Z"), result("b0", "ok"),
        use("w1", "Write", {"file_path": "/tmp/bgsalv-fixture/tests/test_lane.py",
                            "content": "import requests\nrequests.post('https://www.acme-vendor.com/x')\n"}),
        result("w1", "written"),
        bash("b1", "python3 /tmp/bgsalv-fixture/tests/test_lane.py", ts="2026-09-29T17:30:00.000Z"),
        result("b1", "ok"))
    rows = [l for l in s.splitlines() if l.startswith(("ok", "error", "UNKNOWN"))]
    check("17d: a test-file row is tagged and listed after the real write",
          len(rows) == 2 and "git push origin dev" in rows[0] and "(test file)" in rows[1],
          s or out[-900:])
    shutil.rmtree("/tmp/bgsalv-fixture", ignore_errors=True)


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

    # 12. DRAFT REPORTS (self-audit 2026-09-27, P3): 17 of 80 workers ended
    # without a final report after a usage wall, 12 of them inside the
    # verifier. Workers now write bg-reports/<runId>.draft.md before the
    # verifier, and --report hands that draft back when the final is missing.
    LIMIT_DEATH = [
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "You've hit your session limit \u00b7 resets 6:20pm"}]}},
        {"type": "result", "subtype": "success", "is_error": True,
         "result": "You've hit your session limit \u00b7 resets 6:20pm"},
    ]
    DRAFT = "# Draft report\n\nShipped the handler; tests 12 of 12.\nverifier not run yet.\n"

    L = Layout(brief="# TASK\nShip the handler.", log_text="Dispatching qa-agent now.",
               extra_records=LIMIT_DEATH)
    draft = L.make_draft(DRAFT)
    key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    rc, out, _ = L.run()
    verdict = out.split("--- VERDICT ---")[-1]
    check("12a: the listing names the draft report of a dead worker",
          "DRAFT REPORT" in out and draft in out, out[-800:])
    check("12b: a draft of a worker with no final report flips the verdict",
          SURVIVED in out and NOTHING not in out and f"--report {key}" in verdict, verdict)
    rc, out, err = L.run("--report", key)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    body = open(written).read() if written and os.path.exists(written) else ""
    check("12c: --report writes the draft when the worker has no final report",
          rc == 0 and DRAFT in body, out + err)
    check("12d: the written draft is labelled at the top, with its time",
          body.startswith("DRAFT REPORT: this worker ended without a final report; "
                          "below is the last draft it wrote (") and "T" in body.splitlines()[0],
          body[:200])
    check("12e: the limit message is not passed off as the report",
          "hit your session limit" not in body, body[:300])
    if written and os.path.exists(written):
        os.remove(written)

    # 12f. no run log at all, only the draft: still recoverable.
    L = Layout(brief="# TASK\nShip the handler.", with_log=False)
    L.make_draft(DRAFT)
    key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    rc, out, err = L.run("--report", key)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    body = open(written).read() if written and os.path.exists(written) else ""
    check("12f: a draft with no run log is still written by --report",
          rc == 0 and body.startswith("DRAFT REPORT") and DRAFT in body, out + err)
    if written and os.path.exists(written):
        os.remove(written)

    # 12g. a worker that FINISHED: its final report wins over the draft.
    FINAL = "FINAL REPORT\n" + ("y" * 300)
    L = Layout(brief="# TASK\nShip the handler.", log_text=FINAL,
               extra_records=[{"type": "result", "subtype": "success", "is_error": False,
                               "result": FINAL}])
    L.make_draft(DRAFT)
    key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    rc, out, err = L.run("--report", key)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    body = open(written).read() if written and os.path.exists(written) else ""
    check("12g: a finished worker's --report is its final report, not the draft",
          rc == 0 and body == FINAL, body[:200])
    rc, out, _ = L.run()
    check("12h: the listing says a finished worker's draft is superseded",
          "DRAFT REPORT" in out and "superseded" in out, out[-600:])
    if written and os.path.exists(written):
        os.remove(written)

    # 12i. an EMPTY draft is not a draft.
    L = Layout(brief="# TASK\nShip the handler.", log_text="Dispatching qa-agent now.",
               extra_records=LIMIT_DEATH)
    L.make_draft("")
    key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    rc, out, _ = L.run("--report", key)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    body = open(written).read() if written and os.path.exists(written) else ""
    check("12i: an empty draft is ignored (the transcript tail is written as before)",
          rc == 0 and not body.startswith("DRAFT REPORT"), body[:200])
    if written and os.path.exists(written):
        os.remove(written)

    # 12j. a LIVE worker's draft is not a relaunch or recovery candidate.
    L = Layout(brief="# TASK\nBuild the film.", log_text="Rendering.", pid=os.getpid())
    L.make_draft(DRAFT)
    key = list(json.load(open(os.path.join(L.bridge, "bg-inflight.json"))))[0]
    rc, out, _ = L.run()
    verdict = out.split("--- VERDICT ---")[-1]
    check("12j: a live worker with a draft stays STILL RUNNING, no --report offered",
          "STILL RUNNING" in out and f"--report {key}" not in verdict, verdict)
    # 12k. QA 2026-09-27: --report on that LIVE worker must not say it ended.
    rc, out, err = L.run("--report", key)
    written = out.split("wrote ")[1].split(" ")[0] if "wrote " in out else ""
    body = open(written).read() if written and os.path.exists(written) else ""
    check("12k: --report on a live worker labels the draft STILL RUNNING, never ended",
          rc == 0 and "ended without a final report" not in (body + out)
          and "STILL RUNNING" in (body.splitlines()[0] if body else "") and DRAFT in body,
          (out + err + body[:200]))
    if written and os.path.exists(written):
        os.remove(written)

    production_writes()

    for d in _dirs:
        shutil.rmtree(d, ignore_errors=True)
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
