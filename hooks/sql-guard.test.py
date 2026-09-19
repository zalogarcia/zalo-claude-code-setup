#!/usr/bin/env python3
"""Behaviour suite for sql-guard.

Run: python3 ~/.claude/hooks/sql-guard.test.py
     SQL_GUARD_HOOK=/tmp/sql-guard-v3.py python3 ~/.claude/hooks/sql-guard.test.py

sql-guard is a PreToolUse hook on mcp__supabase__execute_sql. A broken one
blocks every Supabase MCP call on this machine, so this suite must be green
before the file is installed.

The bias the suite encodes (audit 2026-08-28, P1): FALSE NEGATIVES ARE
ACCEPTABLE, FALSE POSITIVES ARE NOT. Every "allow" case below is a real query
shape that v2 wrongly blocked, or a drift shape that must never be blocked.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.environ.get("SQL_GUARD_HOOK") or os.path.expanduser("~/.claude/hooks/sql-guard.py")
REF = "abcdefghijklmnopqrst"      # a fake 20-letter project ref
OTHER_REF = "zyxwvutsrqponmlkjihg"

ALLOW, BLOCK = "allow", "block"

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


SNAPSHOT = """# SCHEMA-PROD, Production Database Snapshot

> **Generated:** {date} UTC
> **Source:** Supabase prod project `{ref}`, `public` schema

## Tables

### `tenants`

| column       | type        | null | default             |
| ------------ | ----------- | ---- | ------------------- |
| `id`         | uuid        | NO   | `gen_random_uuid()` |
| `slug`       | varchar(64) | NO   |                     |
| `created_at` | timestamptz | NO   | `now()`             |

### `tenant_contacts`

| column       | type         | null | default |
| ------------ | ------------ | ---- | ------- |
| `id`         | uuid         | NO   |         |
| `tenant_id`  | uuid         | NO   |         |
| `email`      | varchar(255) | YES  |         |
| `created_at` | timestamptz  | NO   |         |

### `agency_billable_actions`

| column        | type    | null | default |
| ------------- | ------- | ---- | ------- |
| `id`          | uuid    | NO   |         |
| `action_key`  | text    | NO   |         |
| `price_cents` | integer | NO   |         |
"""

DRIFT_NOTE = (
    "\n### Applied AFTER this snapshot was taken\n\n"
    "| Migration | Effect |\n| --- | --- |\n"
    "| `00154_tenant_contacts_notes.sql` | `tenant_contacts.notes text NULL` is "
    "live in prod but absent from the body below | \n"
)


class Env:
    """A fake machine: a dev root with repos, snapshots, and a settings file."""

    def __init__(self, repos, date="2026-08-27", settings_env=None):
        self.root = tempfile.mkdtemp(prefix="sql-guard-test-")
        _dirs.append(self.root)
        self.dev = os.path.join(self.root, "dev")
        self.state = os.path.join(self.root, "state")
        os.makedirs(self.dev, exist_ok=True)
        os.makedirs(self.state, exist_ok=True)
        for name, body in repos.items():
            d = os.path.join(self.dev, name, "docs")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "SCHEMA-PROD.md"), "w") as f:
                f.write(body if body.startswith("#") else SNAPSHOT.format(date=date, ref=body))
        self.settings = os.path.join(self.root, "settings.local.json")
        with open(self.settings, "w") as f:
            json.dump({"env": settings_env or {}}, f)

    def env(self):
        return dict(
            os.environ,
            SQL_GUARD_DEV_ROOT=self.dev,
            SQL_GUARD_SETTINGS=self.settings,
            SQL_GUARD_STATE_DIR=self.state,
        )

    def run(self, query, session="s1", project_id=REF, cwd=None, tool=None,
            event="PreToolUse", raw=None, tool_input=None):
        payload = {
            "session_id": session,
            "hook_event_name": event,
            "tool_name": tool or "mcp__supabase__execute_sql",
            "tool_input": tool_input if tool_input is not None else {
                "project_id": project_id, "query": query},
            "cwd": cwd if cwd is not None else self.dev,
        }
        p = subprocess.run(
            [sys.executable, HOOK],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, env=self.env(),
        )
        assert p.returncode in (0, 2), f"unexpected exit {p.returncode}: {p.stderr[:300]}"
        return (BLOCK if p.returncode == 2 else ALLOW), p.stdout, p.stderr

    def primed(self, session="s1", project_id=REF):
        """Satisfy the one-time schema hold so later calls exercise validation."""
        self.run("SELECT 1 FROM tenants", session=session, project_id=project_id)
        return session


def main():
    # ---------------------------------------------------------------- holds --
    e = Env({"delta-agents": REF})
    v, _, err = e.run("SELECT id FROM tenants")
    check("1a: first data query of a session is held once", v == BLOCK)
    check("1b: the hold names the snapshot", "SCHEMA-PROD.md" in err)
    v, _, _ = e.run("SELECT id FROM tenants")
    check("1c: the hold does not fire twice", v == ALLOW)

    e = Env({"delta-agents": REF})
    v, _, _ = e.run("SELECT column_name FROM information_schema.columns WHERE table_name='tenants'")
    check("2a: a catalog query is never held", v == ALLOW)
    v, _, _ = e.run("SELECT id FROM tenants")
    check("2b: a catalog query satisfies the hold for the session", v == ALLOW)

    # ------------------------------------------------------ multi-statement --
    e = Env({"delta-agents": REF}); e.primed()
    v, _, err = e.run("SELECT 1 FROM tenants; SELECT 2 FROM tenants")
    check("3a: multi-statement SQL is blocked", v == BLOCK and "multi-statement" in err)
    v, _, _ = e.run("SELECT id FROM tenants WHERE slug = 'a; b'")
    check("3b: a semicolon inside a string literal is not multi-statement", v == ALLOW)
    v, _, _ = e.run("SELECT id FROM tenants;")
    check("3c: one trailing semicolon is fine", v == ALLOW)

    # ----------------------------------------------- table validation (v2) --
    e = Env({"delta-agents": REF}); e.primed()
    v, _, err = e.run("SELECT id FROM tenatns")
    check("4a: an unknown table is blocked", v == BLOCK and "tenatns" in err)
    check("4b: the block suggests the real table", "tenants" in err)
    v, _, _ = e.run("SELECT id FROM tenants JOIN tenant_contacts ON true")
    check("4c: known tables pass", v == ALLOW)

    # --------------------------------- P1.2 — alias false positives (v2 bugs) --
    e = Env({"delta-agents": REF}); e.primed()
    alias_cases = [
        ("CTE alias", "WITH t AS (SELECT id FROM tenants) SELECT * FROM t"),
        ("CTE with a column list", "WITH t (a) AS (SELECT id FROM tenants) SELECT * FROM t"),
        ("CTE MATERIALIZED", "WITH npa AS MATERIALIZED (SELECT id FROM tenants) SELECT * FROM npa"),
        ("second CTE in a chain",
         "WITH a AS (SELECT id FROM tenants), straddle AS (SELECT id FROM a) SELECT * FROM straddle"),
        ("VALUES alias", "SELECT * FROM (VALUES (1),(2)) AS t(n) JOIN tenants ON true"),
        ("derived table alias", "SELECT * FROM (SELECT id FROM tenants) AS npa"),
        ("IS DISTINCT FROM", "SELECT id FROM tenants WHERE slug IS DISTINCT FROM created_at::text"),
        ("IS NOT DISTINCT FROM", "SELECT id FROM tenants WHERE slug IS NOT DISTINCT FROM slug"),
        ("EXTRACT(... FROM ...)", "SELECT extract(month FROM created_at) FROM tenants"),
        ("SUBSTRING(... FROM ...)", "SELECT substring(slug FROM 1 FOR 3) FROM tenants"),
        ("TRIM(both ... FROM ...)", "SELECT trim(both ' ' FROM slug) FROM tenants"),
        ("set-returning function", "SELECT * FROM unnest(ARRAY[1,2]) AS n"),
        ("schema-qualified table", "SELECT id FROM public.tenants"),
    ]
    ok = True
    for label, q in alias_cases:
        v, _, err = e.run(q)
        if v != ALLOW:
            check(f"5: alias/keyword shape allowed — {label}", False, err[:160])
            ok = False
    check("5: every CTE/VALUES/DISTINCT-FROM/EXTRACT shape is allowed (13 cases)", ok)

    # --------------------------------------- P1.1 — column validation (new) --
    e = Env({"delta-agents": REF}); e.primed()
    v, _, err = e.run("SELECT t.nonexistent_zzz FROM tenants t")
    check("6a: a qualified guessed column is blocked", v == BLOCK and "nonexistent_zzz" in err)
    check("6b: the block echoes the table's real columns", "slug" in err and "created_at" in err)

    v, _, _ = e.run("SELECT t.slug FROM tenants t")
    check("6c: a real qualified column passes", v == ALLOW)
    v, _, _ = e.run("SELECT slug, created_at FROM tenants")
    check("6d: real bare columns pass", v == ALLOW)
    v, _, err = e.run("SELECT bogus_col_xyz FROM tenants")
    check("6e: a bare guessed column is blocked in a single-table query",
          v == BLOCK and "bogus_col_xyz" in err)

    # cross-table names are NOT blocked (false-negative on purpose)
    v, _, _ = e.run("SELECT t.action_key FROM tenants t")
    check("7a: a column that exists on ANOTHER table is allowed (drift-safe)", v == ALLOW)
    e2 = Env({"delta-agents": SNAPSHOT.format(date="2026-08-27", ref=REF) + DRIFT_NOTE})
    e2.primed()
    v, _, _ = e2.run("SELECT c.notes FROM tenant_contacts c")
    check("7b: a column named only in a drift note is allowed", v == ALLOW)

    # multi-table queries: bare names are never attributed
    v, _, _ = e.run("SELECT bogus_col_xyz FROM tenants JOIN tenant_contacts ON true")
    check("7c: bare names in a multi-table query are not attributed", v == ALLOW)
    v, _, _ = e.run("WITH x AS (SELECT id FROM tenants) SELECT bogus_col_xyz FROM x")
    check("7d: bare names inside a CTE query are not attributed", v == ALLOW)

    # shapes that must not be read as columns
    for label, q in [
        ("output alias", "SELECT slug AS bogus_alias_zzz FROM tenants"),
        ("function call", "SELECT count(*) FROM tenants"),
        ("cast", "SELECT id::text FROM tenants"),
        ("json operator with a literal key", "SELECT id FROM tenants WHERE slug = 'x'"),
        ("null/boolean keywords", "SELECT id FROM tenants WHERE slug IS NOT NULL AND true"),
        ("order/limit keywords", "SELECT id FROM tenants ORDER BY created_at DESC LIMIT 10"),
        ("type name in a cast", "SELECT created_at::timestamptz FROM tenants"),
    ]:
        v, _, err = e.run(q)
        check(f"8: not a column reference — {label}", v == ALLOW, err[:160])

    # ----------------------------- P1.3 — snapshot resolution by project ref --
    e = Env({"delta-agents": REF, "other-repo": OTHER_REF})
    v, _, err = e.run("SELECT id FROM tenants", project_id=REF)
    check("9a: the hold resolves the snapshot by project ref", v == BLOCK)
    v, _, _ = e.run("SELECT id FROM tenants", project_id=REF)
    check("9b: tables of the matching snapshot pass", v == ALLOW)

    # THE 2026-08-28 BUG: a project with no snapshot must not be validated
    # against another repo's snapshot.
    e = Env({"delta-agents": REF})
    v, _, err = e.run("SELECT id FROM lessons", project_id=OTHER_REF, session="s9")
    check("10a: an unmatched project ref is held once, not validated",
          v == BLOCK and "declares project ref" in err)
    v, _, err = e.run("SELECT id FROM lessons", project_id=OTHER_REF, session="s9")
    check("10b: a table absent from ANOTHER repo's snapshot is NOT blocked",
          v == ALLOW, err[:200])
    v, _, err = e.run("SELECT anything_at_all FROM lessons", project_id=OTHER_REF, session="s9")
    check("10c: columns are not validated for an unmatched ref either", v == ALLOW, err[:200])

    # the ref may be declared via a $VAR resolved from settings.local.json
    e = Env({"delta-agents": SNAPSHOT.format(date="2026-08-27", ref="$DELTA_PROD_PROJECT_REF")},
            settings_env={"DELTA_PROD_PROJECT_REF": REF})
    e.primed()
    v, _, err = e.run("SELECT id FROM tenatns")
    check("11: a $VAR project ref resolves via settings.local.json",
          v == BLOCK and "tenatns" in err)

    # an explicit in-query hint wins
    e = Env({"delta-agents": REF, "other-repo": OTHER_REF})
    e.primed(project_id=REF)
    v, _, err = e.run("-- schema-repo: delta-agents\nSELECT id FROM tenatns", project_id=REF)
    check("12: `-- schema-repo:` hint selects the snapshot", v == BLOCK and "tenatns" in err)

    # several snapshots claim the same ref (repo + worktrees): pick one, say so
    e = Env({"delta-agents": REF, "delta-agents-wt": REF})
    v, _, err = e.run("SELECT id FROM tenants", project_id=REF)
    check("13: an ambiguous ref names the other candidates in the hold",
          v == BLOCK and "several snapshots declare" in err.lower())

    # ------------------------------------------------------ staleness hold ---
    e = Env({"delta-agents": REF}, date="2020-01-01")
    v, _, err = e.run("SELECT id FROM tenants")
    check("14: a snapshot older than 7 days holds with a staleness message",
          v == BLOCK and "days old" in err)

    # ------------------------------- P1.4 — apply_migration re-arms the hold --
    e = Env({"delta-agents": REF})
    e.primed(session="s5")
    v, out, _ = e.run("", session="s5", tool="mcp__supabase__apply_migration",
                      event="PostToolUse", tool_input={"name": "00160_add_thing"})
    check("15a: apply_migration PostToolUse exits 0 with a note",
          v == ALLOW and "SNAPSHOT NOW STALE" in out)
    check("15b: the note names the migration", "00160_add_thing" in out)
    v, _, err = e.run("SELECT id FROM tenants", session="s5")
    check("15c: the next query is held again, citing the migration",
          v == BLOCK and "migration was applied" in err)
    v, _, _ = e.run("SELECT id FROM tenants", session="s5")
    check("15d: and only once", v == ALLOW)
    v, _, _ = e.run("", session="s6", tool="mcp__supabase__apply_migration",
                    event="PreToolUse", tool_input={"name": "x"})
    check("15e: apply_migration on PreToolUse never blocks", v == ALLOW)

    # ------------------------------------------------------------ malformed --
    e = Env({"delta-agents": REF}); e.primed(session="s7")
    bad = [
        ("unparseable JSON", dict(raw='{"tool_name": ')),
        ("empty stdin", dict(raw="")),
        ("top-level list", dict(raw="[1,2,3]")),
        ("no tool_name", dict(raw=json.dumps({"tool_input": {"query": "SELECT 1"}}))),
        ("wrong tool", dict(raw=json.dumps({"tool_name": "Bash",
                                            "tool_input": {"command": "ls"}}))),
        ("tool_input is null", dict(raw=json.dumps({"tool_name": "mcp__supabase__execute_sql",
                                                    "tool_input": None}))),
        ("query is a dict", dict(session="s7", tool_input={"project_id": REF,
                                                           "query": {"a": 1}})),
        ("query missing", dict(session="s7", tool_input={"project_id": REF})),
        ("project_id is a list", dict(session="s7", tool_input={"project_id": [REF],
                                                                "query": "SELECT id FROM tenants"})),
        ("empty query", dict(session="s7", tool_input={"project_id": REF, "query": "   "})),
        ("cwd is null", dict(session="s7", cwd="")),
        # added 2026-09-19: a non-string cwd crashed the hook with TypeError
        # (exit 1) — the same class as the two AttributeErrors above, which the
        # original 11 cases did not cover.
        ("cwd is a list", dict(session="s7", cwd=["/x"])),
    ]
    ok = True
    for label, kw in bad:
        try:
            v, _, err = e.run(kw.pop("query", "SELECT id FROM tenants"), **kw)
        except AssertionError as ex:
            check(f"16: malformed — {label}", False, str(ex))
            ok = False
            continue
        if v != ALLOW:
            check(f"16: malformed — {label}", False, f"blocked: {err[:160]}")
            ok = False
    check("16: every malformed payload exits 0 and allows (12 cases)", ok)

    # a snapshot in an unreadable/garbage format must not block anything
    e = Env({"delta-agents": "# not a snapshot at all\n\njust prose, no tables\n"})
    e.run("SELECT 1 FROM tenants", project_id=REF)  # burn the hold
    v, _, err = e.run("SELECT whatever FROM made_up_table", project_id=REF)
    check("17: an unparseable snapshot validates nothing", v == ALLOW, err[:200])

    # no snapshot anywhere on the machine
    e = Env({})
    e.run("SELECT 1 FROM tenants", project_id=REF)
    v, _, err = e.run("SELECT whatever FROM made_up_table", project_id=REF)
    check("18: no snapshot at all validates nothing", v == ALLOW, err[:200])

    for d in _dirs:
        shutil.rmtree(d, ignore_errors=True)
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
