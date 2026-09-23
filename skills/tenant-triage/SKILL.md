---
name: tenant-triage
description: Evidence-first triage for "tenant X says Y broke, check why" reports on Delta Agents prod. Resolves the tenant by fuzzy slug match, time-scopes from the user's report, pulls parallel evidence (sessions, messages, voice calls + tool events, followups, alerts/audit/escalations) via the Supabase MCP, greps ECS gateway/worker logs by tenant id, correlates with recent deploys, and emits a triage summary BEFORE any hypothesis. Use for a tenant or customer complaint with a fuzzy symptom (a tenant, user or customer reports that something broke and wants to know why).
---

Turn a fuzzy customer complaint ("raqm says voice broke a couple days ago") into a grounded evidence table before anyone hypothesizes.

All SQL below uses REAL column names verified against `docs/SCHEMA-PROD.md` (in the delta-agents repo). If any query fails on a column/table name, run the `schema-snapshot` skill to refresh the snapshot — do NOT guess a replacement column.

## When to invoke

- The user relays a customer/tenant complaint: "tenant X says…", "our user at X reports…", "customer reported…", "check why X isn't getting replies".
- You have: a tenant name/slug fragment + a fuzzy symptom + (optionally) a timeframe.
- Skip for: bugs reproduced locally with a known stack trace (go straight to `/bug`), and platform-wide outages (start with `docs/RUNBOOK.md` first-5-minutes checklist instead — that's fleet-level, this is tenant-level).

## Preflight — transport check

Run `SELECT 1` via `mcp__supabase__execute_sql` (`project_id: $DELTA_PROD_PROJECT_REF`) first. If it fails, the MCP transport is down — back off and report; do not rewrite queries trying to "fix" them.

> **Resolving `$DELTA_PROD_PROJECT_REF`:** `jq -r '.env.DELTA_PROD_PROJECT_REF' ~/.claude/settings.local.json` (gitignored). Fallback: `mcp__supabase__list_projects` and pick the delta-agents prod project. Never paste the literal ref back into this file — it is committed to a public repo.

**Read-only contract: every query in this skill is a SELECT. Never write to prod during triage.**

**Caller data stays masked.** Every free-text column this skill prints (config head, last turn, contact name, message body, call summary, tool error, alert message) goes through the mask `voice-call-triage` uses: emails become `<email>`, any 10+ digit run and any US number with separators keep only the last 4 digits (`<phone ..1234>`). Ids stay whole, since the mask would corrupt uuids (its digit passes hit 152 of 1,243 address-free session keys), EXCEPT when an id carries `@`, `+<digit>`, or ends in a bare 10 to 15 digit run: a native email, SMS or WhatsApp contact's id IS its address (a WhatsApp Cloud `wa_id` is digits with no `+`), so `session_key` and the varchar `contact_id` columns get the mask behind that guard (5 of 1,248 session keys as of 2026-09-23, all `native:<tenant>:<address>`). Put the same mask on any free-text column you add; it misses emails and numbers spelled out in words, so redact those by hand before quoting.

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
SELECT id, slug, status,
       left(regexp_replace(regexp_replace(regexp_replace(config::text,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 120) AS config_head
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

Each block is one `mcp__supabase__execute_sql` call (`project_id: $DELTA_PROD_PROJECT_REF`). They are independent — run them in parallel (single message, multiple tool calls). Substitute `<tenant_id>` and the window. Skip 3c/3d when the symptom is clearly not voice; run everything else always.

**3a — Recent sessions + last-turn shape** (`conversation` is a jsonb array of turns; take the raw last element rather than guessing its keys):

```sql
SELECT CASE WHEN session_key ~ '@|\+[0-9]|(^|:)[0-9]{10,15}$' THEN regexp_replace(regexp_replace(regexp_replace(session_key,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g')
            ELSE session_key END AS session_key,
       status, channel_type, contact_id, trace_id,
       last_activity_at, jsonb_array_length(conversation) AS turns,
       left(regexp_replace(regexp_replace(regexp_replace((conversation->-1)::text,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 200) AS last_turn
FROM tenant_sessions
WHERE tenant_id = '<tenant_id>'
  AND last_activity_at >= now() - interval '72 hours'
ORDER BY last_activity_at DESC
LIMIT 20;
```

**3b — Recent messages** (did the agent actually send/receive anything?):

```sql
SELECT m.created_at, m.direction, m.channel, m.platform,
       regexp_replace(regexp_replace(regexp_replace(c.name,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g') AS contact_name,
       left(regexp_replace(regexp_replace(regexp_replace(m.body,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 160) AS body_preview
FROM tenant_messages m
JOIN tenant_contacts c ON c.id = m.contact_id
WHERE m.tenant_id = '<tenant_id>'
  AND m.created_at >= now() - interval '72 hours'
ORDER BY m.created_at DESC
LIMIT 30;
```

**3c — Voice calls** (voice symptoms only). Two engines write this table: `retell`, and `openai-live` (GPT-Live over Twilio, where `retell_call_id` holds the Twilio CallSid `CA...`). Split by engine first, then list the calls:

```sql
SELECT engine, count(*) AS calls,
       count(*) FILTER (WHERE booking_claim_unbacked)  AS unbacked_booking_claims,
       count(*) FILTER (WHERE booking_claim_unbacked IS NULL AND call_status = 'ended') AS not_audited,
       count(*) FILTER (WHERE engine = 'openai-live'
                          AND metadata->'engine_session'->>'backend_model' IS NULL) AS no_delegation
FROM tenant_voice_calls
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
GROUP BY engine;
```

```sql
SELECT engine, retell_call_id, direction, call_status, disconnection_reason,
       duration_seconds, call_successful, user_sentiment, agent_id,
       booking_claim_unbacked,
       metadata->'engine_session'->>'backend_model' AS backend_model,
       metadata->'engine_session'->>'greeting_mode' AS greeting_mode,
       started_at, ended_at,
       left(regexp_replace(regexp_replace(regexp_replace(summary,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 200) AS summary_preview
FROM tenant_voice_calls
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY created_at DESC
LIMIT 20;
```

For openai-live rows: `backend_model` null means no delegation completed (no tool could run, so any booking the agent claimed was invented); `booking_claim_unbacked` is a whole-call verdict (a booking that succeeded later in the call clears it even when the agent said "you're booked" first). For one suspicious call, run `voice-call-triage` ("openai-live calls: Steps 1L to 4L"): it reads the in-call booking guard lines from the `voice-bridge` log. These columns are newer than some checkouts' `docs/SCHEMA-PROD.md`; if sql-guard blocks one, confirm it in `information_schema.columns` and refresh the snapshot, never drop the column.

**3d — Voice tool events, failures first** (voice symptoms only; join by `retell_call_id`, there is no voice_call FK):

```sql
SELECT created_at, engine, retell_call_id, tool_name, status, duration_ms,
       regexp_replace(regexp_replace(regexp_replace(error,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g') AS error
FROM tenant_voice_tool_events
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY (error IS NOT NULL) DESC, created_at DESC
LIMIT 40;
```

**3e — Followups due/fired in window** (schedule column is `due_at`, NOT `scheduled_at`; `contact_id` here is **varchar**, not uuid — do not join `tenant_contacts` without a cast, per the 42P08 trap in SCHEMA-PROD):

```sql
SELECT id,
       CASE WHEN contact_id ~ '@|\+[0-9]|(^|:)[0-9]{10,15}$' THEN regexp_replace(regexp_replace(regexp_replace(contact_id,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g')
            ELSE contact_id END AS contact_id,
       sequence_id, step_number, due_at, status, updated_at
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
       status,
       left(regexp_replace(regexp_replace(regexp_replace(message,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 200) AS detail
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
       CASE WHEN contact_id ~ '@|\+[0-9]|(^|:)[0-9]{10,15}$' THEN regexp_replace(regexp_replace(regexp_replace(contact_id,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g')
            ELSE contact_id END AS contact_id,
       CASE WHEN session_key ~ '@|\+[0-9]|(^|:)[0-9]{10,15}$' THEN regexp_replace(regexp_replace(regexp_replace(session_key,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g')
            ELSE session_key END AS session_key
FROM tenant_escalations
WHERE tenant_id = '<tenant_id>'
  AND created_at >= now() - interval '72 hours'
ORDER BY created_at DESC
LIMIT 20;
```

Carry `trace_id` values forward — they link sessions ↔ audit rows ↔ log lines.

## Step 4 — ECS runtime logs (gateway + worker)

Log groups (from `docs/RUNBOOK.md`; `aws logs describe-log-groups --log-group-name-prefix /ecs/delta-agents` lists them): `/ecs/delta-agents/gateway`, `/ecs/delta-agents/worker`, `/ecs/delta-agents/embedding-worker`, and for openai-live voice calls `/ecs/delta-agents/voice-bridge` (its lines carry the tenant UUID as `tenantId` and the call as `metadata.callSid`). Read `~/.claude/projects/-Users-zalo-dev/memory/aws-filter-log-events-undercounts.md` before counting anything from these pulls. Logs are structured JSON containing the tenant **UUID**; webhook-ingress lines also carry the **slug** (URL path `/hooks/:crm_type/:tenant_slug`). Filter by UUID first; add a slug pass when the symptom is "messages never arrive".

Every pull goes through `pull`, which counts ALL matching events and prints a bounded slice. The old `--output text | tail -80` printed 5 "lines" for 391 events (raqm, 2026-09-23): text output joins a whole page onto one line with tabs. The slice shows ids and event names only, never message text; `/tmp/triage-<name>.json` keeps the full lines (`jq -r '.[]? | fromjson? | objects | select(.event == "<event>")'`), which are unmasked, so mask anything you quote from them.

```bash
TENANT_ID='<tenant_id>'
START=$(date -v-72H +%s)000; END=$(date +%s)000   # macOS; Linux: $(date -d '72 hours ago' +%s)000
CAP=50000   # --max-items is a safety cap; never --limit, it stops after one page

pull() {   # pull <name> <log group> <filter pattern>
  aws logs filter-log-events --region us-east-1 --log-group-name "/ecs/delta-agents/$2" \
    --filter-pattern "$3" --start-time "$START" --end-time "$END" --max-items "$CAP" \
    --query 'events[].message' --output json > "/tmp/triage-$1.json" || { echo "$1: aws failed"; return 1; }
  N=$(jq -n '[inputs | length] | add // 0' "/tmp/triage-$1.json")
  echo "== $1: $N events$([ "$N" -ge "$CAP" ] && echo ', TRUNCATED at the cap: narrow the window')"
  jq -r '.[]? | ((fromjson? | objects) // {level: "-", event: "(non-JSON line)"}) | "\(.level)\t\(.event)"' \
    "/tmp/triage-$1.json" | sort | uniq -c | sort -rn | awk '$2 != "info" || ++i <= 15'   # all warn/error names, top 15 info
  jq -r '.[]? | fromjson? | objects | [.timestamp, .level, .event, (.metadata.callSid? // .traceId // "")] | @tsv' \
    "/tmp/triage-$1.json" | sort | tail -30                           # the 30 latest
}

pull gateway gateway "\"$TENANT_ID\""                # every line naming the tenant
pull voice-bridge voice-bridge "{ \$.tenantId = \"$TENANT_ID\" && (\$.level = \"warn\" || \$.level = \"error\") }"
pull worker worker "\"$TENANT_ID\" \"error\""         # two quoted terms = AND
```

For "no reply" symptoms, also check the intentional bailed-silent paths (these are NOT bugs):

```bash
# same shell as the block above (it defines pull, START, END, CAP)
pull bailed-silent worker "{ \$.tenantId = \"$TENANT_ID\" && (\$.event = \"agent_after_hours_skip\" || \$.event = \"paused_contact_blocked\" || \$.event = \"manual_reply_cooldown_blocked\") }"
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
- Voice (3c/3d): <calls per engine (retell / openai-live); disconnection_reasons; unbacked booking claims; openai-live calls with no delegation; failed tool events: tool_name → error>
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
