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
    writes.update({
        # QA 2026-09-27 round 1
        "\\gexec runs the SQL a query generates": "select 'DELETE FROM t' \\gexec",
        "schema-qualified setval": "SELECT pg_catalog.setval('s', 1)",
        "lo_import creates a large object": "SELECT lo_import('/tmp/x')",
        "net.http_get queues a request row": "SELECT net.http_get('https://example.org')",
        # QA 2026-09-27 hooks round 1: the replay's 15 write functions called from a SELECT
        "a public write function (set_)": "SELECT public.set_user_plan_service('4137ea16'::uuid, NULL)",
        "a public ingest function": "SELECT public.sales_challenge_ingest() AS rows_written",
        "a public sweep function": "select public.sweep_demo_gptlive_calls()",
        "a public reconcile function": "select public.reconcile_demo_gptlive_recordings()",
        "an unqualified write function": "select sweep_demo_gptlive_calls()",
        "a write function in FROM with an alias": "select * from public.sync_users() as s",
    })
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
        "builtin set_config is a session setting": "select set_config('search_path', 'public', false)",
        "jsonb_set is a value function": "select jsonb_set(data, '{a}', '1') from t",
        "a public read function": "select public.get_tenant_summary('x')",
        "log() math": "select log(10)",
        # QA 2026-09-27 hooks round 2: `column op (` is not a call
        "run_id = (subquery)": "SELECT * FROM prompt_run_steps WHERE run_id = (SELECT id FROM prompt_runs ORDER BY created_at DESC LIMIT 1)",
        "send_attempts >= (subquery)": "select * from jobs where send_attempts >= (select max_attempts from cfg)",
        "a CTE named with a verb": "WITH sync_rows(id) AS (SELECT 1) SELECT * FROM sync_rows",
        "a second CTE named with a verb": "WITH a AS (SELECT 1), refund_totals(x) AS (SELECT 2) SELECT * FROM refund_totals",
        "cast with ::": "select run_id::text from t",
        "count and now": "select count(*), now() from t",
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
    # QA 2026-09-27 round 1: remote writes that the first version let through.
    bash_writes.update({
        "--db-url from a variable (any name is a URL there)": 'supabase db push --db-url "$PROD_DB"',
        "--db-url from a short variable": "supabase db push --db-url $TARGET",
        "--db-url assigned a remote URL in the same command":
            'PROD_DB=postgresql://postgres:pw@db.abc.supabase.co:5432/postgres; supabase db push --db-url "$PROD_DB"',
        "supabase db reset --linked=true": "supabase db reset --linked=true",
        "supabase migration up --linked=true": "supabase migration up --linked=true",
        "supabase migration up --db-url from a variable": 'supabase migration up --db-url "$PROD"',
        "--db-url whose host is in the query string":
            'supabase db push --db-url "postgresql://postgres:pw@/postgres?host=db.abc.supabase.co"',
        "prisma with DATABASE_URL from a variable": 'DATABASE_URL="$PROD" npx prisma migrate deploy',
        "prisma with DATABASE_URL=$VAR unquoted": "DATABASE_URL=$PROD_DB npx prisma migrate deploy",
        "a remote URI with a $PW password": 'psql "postgresql://postgres:$PW@db.abc.supabase.co/postgres" -c "delete from t"',
        "npm run db:seed": "npm run db:seed",
        "docker exec psql to a prod-named variable": 'docker exec supabase_db_x psql "$PROD" -c "DELETE FROM users"',
        "docker exec psql to a URL assigned in the same command":
            'PROD=postgresql://postgres:pw@db.abc.supabase.co/postgres; docker exec supabase_db_x psql "$PROD" -c "DELETE FROM users"',
        "docker exec psql with a hostaddr conninfo":
            'docker exec supabase_db_x psql "hostaddr=34.1.2.3 dbname=postgres user=postgres" -c "DELETE FROM users"',
        "docker exec -ePGHOST= attached": "docker exec -ePGHOST=db.abc.supabase.co supabase_db_x psql -U postgres -c 'DELETE FROM users'",
        "docker exec psql -d a name that resolves to a remote URL":
            'DB=postgresql://postgres:pw@db.abc.supabase.co/postgres; docker exec -i db psql -U postgres -d "$DB" -c "delete from t"',
        "docker -H ssh:// (a remote daemon)": "docker -H ssh://prod exec db psql -c 'DELETE FROM users'",
        "docker --context (a remote daemon)": "docker --context prod exec db psql -c 'DELETE FROM users'",
        "DOCKER_HOST= prefix (a remote daemon)": "DOCKER_HOST=ssh://prod docker exec db psql -c 'DELETE FROM users'",
        "ssh host psql": "ssh prod psql -c 'DELETE FROM t'",
        "ssh host with a quoted remote command": "ssh -p 22 prod 'cd /srv && supabase db reset'",
        "perl alarm wrapper (the rewrite shell-mechanics-guard prescribes)":
            "perl -e 'alarm shift; exec @ARGV or die \"exec: $!\"' 600 supabase db push",
        "perl alarm wrapper around npx": "perl -e 'alarm shift; exec @ARGV' 600 npx supabase db push",
        "nice -n": "nice -n 10 supabase db push",
        "sudo -u": "sudo -u zalo supabase db push",
        "caffeinate -i -t": "caffeinate -i -t 3600 supabase db push",
        "xargs -n": "echo x | xargs -n 1 supabase db push",
        "npm run db:push": "npm run db:push",
        "pnpm run migrate:deploy": "pnpm run migrate:deploy",
        "yarn db:migrate": "yarn db:migrate",
    })
    # QA 2026-09-27 hooks round 1
    bash_writes.update({
        "--db-url from an unquoted $(...)": "supabase db push --db-url $(cat ~/.prod-db-url)",
        "psql -h from an unquoted $(...) then -c": "psql -h $(cat /tmp/host) -U postgres -c 'delete from users'",
        "psql -h from backticks then -c": "psql -h `cat /tmp/host` -c 'delete from users'",
        "a write inside an unquoted $(...)": "echo $(supabase db push)",
        "a write inside a quoted $(...)": 'echo "done: $(supabase db push)"',
        "docker run psql to a remote URL (the prescribed route, psql is not installed)":
            "docker run --rm postgres:16-alpine psql 'postgresql://postgres:pw@db.abcdefgh.supabase.co:5432/postgres' -c 'delete from users'",
        "docker run -e PGHOST= psql": "docker run --rm -e PGHOST=db.abc.supabase.co postgres:16 psql -U postgres -c 'delete from t'",
        "docker run --entrypoint psql": "docker run --rm --entrypoint psql postgres:16 -h db.abc.supabase.co -c 'delete from t'",
        "docker run psql with no host (unknown, not the local container)":
            "docker run --rm -i postgres:16 psql -U postgres -c 'delete from t'",
        "psql -c from a variable assigned a write":
            "SQL='delete from users'; psql -h db.abc.supabase.co -c \"$SQL\"",
        "psql -c from an unassigned variable": 'psql -h db.abc.supabase.co -c "$SQL"',
        "psql -c from a command substitution": 'psql -h db.abc.supabase.co -c "$(cat /tmp/fix.sql)"',
        "gunzip | psql (a restore)": "gunzip -c backup.sql.gz | psql -h db.abc.supabase.co -d postgres",
        "python | psql": "python3 gen_sql.py | psql -h db.abc.supabase.co",
        "pg_restore to a remote host": "pg_restore -h db.abc.supabase.co -d postgres --clean dump.custom",
        "supabase migration down --linked": "supabase migration down --linked",
        "supabase migration repair (remote history by default)": "supabase migration repair --status applied 20260101000000",
        "prisma db execute": "npx prisma db execute --file x.sql",
        "prisma db seed": "npx prisma db seed",
        "pnpm db:push (run-less)": "pnpm db:push",
        "supabase with two global value flags": "supabase --workdir /a --profile b db push",
        "docker exec -e PGHOST (value from the outer env)": "docker exec -e PGHOST db psql -U postgres -c 'delete from t'",
        "docker exec --env-file": "docker exec --env-file .env.prod db psql -U postgres -c 'delete from t'",
        "sudo sudo chain": "sudo sudo supabase db push",
        "a write chained after a commit heredoc with an apostrophe (QA hooks round 2)":
            "git commit -m \"$(cat <<'EOF'\nfix: Zalo's approval\nEOF\n)\" && supabase db push --linked",
        # QA 2026-09-27 hooks round 2
        "> then >> into the same file: the first heredoc cannot vouch":
            "cat > /tmp/q.sql <<'SQL'\nselect 1;\nSQL\ncat >> /tmp/q.sql <<'SQL'\ndelete from users;\nSQL\npsql -h db.abc.supabase.co -f /tmp/q.sql",
        "echo >> after the heredoc": "cat > /tmp/q.sql <<'SQL'\nselect 1;\nSQL\necho 'delete from t;' >> /tmp/q.sql; psql -h db.abc.supabase.co -f /tmp/q.sql",
        "sed -i after the heredoc": "cat > /tmp/q.sql <<'SQL'\nselect 1;\nSQL\nsed -i '' 's/select 1/delete from t/' /tmp/q.sql; psql -h db.abc.supabase.co -f /tmp/q.sql",
        "psql -f BEFORE the heredoc writes the file": "psql -h db.abc.supabase.co -f /tmp/q.sql; cat > /tmp/q.sql <<'SQL'\nselect 1;\nSQL",
        "echo $SQL | psql": 'echo "$SQL" | psql -h db.abc.supabase.co',
        "printf of $SQL | psql": "printf '%s\\n' \"$SQL\" | psql -h db.abc.supabase.co",
        "here-string from a substitution": 'psql -h db.abc.supabase.co <<< "$(cat migration.sql)"',
        "unquoted heredoc carrying $SQL": "psql -h db.abc.supabase.co <<EOF\n$SQL\nEOF",
        "psql -f a process substitution": "psql -h db.abc.supabase.co -f <(cat fix.sql)",
        "psql < a process substitution": "psql -h db.abc.supabase.co < <(cat fix.sql)",
        "a write inside a process substitution": "diff <(supabase db push) /dev/null",
        # the owner's approval cannot be minted by the run it would release
        "schedule.mjs --allow-write, even with TMUX=x in front":
            "LEASH_LANE=bg TMUX=x node ~/dev/claude-telegram-bridge/schedule.mjs update 8 --allow-write",
        "schedule.mjs add --allow-write behind env -u":
            "env -u LEASH_LANE -u LEASH_TRIGGER node schedule.mjs add daily 04:00 --run --allow-write 'x'",
        "--allow-write=true": "node ~/dev/claude-telegram-bridge/schedule.mjs update 8 --allow-write=true",
        "a redirect into bg-queue.json": "echo '[{\"text\":\"x\",\"scheduleId\":8,\"allowWrite\":true}]' > ~/dev/claude-telegram-bridge/bg-queue.json",
        "cp over schedules.json": "cp /tmp/s.json ~/dev/claude-telegram-bridge/schedules.json",
        "sed -i on schedules.json": "sed -i '' 's/\"run\": true/\"run\": true, \"allowWrite\": true/' ~/dev/claude-telegram-bridge/schedules.json",
        "sudo --user long flag": "sudo --user postgres psql -h db.abc.supabase.co -c 'delete from t'",
        "script -q FILE cmd": "script -q /dev/null supabase db push",
        "env --chdir long flag": "env --chdir /x supabase db push",
        "a psql write on the next line after that heredoc":
            "git commit -m \"$(cat <<'EOF'\nZalo's (note\nEOF\n)\"\npsql -h db.abc.supabase.co -c 'delete from t'",
        "an APPENDED heredoc cannot vouch for the file":
            "cat >> /tmp/q.sql <<'SQL'\nselect 1;\nSQL\npsql -h db.abc.supabase.co -f /tmp/q.sql",
        "a basename match does not vouch on this Mac":
            "cat > /tmp/q.sql <<'SQL'\nselect 1;\nSQL\npsql -h db.abc.supabase.co -f ~/migrations/q.sql",
    })
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
        "npm run a non-db script": "npm run build && npm run test",
        "npm run db:status is not a push": "npm run db:status",
        "npm run lint:migrations is a lint (replay FP)": "npm run lint:migrations",
        "pnpm run test:migrations": "pnpm run test:migrations",
        "docker exec psql -d a name built with $$ (replay FP)":
            'C=supabase_db_x; DB="ob_red_$$"; docker exec -i "$C" psql -U postgres -1 -d "$DB" < "$1"',
        "perl one-liner that is not a wrapper": "perl -pi -e 's/push/pull/' supabase/config.toml",
        "nice around a read": "nice -n 10 psql -h localhost -c 'select 1'",
        "ssh that only reads": "ssh prod 'psql -c \"select 1\"'",
        "npm run db:up starts a local container": "npm run db:up",
        "schedule.mjs list": "node ~/dev/claude-telegram-bridge/schedule.mjs list",
        "schedule.mjs revoking the approval": "node ~/dev/claude-telegram-bridge/schedule.mjs update 8 --allow-write false",
        "reading schedules.json": "cat ~/dev/claude-telegram-bridge/schedules.json | python3 -m json.tool",
        "a scratch schedules.json in a test dir (replay FP)":
            "cd /tmp/sched-audit && echo '{\"nextId\":0,\"items\":[]}' > schedules.json && node schedule.mjs list",
        "quoted heredoc with a literal $SQL line is literal": "psql -h db.abc.supabase.co <<'EOF'\nselect '$SQL' as x;\nEOF",
        "echo of a read into psql": "echo 'select 1' | psql -h db.abc.supabase.co",
        "echo $Q assigned a read": "Q='select 1'; echo \"$Q\" | psql -h db.abc.supabase.co",
        "diff of two process substitutions": "diff <(ls a) <(ls b)",
        "commit message heredoc in $(...) with an apostrophe and the command text":
            "git commit -m \"$(cat <<'EOF'\nfix: don't hold it\nsupabase db push\npsql -c 'delete from t'\nEOF\n)\" && echo ok",
        "unquoted commit heredoc in $(...)":
            "git commit -m $(cat <<'EOF'\nsupabase db push\nEOF\n) && echo ok",
        "a comment with an apostrophe inside $(...)": "echo $(ls # it's fine\n) && echo ok",
        "xargs grep -l psql is a grep": "cat list | xargs grep -l psql",
        "psql -c with a variable inside the SQL text": 'psql -h db.abc.supabase.co -c "select * from t where id = $ID"',
        "psql -c from a variable assigned a read": "Q='select 1'; psql -h db.abc.supabase.co -c \"$Q\"",
        "$(...) that only reads": "echo $(psql -h db.abc.supabase.co -c 'select 1')",
        "pg_restore --list only reads": "pg_restore --list dump.custom",
        "docker run of something that is not a db tool": "docker run --rm -v $PWD:/w alpine ls /w",
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
        "--db-url assigned a loopback URL in the same command":
            "L=postgresql://postgres:postgres@127.0.0.1:54322/postgres; supabase db push --db-url \"$L\"",
        "docker exec psql -d a name assigned in the same command":
            "DB=qa_rl_1; docker exec -i supabase_db_x psql -U postgres -d $DB -c 'drop table t'",
        "docker run psql to host.docker.internal (the Mac)":
            "docker run --rm postgres:16 psql -h host.docker.internal -p 54322 -U postgres -c 'delete from t'",
        "pg_restore into the local container": "docker exec -i supabase_db_x pg_restore -U postgres -d scratch < dump.custom",
        "gunzip | docker exec local psql": "gunzip -c b.sql.gz | docker exec -i supabase_db_x psql -U postgres -d scratch",
        "docker exec -e with a local PGHOST":
            "docker exec -e PGHOST=localhost db psql -U postgres -c 'delete from t'",
        "supabase db reset --linked=false": "supabase db reset --linked=false",
        "perl alarm wrapper around a local reset": "perl -e 'alarm shift; exec @ARGV' 300 supabase db reset --local",
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

    # QA 2026-09-27 hooks round 1: adversarial inputs stay fast (a hook runs
    # before every Bash call; the harness gives it 10 s and then fails open).
    import time
    slow = {
        "2,000 sudo words": "sudo " * 2000 + "supabase db push",
        "5,000 timeout 1 words": "timeout 1 " * 5000 + "supabase db push",
        "20,000 docker -e flags": "docker exec " + "-e A=1 " * 20000 + "db psql -c 'delete from t'",
        "deep $(": "echo " + "$(" * 2000 + "x" + ")" * 2000,
    }
    for label, c in slow.items():
        t0 = time.perf_counter()
        b(c)
        dt = time.perf_counter() - t0
        check(f"perf: {label} in {dt:.2f}s (< 2 s)", dt < 2.0)

    # File tools on the bridge's state files (wired on Write|Edit|MultiEdit too)
    for tool in ("Write", "Edit", "MultiEdit"):
        payload = {"tool_name": tool, "tool_input": {"file_path": "/Users/zalo/dev/claude-telegram-bridge/schedules.json"}}
        code, _ = m.decide(payload, SCHEDULE)
        check(f"{tool} on schedules.json in a scheduled run is held", code == 2)
        code, _ = m.decide(payload, {"TMUX": TMUX_VAL, "LEASH_TRIGGER": "schedule"})
        check(f"{tool} on schedules.json in tmux passes", code == 0)
    code, _ = m.decide({"tool_name": "Write", "tool_input": {"file_path": "/tmp/sched-audit/schedules.json"}}, SCHEDULE)
    check("Write to a scratch schedules.json outside the bridge passes", code == 0)
    code, _ = m.decide({"tool_name": "Write", "tool_input": {"file_path": "/tmp/notes.md"}}, SCHEDULE)
    check("Write to any other file in a scheduled run passes", code == 0)
    code, _ = m.decide({"tool_name": "Edit", "tool_input": {"file_path": "/x/bg-queue.json"}}, dict(SCHEDULE, LEASH_ALLOW_WRITE="1"))
    check("an approved run may edit the queue", code == 0)

    # The hold message makes the approval Zalo's alone.
    code, err = m.decide({"tool_name": "mcp__supabase__apply_migration", "tool_input": {"name": "x"}}, SCHEDULE)
    check("the hold message says the approval is Zalo's alone",
          code == 2 and "Only Zalo can approve it" in err and "never pass --allow-write" in err, err)

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
