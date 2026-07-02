---
name: tenant-triage
description: Evidence-first triage for "tenant X says Y broke, check why" reports on Delta Agents prod. Resolves the tenant by fuzzy slug match, time-scopes from the user's report, pulls parallel evidence (sessions, messages, voice calls + tool events, followups, alerts/audit/escalations) via the Supabase MCP, greps ECS gateway/worker logs by tenant id, correlates with recent deploys, and emits a triage summary BEFORE any hypothesis. Use when the user says "tenant … says", "our user … reports", "check why … for tenant", "customer reported", or names a tenant plus a fuzzy symptom. Encodes the intake typed 13× in 15 days.
---

Turn a fuzzy customer complaint ("raqm says voice broke a couple days ago") into a grounded evidence table before anyone hypothesizes.

All SQL below uses REAL column names verified against `docs/SCHEMA-PROD.md` (in the delta-agents repo). If any query fails on a column/table name, run the `schema-snapshot` skill to refresh the snapshot — do NOT guess a replacement column.

## When to invoke

- The user relays a customer/tenant complaint: "tenant X says…", "our user at X reports…", "customer reported…", "check why X isn't getting replies".
- You have: a tenant name/slug fragment + a fuzzy symptom + (optionally) a timeframe.
- Skip for: bugs reproduced locally with a known stack trace (go straight to `/bug`), and platform-wide outages (start with `docs/RUNBOOK.md` first-5-minutes checklist instead — that's fleet-level, this is tenant-level).

## Preflight — transport check

Run `SELECT 1` via `mcp__supabase__execute_sql` (`project_id: xbwcziymjfsobaxmanlo`) first. If it fails, the MCP transport is down — back off and report; do not rewrite queries trying to "fix" them.

**Read-only contract: every query in this skill is a SELECT. Never write to prod during triage.**

## Step 1 — Resolve the tenant (fuzzy slug match)

There is NO `tenants.name` column — the slug is the identifier; display name lives in `config` JSONB. Fuzzy-match on slug first:

```sql
SELECT id, slug, status, tenant_type, ingest_suspended, lead_recovery_suspended,
       voice_enabled, voice_outbound_enabled, created_at
FROM tenants
WHERE slug ILIKE '%<fragment>%'
ORDER BY (slug = '<fragment>') DESC, slug
LIMIT 10;
```

- **Exactly one row** → that's the tenant. Note `id` (used everywhere below) AND the posture flags: `status <> 'active'`, `ingest_suspended = true`, or a false `voice_enabled` on a voice complaint is often the entire answer — surface it immediately.
- **Multiple rows** → list the candidates (slug + status + created_at) and ask the user which one. Do not pick silently.
- **Zero rows** → fall back to the display name inside config:

```sql
SELECT id, slug, status, left(config::text, 120) AS config_head
FROM tenants
WHERE config::text ILIKE '%<fragment>%'
LIMIT 10;
```

Still zero → report "no tenant matches" with the exact fragments tried; do not proceed on a guessed id.

## Step 2 — Time-scope from the report

Convert the user's phrasing to a window; when in doubt, widen:

| User said                                | Window            |
| ---------------------------------------- | ----------------- |
| "just now" / "today"                     | 24h               |
| "yesterday"                              | 48h               |
| "a couple days ago" / no timeframe given | **72h (default)** |
| "last week" / "a while ago"              | 7d                |

Use the same window in every SQL `interval` and in the epoch-ms `--start-time` for log pulls. If Step 3 returns zero rows everywhere, double the window ONCE, then stop and report.

## Step 3 — Parallel evidence pull

Each block is one `mcp__supabase__execute_sql` call (`project_id: xbwcziymjfsobaxmanlo`). They are independent — run them in parallel (single message, multiple tool calls). Substitute `<tenant_id>` and the window. Skip 3c/3d when the symptom is clearly not voice; run everything else always.

**3a — Recent sessions + last-turn shape** (`conversation` is a jsonb array of turns; take the raw last element rather than guessing its keys):

```sql
SELECT session_key, status, channel_type, contact_id, trace_id,
       last_activity_at, jsonb_array_length(conversation) AS turns,
       left((conversation->-1)::text, 200) AS last_turn
FROM tenant_sessions
WHERE tenant_id = '<tenant_id>'
  AND last_activity_at >= now() - interval '72 hours'
ORDER BY last_activity_at DESC
LIMIT 20;
```

**3b — Recent messages** (did the agent actually send/receive anything?):

```sql
SELECT m.created_at, m.direction, m.channel, m.platform,
       c.name AS contact_name, left(m.body, 160) AS body_preview
FROM tenant_messages m
JOIN tenant_contacts c ON c.id = m.contact_id
WHERE m.tenant_id = '<tenant_id>'
  AND m.created_at >= now() - interval '72 hours'
ORDER BY m.created_at DESC
LIMIT 30;
```

**3c — Voice calls** (voice symptoms only):

```sql
SELECT retell_call_id, direction, call_status, disconnection_reason,
       duration_seconds, call_successful, user_sentiment, agent_id,
       started_at, ended_at, left(summary, 200) AS summary_preview
FROM tenant_voice_calls
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY created_at DESC
LIMIT 20;
```

**3d — Voice tool events, failures first** (voice symptoms only; join by `retell_call_id`, there is no voice_call FK):

```sql
SELECT created_at, retell_call_id, tool_name, status, error, duration_ms
FROM tenant_voice_tool_events
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY (error IS NOT NULL) DESC, created_at DESC
LIMIT 40;
```

**3e — Followups due/fired in window** (schedule column is `due_at`, NOT `scheduled_at`; `contact_id` here is **varchar**, not uuid — do not join `tenant_contacts` without a cast, per the 42P08 trap in SCHEMA-PROD):

```sql
SELECT id, contact_id, sequence_id, step_number, due_at, status, updated_at
FROM tenant_followups
WHERE tenant_id = '<tenant_id>'
  AND (due_at >= now() - interval '72 hours'
       OR updated_at >= now() - interval '72 hours')
ORDER BY due_at DESC
LIMIT 30;
```

**3f — Error-ish rows: alerts, audit trail, escalations** (audit table is `audit_log`, NOT `tenant_audit_log`):

```sql
SELECT 'alert' AS kind, created_at, alert_type AS what, severity,
       status, left(message, 200) AS detail
FROM tenant_alerts
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY created_at DESC
LIMIT 30;
```

```sql
SELECT created_at, action, resource_type, resource_id, trace_id
FROM audit_log
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY created_at DESC
LIMIT 50;
```

```sql
SELECT created_at, escalation_type, escalation_target, status,
       contact_id, session_key
FROM tenant_escalations
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY created_at DESC
LIMIT 20;
```

Carry `trace_id` values forward — they link sessions ↔ audit rows ↔ log lines.

## Step 4 — ECS runtime logs (gateway + worker)

Log groups (from `docs/RUNBOOK.md`): `/ecs/delta-agents/gateway`, `/ecs/delta-agents/worker`, `/ecs/delta-agents/embedding-worker`. Logs are structured JSON containing the tenant **UUID**; webhook-ingress lines also carry the **slug** (URL path `/hooks/:crm_type/:tenant_slug`). Filter by UUID first; add a slug pass when the symptom is "messages never arrive".

```bash
TENANT_ID='<tenant_id>'
START=$(date -v-72H +%s)000   # macOS; Linux: $(date -d '72 hours ago' +%s)000

# Gateway — all lines mentioning the tenant in the window
aws logs filter-log-events \
  --log-group-name /ecs/delta-agents/gateway \
  --filter-pattern "\"$TENANT_ID\"" \
  --start-time "$START" \
  --query 'events[].message' --output text | tail -80

# Worker — error-ish lines only (CloudWatch pattern: two quoted terms = AND)
aws logs filter-log-events \
  --log-group-name /ecs/delta-agents/worker \
  --filter-pattern "\"$TENANT_ID\" \"error\"" \
  --start-time "$START" \
  --query 'events[].message' --output text | tail -60
```

For "no reply" symptoms, also check the intentional bailed-silent paths (these are NOT bugs):

```bash
aws logs filter-log-events \
  --log-group-name /ecs/delta-agents/worker \
  --filter-pattern '?agent_after_hours_skip ?paused_contact_blocked ?manual_reply_cooldown_blocked' \
  --start-time "$START" \
  --query 'events[].message' --output text | grep "$TENANT_ID" | tail -40
```

## Step 5 — Deploy correlation

```bash
gh run list --workflow "Deploy to ECS" --limit 10 \
  --json databaseId,displayTitle,conclusion,headSha,updatedAt
```

Mark every deploy whose `updatedAt` falls inside (or just before) the symptom window. A deploy landing hours before symptom onset is the single most common root cause — but it is CORRELATION at this stage; record it as evidence, not verdict.

## Step 6 — Output contract (summary BEFORE hypothesis)

Emit this exact shape. The **Hypothesis** section must come last and must cite evidence lines above it — never lead with a theory.

```markdown
## Triage Summary — <slug> (<tenant_id>)

**Reported symptom:** <verbatim-ish>
**Window:** <e.g. 72h, 2026-06-29T14:00Z → now>
**Tenant posture:** status=<...>, voice_enabled=<...>, ingest_suspended=<...>

**Evidence:**

- Sessions (3a): <N in window; last activity; anomalies>
- Messages (3b): <in/out counts; last outbound at>
- Voice (3c/3d): <calls; disconnection_reasons; failed tool events: tool_name → error>
- Followups (3e): <due vs fired vs stuck-pending counts>
- Alerts/audit/escalations (3f): <notable rows or "clean">
- Runtime logs (4): <error lines / bailed-silent events / "clean">
- Deploys (5): <run id, sha, time, relation to symptom onset>

**What's broken (facts only):** <observable failures, quoted evidence>
**Next probe:** <the ONE cheapest check that would discriminate between causes>

---

**Hypothesis (only after the above):** <cause ranked by evidence, cite rows/lines>
```

## Anti-patterns

- ❌ **Hypothesizing before the evidence table.** The whole point is intake discipline — 13 past sessions started with a theory and paid for it.
- ❌ Guessing column names instead of using this skill's SQL / `docs/SCHEMA-PROD.md`. Known traps: no `tenants.name` (use `slug`), no `tenant_audit_log` (use `audit_log`), `tenant_followups.due_at` not `scheduled_at`, `tenant_followups.contact_id` is varchar.
- ❌ Local `psql` / pg scripts against prod — the Supabase MCP is the only sanctioned prod read path.
- ❌ Any INSERT/UPDATE/DELETE during triage. Read-only, always.
- ❌ Filtering CloudWatch by slug alone — most log lines carry the tenant UUID, not the slug.
- ❌ Silently picking one of several slug matches.
- ❌ Treating bailed-silent worker events (DND, after-hours, pause, manual-reply cooldown) as bugs — they are intentional non-reply paths.

## Edge cases

- **Ambiguous slug** → present candidates, wait for the user. (Agency setups often have `parent_tenant_id` families with similar slugs.)
- **Zero evidence in window** → widen ×2 once. Still zero → report "no evidence in window" honestly; the symptom may predate retention or belong to a different tenant.
- **Symptom contradicts posture** (voice complaint but `voice_enabled = false`; no-messages complaint but `ingest_suspended = true`) → the posture flag IS the finding; report it in the summary and stop pulling deeper evidence.
- **`tenant_followups` join needs contact names** → cast explicitly (`c.id = f.contact_id::uuid`) and expect cast failures on non-UUID external ids — prefer reporting the raw varchar id.
- **Query fails on a column this skill names** → prod schema drifted; run `schema-snapshot` to refresh, then fix the query from the new snapshot.
