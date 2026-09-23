---
name: schema-snapshot
description: 'Dump the Delta Agents production Supabase public schema (tables, columns, types, nullability, defaults, FKs, RLS flags) via the Supabase MCP and rewrite docs/SCHEMA-PROD.md with a generated-at header and drift notes. Use after applying any migration, whenever the snapshot is >7 days old, when a prod SQL query fails on a column/table name, or when the user asks to "refresh the schema snapshot". Prevents schema-guessing in ad-hoc SQL. The queries target Delta Agents prod ($DELTA_PROD_PROJECT_REF); in another repo, swap in the ref of that project first.'
---

Refresh `docs/SCHEMA-PROD.md` from the live production database so ad-hoc SQL never guesses column names again.

## When to invoke

- **Immediately after applying any migration** (`mcp__supabase__apply_migration`, `supabase db push`) — the snapshot must never lag the schema.
- The `Generated:` timestamp in `docs/SCHEMA-PROD.md` is **more than 7 days old**.
- A prod query failed with `column ... does not exist` / `relation ... does not exist` on a name the snapshot lists — the snapshot may be stale.
- The user asks to refresh/regenerate the schema snapshot.

Skip for: local-dev databases (`supabase start`), branches — this snapshot documents **prod** (`$DELTA_PROD_PROJECT_REF`) only.

> **Resolving `$DELTA_PROD_PROJECT_REF`:** `jq -r '.env.DELTA_PROD_PROJECT_REF' ~/.claude/settings.local.json` (gitignored). Fallback: `mcp__supabase__list_projects` and pick the delta-agents prod project. Never paste the literal ref back into this file — it is committed to a public repo.

## Preflight — transport check

Run `SELECT 1` via `mcp__supabase__execute_sql` first. **If `SELECT 1` fails, the MCP transport is down — back off and report; do NOT rewrite queries trying to "fix" them.** (A past session burned 21 turns misreading an MCP outage as query bugs.)

## Two read paths: the helper, or the MCP

This folder holds a helper pair from a past run. `node ~/.claude/skills/schema-snapshot/dump-catalog.cjs <dir>` reads only `SUPABASE_SESSION_POOLER_URL` from the environment (export it from `~/dev/delta-agents/.env` first), loads pg from delta-agents' `node_modules`, runs the four queries below plus a fifth for views, read-only, and writes `columns_raw.json`, `fks.json`, `rls_raw.json`, `parents.json` and `views.json` into `<dir>`. `python3 ~/.claude/skills/schema-snapshot/render_schema.py <dir> <out>` collapses the partitions and writes a whole file, but its "Includes: ... through" header line and its drift notes are hard-coded from that past run: after rendering, put back the current file's header line and carry its drift notes forward (Rendering, item 2), or the refresh silently rolls them back. Without the pooler URL or pg, run the queries below through `mcp__supabase__execute_sql`, add the fifth query from `dump-catalog.cjs` (`Q5`, views), and save the results under the same five file names.

## The queries (run all four; 1, 2, 3 are independent — run in parallel)

All via `mcp__supabase__execute_sql` with `project_id: $DELTA_PROD_PROJECT_REF`.

**Query 1 — leaf-table columns** (one aggregated row per table keeps output small):

```sql
SELECT c.table_name,
       string_agg(
         c.column_name || '|' ||
         (CASE WHEN c.data_type IN ('USER-DEFINED','ARRAY') THEN c.udt_name ELSE c.data_type END) ||
         (CASE WHEN c.character_maximum_length IS NOT NULL THEN '(' || c.character_maximum_length || ')' ELSE '' END) || '|' ||
         c.is_nullable || '|' ||
         COALESCE(c.column_default, ''),
         E'\n' ORDER BY c.ordinal_position
       ) AS cols
FROM information_schema.columns c
JOIN pg_class pc ON pc.relname = c.table_name
JOIN pg_namespace pn ON pn.oid = pc.relnamespace AND pn.nspname = 'public'
WHERE c.table_schema = 'public' AND pc.relkind = 'r'
GROUP BY c.table_name
ORDER BY c.table_name;
```

**Query 2 — foreign keys** (via `pg_constraint`, `conparentid = 0` dedupes partition copies):

```sql
SELECT conrelid::regclass::text AS table_name, pg_get_constraintdef(oid) AS fk_def
FROM pg_constraint
WHERE contype = 'f' AND connamespace = 'public'::regnamespace
  AND conparentid = 0
ORDER BY conrelid::regclass::text, conname;
```

**Query 3 — RLS flags:**

```sql
SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relname;
```

**Query 4 — partitioned parents** (Query 1's `relkind='r'` misses parents like `usage_events` / `wallet_ledger`):

```sql
SELECT c.relname AS table_name, c.relkind, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced,
       string_agg(a.attname || '|' || format_type(a.atttypid, a.atttypmod) || '|' || (CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END) || '|' || COALESCE(pg_get_expr(d.adbin, d.adrelid), ''), E'\n' ORDER BY a.attnum) AS cols
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
WHERE n.nspname = 'public' AND c.relkind = 'p'
GROUP BY c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity
ORDER BY c.relname;
```

## Rendering (rewrite the file, don't string-edit it)

Do **not** hand-transcribe 70+ tables into markdown — transcription introduces errors. Write the query results as JSON arrays to scratchpad files named as `render_schema.py` reads them (`columns_raw.json`, `fks.json`, `rls_raw.json`, `parents.json`, `views.json`), then render with the script and **Write the whole `docs/SCHEMA-PROD.md`** (never patch it with string edits).

Save every result verbatim: `render_schema.py` does the partition collapse itself (it drops the monthly leaves `usage_events_YYYY_MM` / `wallet_ledger_YYYY_MM` and takes the parents and their RLS flags from `parents.json`, Query 4).

Required output shape (match the existing file — diff-stability matters):

1. **Header block:** title, `Generated: YYYY-MM-DD HH:MM UTC`, source project id, pointer to this skill, the refresh triggers (after every migration / >7 days).
2. **"Known drift vs migrations"** section: carry forward and re-verify the notes already in the file. If the refresh reveals a prod column missing from `supabase/migrations/`, ADD it to this section.
3. **"Common wrong guesses"** table (no `agents` table → `tenant_agents`; no `tenant_audit_log` → `audit_log`; no `first_name` → `name`; `due_at` not `scheduled_at`; no `tenants.name` → `slug`; query partition parents not leaves).
4. **`contact_id` type table** — derive from the data: which tables use `uuid` vs `varchar` contact_id (the 42P08 cast trap).
5. **Per-table sections** (alphabetical): `### \`table_name\``, RLS line (`enabled (forced)`/`enabled (not forced)`), compact column table `| column | type | null | default |`(shorten`character varying`→`varchar`, `timestamp with time zone`→`timestamptz`, `character(n)`→`char(n)`, `\_text`→`text[]`), then FK list.
6. Footer: "generated file — do not hand-edit; refresh via `schema-snapshot`".

The render script lives beside this file: `render_schema.py <dir> <out>`. It prints `Wrote <out>: <N> tables, <M> FKs, <V> view(s)`.

## Verify (per ~/.claude/rules/gates.md — show evidence in the same turn)

- Script prints `Wrote docs/SCHEMA-PROD.md: <N> tables, <M> FKs, <V> view(s)`; N and M should be at or near the counts in the previous snapshot's header. A sudden large drop means a query silently returned partial data: investigate, don't ship.
- `grep -c '^### ' docs/SCHEMA-PROD.md` equals N + V (each view also gets a `###` heading).
- Spot-check one recently-migrated table's new column appears.

## Anti-patterns

- ❌ **`information_schema` join for FKs** (`table_constraints` × `key_column_usage` × `constraint_column_usage`) — fans out across partitions to megabytes of output and blows the MCP result cap. Use `pg_constraint` with `conparentid = 0` (Query 2).
- ❌ Editing individual table sections in place — always regenerate the whole file. Partial edits rot.
- ❌ Running the dump against a Supabase **branch** and labeling it prod.
- ❌ Retrying/rewriting queries when `SELECT 1` already failed — that's a transport outage, not a SQL bug.
- ❌ Hand-writing the markdown tables from memory of the query output — transcribe to JSON verbatim, render mechanically.
- ❌ Ad-hoc `psql` or hand-written pg scripts against prod. The two sanctioned read paths are `dump-catalog.cjs` (read-only catalog queries over the session pooler) and the Supabase MCP.

## Edge cases

- **New partitioned table appears:** Query 4 catches the parent; extend the partition-collapse regex for its leaf naming pattern.
- **Output exceeds MCP result cap anyway** (schema doubled): split Query 1 with `WHERE c.table_name < 'tenant_m'` / `>= 'tenant_m'` halves and merge the JSON.
- **Views:** the helper's fifth query dumps them (`relkind = 'v'`, with `security_invoker`), and `render_schema.py` writes them in their own Views section. Materialized views are not covered.
