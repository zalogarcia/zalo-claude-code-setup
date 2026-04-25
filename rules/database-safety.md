# Database Migration Safety

All migrations MUST be additive and non-breaking for existing users. Zero-downtime compatible.

## The Rule

**Every migration must be safe to run while the old application code is still serving traffic.** If the old code would break after the migration runs, the migration is not safe.

## Allowed (Additive / Non-Breaking)

- `CREATE TABLE` — new tables are invisible to old code
- `ADD COLUMN` with `DEFAULT` or `NULL` — old code ignores new columns
- `CREATE INDEX` (use `CONCURRENTLY` on large tables)
- `CREATE OR REPLACE FUNCTION` / `CREATE OR REPLACE VIEW`
- Add new RLS policies
- Add new enum values (`ALTER TYPE ... ADD VALUE`)
- Backfill data in new columns
- Add new triggers

## Forbidden (Breaking)

- `DROP TABLE` — unless confirmed unused by ALL application code
- `DROP COLUMN` — old code selecting `*` or naming the column will crash
- `RENAME COLUMN` / `RENAME TABLE` — breaks all existing queries referencing the old name
- `ALTER COLUMN ... SET NOT NULL` on existing column with NULLs — fails on existing data
- `ALTER COLUMN ... TYPE` (type change) — can lock table, break queries expecting old type
- Remove enum values
- Drop or modify existing RLS policies that protect user data
- `TRUNCATE` on any table with user data

## Safe Migration Pattern for Breaking Changes

If a breaking change is genuinely needed, use the expand-contract pattern across multiple deploys:

```
Deploy 1 (expand):   Add new column/table. Dual-write to both old and new.
Deploy 2 (migrate):  Backfill old data into new structure. Verify.
Deploy 3 (contract): Remove old column/table after confirming no code reads it.
```

Never combine these into a single migration. Each step must be independently deployable and rollback-safe.

## Supabase-Specific Rules

- Always use `mcp__supabase__apply_migration` or the Supabase CLI for migrations — never raw SQL execution against prod
- Test migrations on a Supabase branch first (`mcp__supabase__create_branch`) before applying to prod
- Check RLS impact: if adding/modifying RLS, verify existing users can still access their own data
- Edge Functions that depend on new columns must be deployed AFTER the migration succeeds
- Storage policies follow the same additive-only rule

## Pre-Migration Checklist

Before writing any migration:

1. `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '<table>'` — know the current schema
2. Check for existing RLS policies: `SELECT * FROM pg_policies WHERE tablename = '<table>'`
3. Check for dependent views/functions: `SELECT * FROM information_schema.view_column_usage WHERE table_name = '<table>'`
4. Estimate row count: `SELECT reltuples FROM pg_class WHERE relname = '<table>'` — large tables need `CONCURRENTLY` for indexes
5. Verify the migration is rollback-safe: "If I revert this migration, does the app still work?"

## In Autopilot Mode

When `/autopilot` generates migrations autonomously:

- Default to additive. If a breaking change seems necessary, log it to `decisions.log` and use the Tiered Decision Protocol — but the "simpler/safer" tier should almost always win (add new, don't modify old).
- Never drop or rename in autonomous mode. Period. Log it as a deferred issue for human review.
