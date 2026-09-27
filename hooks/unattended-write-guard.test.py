#!/usr/bin/env python3
"""Suite for unattended-write-guard.py.

Run: python3 ~/.claude/hooks/unattended-write-guard.test.py

Two layers:
  A. Subprocess cases: the real script, a scrubbed environment per class of
     run, and the exit code. This is what proves the attended classes are
     untouched and the malformed payloads fail open.
  B. Classifier cases: the pure functions imported directly (fast), one per
     statement kind and per trap (string literals, comments, heredoc bodies,
     grep patterns, commit messages).

Exit 0 = all pass.
"""

import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "unattended-write-guard.py")

ALLOW, BLOCK = 0, 2

SCRUB = (
    "TMUX",
    "LEASH_LANE",
    "CLAUDE_CODE_ENTRYPOINT",
    "LEASH_TRIGGER",
    "LEASH_SCHEDULE_ID",
    "LEASH_ALLOW_WRITE",
    "BG_REPORT_DRAFT",
    "BG_RUN_STARTED_AT",
)

TMUX_VAL = "/tmp/tmux-501/default,123,0"
SCHEDULE = {"LEASH_LANE": "bg", "LEASH_TRIGGER": "schedule", "LEASH_SCHEDULE_ID": "42",
            "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}
SCRIPT_RUN = {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}

passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"ok    {label}")
    else:
        failed += 1
        print(f"FAIL  {label}" + (f": {detail}" if detail else ""))


def run(payload, env_over=None):
    env = dict(os.environ)
    for k in SCRUB:
        env.pop(k, None)
    env.update(env_over or {})
    data = json.dumps(payload) if isinstance(payload, (dict, list)) else payload
    p = subprocess.run([sys.executable, GUARD], input=data, capture_output=True,
                       text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def migration():
    return {"tool_name": "mcp__supabase__apply_migration",
            "tool_input": {"project_id": "abc", "name": "00190_x", "query": "alter table t add c int"}}


def sql(query):
    return {"tool_name": "mcp__supabase__execute_sql",
            "tool_input": {"project_id": "abc", "query": query}}


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def expect(label, want, payload, env, stderr_has=()):
    code, out, err = run(payload, env)
    problems = []
    if code != want:
        problems.append(f"exit {code} (wanted {want})")
    for s in stderr_has:
        if s not in err:
            problems.append(f"stderr missing {s!r}")
    check(label, not problems, "; ".join(problems) + (f" | stderr: {err[:160]!r}" if problems else ""))


def load_module():
    spec = importlib.util.spec_from_file_location("unattended_write_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    # ======================================================================
    # A. env classes (subprocess)
    # ======================================================================
    expect("env: TMUX set + schedule trigger => allow (attended)", ALLOW, migration(),
           dict(SCHEDULE, TMUX=TMUX_VAL))
    expect("env: chat lane => allow", ALLOW, migration(),
           {"LEASH_LANE": "chat", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})
    expect("env: bg worker without a schedule trigger => allow", ALLOW, migration(),
           {"LEASH_LANE": "bg", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})
    expect("env: bridge schedule run => BLOCK, names the schedule id", BLOCK, migration(), SCHEDULE,
           ["bridge schedule #42", "go-ahead", "--allow-write", "Never retry"])
    expect("env: schedule run without an id still blocks", BLOCK, migration(),
           {k: v for k, v in SCHEDULE.items() if k != "LEASH_SCHEDULE_ID"}, ["bridge schedule"])
    expect("env: schedule run + LEASH_ALLOW_WRITE=1 => allow", ALLOW, migration(),
           dict(SCHEDULE, LEASH_ALLOW_WRITE="1"))
    expect("env: LEASH_ALLOW_WRITE=true is not the approval value => BLOCK", BLOCK, migration(),
           dict(SCHEDULE, LEASH_ALLOW_WRITE="true"))
    expect("env: headless script (sdk-cli, no LEASH_LANE) => BLOCK", BLOCK, migration(), SCRIPT_RUN,
           ["headless script run"])
    expect("env: headless script + LEASH_ALLOW_WRITE=1 => allow", ALLOW, migration(),
           dict(SCRIPT_RUN, LEASH_ALLOW_WRITE="1"))
    expect("env: interactive cli outside tmux => allow", ALLOW, migration(),
           {"CLAUDE_CODE_ENTRYPOINT": "cli"})
    expect("env: interactive cli in tmux => allow", ALLOW, migration(),
           {"CLAUDE_CODE_ENTRYPOINT": "cli", "TMUX": TMUX_VAL})
    expect("env: no marker env at all => allow", ALLOW, migration(), {})
    expect("env: schedule trigger on a non-bg lane still counts as a schedule", BLOCK, migration(),
           {"LEASH_TRIGGER": "schedule", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})

    # per tool, unattended
    expect("tool: execute_sql write in a schedule run => BLOCK", BLOCK,
           sql("update tenants set plan='x' where id=1"), SCHEDULE, ["UPDATE"])
    expect("tool: execute_sql read in a schedule run => allow", ALLOW,
           sql("select count(*) from tenants"), SCHEDULE)
    expect("tool: Bash supabase db push in a script run => BLOCK", BLOCK,
           bash("cd /Users/zalo/dev/delta-agents && supabase db push"), SCRIPT_RUN,
           ["supabase db push"])
    expect("tool: Bash read-only command in a schedule run => allow", ALLOW,
           bash("git status --short"), SCHEDULE)
    expect("tool: an unrelated tool => allow", ALLOW,
           {"tool_name": "Read", "tool_input": {"file_path": "/x"}}, SCHEDULE)
    expect("tool: execute_sql write in the chat lane => allow (attended)", ALLOW,
           sql("delete from t"), {"LEASH_LANE": "chat", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})

    # malformed payloads fail open, even when unattended
    expect("malformed: not json => allow", ALLOW, "not json", SCHEDULE)
    expect("malformed: empty stdin => allow", ALLOW, "", SCHEDULE)
    expect("malformed: json list => allow", ALLOW, [1, 2], SCHEDULE)
    expect("malformed: execute_sql without tool_input => allow", ALLOW,
           {"tool_name": "mcp__supabase__execute_sql"}, SCHEDULE)
    expect("malformed: execute_sql with a non-string query => allow", ALLOW,
           {"tool_name": "mcp__supabase__execute_sql", "tool_input": {"query": 5}}, SCHEDULE)
    expect("malformed: Bash with a list tool_input => allow", ALLOW,
           {"tool_name": "Bash", "tool_input": ["x"]}, SCHEDULE)
    expect("malformed: Bash with no command => allow", ALLOW,
           {"tool_name": "Bash", "tool_input": {}}, SCHEDULE)
    expect("apply_migration holds whatever its tool_input looks like", BLOCK,
           {"tool_name": "mcp__supabase__apply_migration"}, SCHEDULE)

    # ======================================================================
    # B. classifiers (imported)
    # ======================================================================
    try:
        m = load_module()
    except Exception as e:  # the module is missing or broken: every B case fails
        check("B: module imports", False, repr(e))
        return finish()

    def w(q):
        return m.sql_write_reason(q)

    writes = {
        "INSERT": "insert into t (a) values (1)",
        "UPDATE": "UPDATE t SET a = 1 WHERE id = 2",
        "DELETE": "delete from t where id = 3",
        "MERGE": "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = s.a",
        "INSERT ON CONFLICT (upsert)": "insert into t values (1) on conflict (id) do update set a = 2",
        "UPSERT keyword": "upsert into t values (1)",
        "TRUNCATE": "truncate table t",
        "DROP": "drop table if exists t",
        "ALTER": "alter table t add column c int",
        "CREATE": "create index concurrently i on t (a)",
        "GRANT": "grant select on t to anon",
        "REVOKE": "revoke all on t from public",
        "COPY FROM": "copy t (a, b) from stdin",
        "psql \\copy FROM": "\\copy t from '/tmp/x.csv' csv",
        "SELECT INTO": "select * into t_backup from t",
        "CALL": "call refresh_stats()",
        "REFRESH MATERIALIZED VIEW": "refresh materialized view concurrently mv",
        "DML inside WITH": "with d as (delete from t where id = 1 returning *) select count(*) from d",
        "UPDATE inside WITH": "WITH u AS (UPDATE t SET a = 1 RETURNING id) SELECT * FROM u",
        "DO block": "do $$ begin perform 1; end $$",
        "second statement writes": "select 1; delete from t",
        "leading comment then write": "-- cleanup\ndelete from t",
        "block comment then write": "/* note */ update t set a = 1",
        "nested block comment then write": "/* a /* b */ c */ delete from t",
        "EXPLAIN ANALYZE runs the DML": "explain analyze delete from t",
        "EXPLAIN (ANALYZE) runs the DML": "explain (analyze, buffers) update t set a = 1",
        "PREPARE AS INSERT": "prepare p as insert into t values ($1)",
        "cron.schedule": "select cron.schedule('job', '* * * * *', 'select 1')",
        "vault.create_secret": "select vault.create_secret('x', 'name')",
        "setval": "select setval('t_id_seq', 100)",
        "pg_terminate_backend": "select pg_terminate_backend(123)",
        "net.http_post": "select net.http_post(url := 'https://x')",
        "COMMENT ON": "comment on table t is 'x'",
        "parenthesised write": "(delete from t)",
        "psql meta-commands before a single write":
            "\\set ON_ERROR_STOP on\n\\echo '=== fix ==='\nupdate t set a = 1",
        "a write ended by \\g instead of a semicolon": "delete from t \\g",
    }
    for label, q in writes.items():
        check(f"sql write: {label}", bool(w(q)), f"{q!r} -> {w(q)!r}")

    reads = {
        "plain SELECT": "select id, name from tenants where id = 1",
        "SELECT with a 'delete' literal": "select * from audit where action = 'delete'",
        "SELECT with an escaped quote literal": "select 'it''s an update; drop table t' as note",
        "E-string with backslash quote": "select E'it\\'s a delete from t' as x",
        "dollar-quoted literal": "select $$ drop table t $$ as x",
        "tagged dollar quote": "select $tag$ insert into t $tag$",
        "comment mentions delete": "select 1 -- delete from t later",
        "block comment mentions drop": "/* drop table t */ select 1",
        "quoted identifier named update": 'select "update", "delete" from t',
        "column names contain write words": "select deleted_at, updated_at, created_at, inserted_by from t",
        "SELECT FOR UPDATE is a lock, not a write": "select * from t where id = 1 for update",
        "WITH ... FOR NO KEY UPDATE": "with x as (select * from t for no key update) select * from x",
        "read-only WITH": "with a as (select 1 as n) select n from a",
        "EXPLAIN SELECT": "explain select * from t",
        "EXPLAIN without ANALYZE of DML plans only": "explain delete from t",
        "SHOW": "show search_path",
        "COPY TO stdout": "copy (select * from t) to stdout with csv",
        "COPY TO with a FROM inside the subquery": "copy (select a from t where b in (select b from u)) to stdout",
        "psql \\d": "\\d tenants",
        "SELECT INTO inside a subquery is not a table write": "select (select 1) as x",
        "BEGIN/ROLLBACK around a read": "begin; select 1; rollback;",
        "SET search_path": "set search_path to public",
        "information_schema read": "select column_name from information_schema.columns where table_name='t'",
        "pg_policies read mentioning UPDATE cmd": "select * from pg_policies where cmd = 'UPDATE'",
        "positional param is not a dollar quote": "select * from t where id = $1 and name = 'a'",
        "psql meta-commands around reads": "\\pset pager off\n\\echo 'update t'\nselect 1;\n\\x on\nselect 2",
        "a read ended by \\gset": "select count(*) as n from t \\gset",
        "empty query": "",
    }
    for label, q in reads.items():
        check(f"sql read: {label}", not w(q), f"{q!r} -> {w(q)!r}")

    def b(c):
        return m.bash_write_reason(c)

    bash_writes = {
        "supabase db push": "supabase db push",
        "npx supabase db push": "npx supabase db push --linked",
        "npx -y supabase@latest db push": "npx -y supabase@latest db push",
        "bunx supabase migration up --linked": "bunx supabase migration up --linked",
        "supabase db reset --linked": "supabase db reset --linked",
        "supabase db reset against a remote --db-url": "supabase db reset --db-url \"$PROD_DB_URL\"",
        "supabase db push --db-url remote": "supabase db push --db-url postgresql://u:p@db.abc.supabase.co:5432/postgres",
        "quoted env assignment before the command":
            "SUPABASE_SESSION_POOLER_URL='postgresql://x@127.0.0.1:54322/p' supabase migration up --linked",
        "supabase with a global flag first": "supabase --workdir /x db push",
        "after cd &&": "cd /Users/zalo/dev/delta-agents && supabase db push",
        "env assignment prefix": "SUPABASE_ACCESS_TOKEN=x supabase db push",
        "absolute binary path": "/opt/homebrew/bin/supabase db push",
        "inside bash -c": "bash -lc 'cd /x && supabase db push'",
        "prisma migrate deploy": "npx prisma migrate deploy",
        "prisma db push": "prisma db push --accept-data-loss",
        "drizzle-kit push": "npx drizzle-kit push",
        "psql -c UPDATE": "psql \"$DATABASE_URL\" -c \"UPDATE tenants SET plan='x'\"",
        "psql -tAc DELETE (clustered flag)": "psql -tAc 'delete from t' postgres",
        "psql --command=": "psql --command='drop table t'",
        "psql -f": "psql \"$URL\" -f migrations/0001.sql",
        "psql --file=": "psql --file=/tmp/x.sql",
        "psql < file": "psql \"$URL\" < /tmp/restore.sql",
        "psql heredoc with a write": "psql \"$URL\" <<'SQL'\nINSERT INTO t VALUES (1);\nSQL",
        "docker exec psql to a remote host": "docker exec -i db psql -h db.abc.supabase.co -U postgres -c 'delete from t'",
        "docker exec psql with a URL variable": "docker exec -i db psql \"$DATABASE_URL\" -c 'delete from t'",
        "psql to a remote URI": "psql 'postgresql://u:p@db.abc.supabase.co:5432/postgres' -c 'delete from t'",
        "psql with no host outside a container": "psql -U postgres -c 'drop table t'",
        "psql with a remote PGHOST assignment": "PGHOST=db.abc.supabase.co psql -c 'delete from t'",
        "echo write | psql": "echo 'delete from t' | psql \"$URL\"",
        "second psql -c writes": "psql -c 'select 1' -c 'truncate t'",
        "on its own line after a comment": "# apply it\nsupabase db push",
        "prisma with no DATABASE_URL in sight": "npx prisma migrate deploy",
        "psql -f a file this command wrote with a WRITE heredoc":
            "cat > /tmp/w.sql <<'SQL'\nupdate t set a = 1;\nSQL\npsql \"$URL\" -f /tmp/w.sql",
        "psql -f a file this command did not write (unknown content)":
            "cat > /tmp/other.sql <<'SQL'\nselect 1;\nSQL\npsql \"$URL\" -f /tmp/migration.sql",
    }
    for label, c in bash_writes.items():
        check(f"bash write: {label}", bool(b(c)), f"{c!r} -> {b(c)!r}")

    bash_reads = {
        "supabase migration list": "supabase migration list --linked",
        "supabase db diff": "supabase db diff --linked",
        "supabase db push --dry-run": "supabase db push --dry-run",
        "supabase functions deploy (not a db write)": "supabase functions deploy x --use-api",
        "git commit message mentions db push": "git commit -m \"fix: run supabase db push after review\"",
        "grep for the command": "grep -rn \"supabase db push\" docs/",
        "rg for prisma": "rg 'prisma migrate deploy' .",
        "echo mentions psql -c write": "echo 'psql -c \"DELETE FROM x\"'",
        "heredoc body mentions db push": "cat > /tmp/notes.md <<'EOF'\nthen run supabase db push\nEOF",
        "python heredoc with psql text": "python3 - <<'PY'\nprint('psql -c \"drop table t\"')\nPY",
        "psql -c SELECT": "psql \"$URL\" -c \"select count(*) from t\"",
        "psql -c \\d": "psql -c '\\d tenants'",
        "psql -tAc read": "docker exec -i db psql -U postgres -tAc \"SELECT extname FROM pg_extension\"",
        "psql heredoc read": "psql \"$URL\" <<'SQL'\nselect 1;\nSQL",
        "psql -l": "psql -l",
        "a file named supabase-db-push.md": "cat docs/supabase-db-push.md",
        "comment line mentions db push": "# later: supabase db push\ngit status",
        "echo of prisma text": "echo \"prisma db push\"",
        "psql version": "psql --version",
        "psql -f a file this command wrote with a read-only heredoc (b5254a5f)":
            "cat > /tmp/q.sql <<'SQL'\nselect count(*) from t;\nSQL\n"
            "docker cp /tmp/q.sql db:/tmp/q.sql\n"
            "docker exec -e PGURL=\"$POOLER_URL\" db sh -c 'psql \"$PGURL\" -At -f /tmp/q.sql'",
        "psql < a file this command wrote with a read-only heredoc":
            "cat > /tmp/r.sql <<'SQL'\nselect 1;\nSQL\npsql \"$URL\" < /tmp/r.sql",
        "which psql": "which psql && psql --version",
        "empty command": "",
    }
    for label, c in bash_reads.items():
        check(f"bash read: {label}", not b(c), f"{c!r} -> {b(c)!r}")

    # Local targets are not what this hook exists for: the 60-day replay found
    # 621 of 621 pattern matches were local scratch databases.
    bash_local = {
        "supabase db reset (local by default)": "supabase db reset",
        "supabase db reset --local": "npx supabase db reset --local",
        "supabase migration up (local by default)": "bunx supabase migration up",
        "supabase db push --local": "supabase db push --local",
        "supabase db push to a loopback --db-url":
            "supabase db push --db-url postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        "docker exec psql into the local container":
            "docker exec -i supabase_db_x psql -U postgres -c 'DROP DATABASE scratch'",
        "docker exec psql -d $DB (a database name, not a URL)":
            "docker exec -i db psql -U postgres -d $DB -v ON_ERROR_STOP=1 < /tmp/m.sql",
        "docker exec sh -c with psql inside":
            "docker exec db sh -c 'pg_dump -U postgres -d a | psql -U postgres -d b'",
        "psql -h localhost": "psql -h localhost -U postgres -c 'drop table t'",
        "psql to a loopback URI":
            "psql postgresql://postgres:postgres@127.0.0.1:54322/postgres -c 'delete from t'",
        "psql with a socket host": "psql -h /tmp -c 'truncate t'",
        "prisma with a loopback DATABASE_URL":
            "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/x npx prisma migrate deploy",
        "quoted env assignment, local migration up":
            "SUPABASE_SESSION_POOLER_URL='postgresql://x@127.0.0.1:54322/p' supabase migration up --local",
    }
    for label, c in bash_local.items():
        check(f"bash local target passes: {label}", not b(c), f"{c!r} -> {b(c)!r}")

    # The switch back to the literal list holds local targets too.
    saved = m.HOLD_LOCAL_TARGETS
    try:
        m.HOLD_LOCAL_TARGETS = True
        for label, c in bash_local.items():
            check(f"HOLD_LOCAL_TARGETS=True holds: {label}", bool(b(c)), f"{c!r} -> {b(c)!r}")
    finally:
        m.HOLD_LOCAL_TARGETS = saved

    return finish()


def finish():
    total = passed + failed
    print()
    if failed:
        print(f"{passed}/{total} passed, {failed} FAILED")
        return 1
    print(f"{total}/{total} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
