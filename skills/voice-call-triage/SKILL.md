---
name: voice-call-triage
description: Triage one voice call (or "the last call") on Delta Agents prod — pull the tenant_voice_calls row (status/duration/disconnection reason), the tenant_voice_tool_events timeline, the gateway ECS log window around the call, and a DA-intended vs Retell-actual config diff via the Retell GET endpoints; for GPT-Live (engine openai-live) calls, the Twilio CallSid path instead: engine session, voice-bridge and gateway logs, the in-call booking guard. Use when a specific voice call misbehaved (hung up, never connected, did the wrong thing) or the user names a phone number with a call symptom.
---

Triage a single Delta Agents voice call end-to-end: DB evidence → tool timeline → gateway logs → config diff. Collect all four evidence layers before hypothesizing: past 20-iteration debugging loops came from fixing the first plausible theory instead of reading the second evidence layer.

Repo root assumed at `/Users/zalo/dev/delta-agents` (adjust if the checkout lives elsewhere). All prod reads go through the Supabase MCP (`mcp__supabase__execute_sql`, project `$DELTA_PROD_PROJECT_REF`) — never local `psql`. Column names below are verified against `docs/SCHEMA-PROD.md`; re-check there before editing any query.

> **Resolving `$DELTA_PROD_PROJECT_REF`:** `jq -r '.env.DELTA_PROD_PROJECT_REF' ~/.claude/settings.local.json` (gitignored). Fallback: `mcp__supabase__list_projects` and pick the delta-agents prod project. Never paste the literal ref back into this file — it is committed to a public repo.

## When to invoke

- "it hung up" / "the call cut off" / "call didn't work" / "caller just heard ringing"
- "check the last call" / "why did the voice agent do X on that call"
- A tenant reports a voice symptom with a phone number or a call time.
- After a Retell sync change, to confirm what the live agent actually runs.

For a FUZZY tenant symptom that is not call-shaped ("tenant X says things broke"), use the `tenant-triage` skill instead — this skill assumes the symptom is a specific call/agent.

## Inputs

Tenant (slug or id) + agent (name or id), **or** a phone number, **or** a Retell call id, **or** a Twilio CallSid (`CA...`, an openai-live call). Optional: a time window ("yesterday afternoon").

## Preflight

`SELECT 1` via `mcp__supabase__execute_sql`. If it fails, the MCP transport is down — back off and report; do NOT rewrite queries.

## Step 0 — resolve ids

```sql
-- tenant (no tenants.name column — slug only):
SELECT id, slug, status FROM tenants WHERE slug ILIKE '%<fragment>%';

-- voice agent + its stored Retell linkage (config.voice.retell):
SELECT id, name, slug, is_active,
       config->'voice'->'retell'->>'agentId'          AS retell_agent_id,
       config->'voice'->'retell'->>'llmId'            AS retell_llm_id,
       config->'voice'->'retell'->>'publishedVersion' AS published_version,
       config->'voice'->'retell'->>'lastSyncedAt'     AS last_synced_at,
       config->'voice'->'retell'->>'apiKeyRef'        AS api_key_ref,
       config->'voice'->>'inboundPhoneNumber'         AS inbound_phone_number,
       config->'voice'->>'phoneNumberDirection'       AS phone_direction
FROM tenant_agents
WHERE tenant_id = '<tenant_id>'::uuid
  AND config->>'modality' = 'voice'
  AND (name ILIKE '%<fragment>%' OR id::text = '<agent_id>');
```

From a phone number instead (checks BOTH the single-number field and the multi-number `numbers[]` array):

```sql
SELECT id, name FROM tenant_agents
WHERE config->>'modality' = 'voice'
  AND (config->'voice'->>'inboundPhoneNumber' = '<+E164>'
       OR config->'voice'->'numbers' @> '[{"number":"<+E164>"}]'::jsonb);
```

## Step 1 — the call row(s)

`tenant_voice_calls` real columns: `retell_call_id` (varchar), `direction`, `from_number`, `to_number`, `call_status`, `disconnection_reason`, `duration_seconds`, `call_successful`, `user_sentiment`, `transfer_target_agent_id`, `started_at`, `ended_at`, `summary`, `transcript`, `metadata`. (`contact_id`/`agent_id` are uuid: cast comparisons `::uuid`.)

Both this table and `tenant_voice_tool_events` also carry an `engine` column: `retell` (the default) or `openai-live` (GPT-Live over Twilio). **Read it first. `retell` continues with Steps 2 to 4 below. `openai-live` goes to "openai-live calls: Steps 1L to 4L" further down, which replaces Steps 2 to 4 (there is no Retell config to diff).**

```sql
SELECT id, engine, retell_call_id, direction, from_number, to_number,
       call_status, disconnection_reason, duration_seconds,
       call_successful, user_sentiment, transfer_target_agent_id,
       started_at, ended_at, created_at, left(summary, 300) AS summary
FROM tenant_voice_calls
WHERE tenant_id = '<tenant_id>'::uuid
  AND agent_id = '<agent_id>'::uuid          -- drop this line when searching by number/time
ORDER BY created_at DESC
LIMIT 5;
```

Read `transcript` in a second query only for the one call under triage (it's large).

Interpretation:

| Observation                                         | Meaning                                                                                                                                                                                                                                                                                                                                                                                           |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No row for the call time at all**                 | The post-call webhook never arrived — stale/absent `webhook_url` token (grep `retell_postcall_auth_failed`), relative URL (`GATEWAY_URL` unset), or the call never connected. Go straight to Steps 3–4.                                                                                                                                                                                           |
| `call_status`                                       | Retell passthrough: `registered` / `ongoing` / `ended` / `error`.                                                                                                                                                                                                                                                                                                                                 |
| `disconnection_reason`                              | Retell passthrough. Hang-up class: `user_hangup`, `agent_hangup`, `call_transfer`, `voicemail_reached`, `inactivity`, `max_duration_reached`. No-connect class: `dial_no_answer`, `dial_busy`, `dial_failed`, `concurrency_limit_reached`. Platform-fault class: `error_*` (e.g. `error_llm_websocket_open`, `error_inbound_webhook`) — these are Retell-side/config faults, not caller behavior. |
| `call_successful`                                   | Retell's post-call analysis verdict (nullable — absent until analysis lands).                                                                                                                                                                                                                                                                                                                     |
| Row exists but `duration_seconds = 0` / thin fields | A "thin row" persisted at call start (`retell_postcall_thin_row_persisted`) that was never enriched — the `call_analyzed` webhook didn't arrive or failed (`retell_postcall_persist_failed`).                                                                                                                                                                                                     |

## Step 2 — tool-events timeline

`tenant_voice_tool_events` is keyed by `retell_call_id` (NOT the local call uuid): `tool_name`, `arguments`, `response`, `status` (varchar(10)), `error`, `duration_ms`, `created_at`.

```sql
SELECT created_at, tool_name, status, duration_ms, error,
       left(arguments::text, 200) AS args, left(response::text, 200) AS resp
FROM tenant_voice_tool_events
WHERE tenant_id = '<tenant_id>'::uuid
  AND retell_call_id = '<retell_call_id>'
ORDER BY created_at ASC;
```

- **Zero events on a phone call where tools were expected** → the MCP server wasn't attached (no token, or zero resolved tools ⇒ `mapper.ts:buildMcps` emits `[]`) or MCP auth failed — check Step 3 for `voice_mcp_auth_failed` and Step 4 for the `mcps[]` entry.
- **Zero events on a web/orb test call is NORMAL** — `{{call_id}}` isn't populated there, so events simply aren't written.
- Same data in the product UI: Contacts → contact → Calls tab → expand call → "Tool activity"; API: `GET /admin/tenants/:tid/voice/calls/:localCallId/events` (local uuid — the route translates to `retell_call_id`).

## Step 3 — gateway log window

Voice runs gateway-side (inbound webhook, MCP tools, post-call). Log group per `docs/RUNBOOK.md`: **`/ecs/delta-agents/gateway`** (worker `/ecs/delta-agents/worker` is NOT in the voice path).

```bash
# window = started_at − 2min … ended_at + 2min, in epoch ms
aws logs filter-log-events \
  --log-group-name /ecs/delta-agents/gateway \
  --start-time <start_ms> --end-time <end_ms> \
  --filter-pattern '"<retell_call_id>"' \
  --query 'events[].message' --output text

# second pass — lifecycle events for the same window (any-term match):
aws logs filter-log-events \
  --log-group-name /ecs/delta-agents/gateway \
  --start-time <start_ms> --end-time <end_ms> \
  --filter-pattern '?retell_inbound ?retell_postcall ?voice_mcp ?da_context ?voice_sync ?retell_config_validation' \
  --query 'events[].message' --output text
```

Event cheat-sheet (all real `logger.*` event names):

| Phase                | Healthy                                                                                                    | Broken                                                                                                                                                                     |
| -------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Inbound pre-call     | `retell_inbound_received` → `retell_inbound_contact` → `da_context_assembled` → `retell_inbound_responded` | `retell_inbound_auth_failed` (stale URL token → Retell retries → caller hears ringing), `retell_inbound_not_entitled`, `da_context_assemble_timeout`                       |
| In-call tools        | `voice_mcp_auth_ok`, `voice_mcp_tool_call`                                                                 | `voice_mcp_auth_failed`, `voice_mcp_context_unavailable`, `voice_mcp_tool_skipped_missing_integration`                                                                     |
| Post-call            | `retell_postcall_received` → `retell_postcall_enriched`                                                    | `retell_postcall_auth_failed`, `retell_postcall_persist_failed`, `retell_postcall_ignored`                                                                                 |
| Sync (config pushes) | `voice_sync_pushed`, `voice_agent_published`, `voice_phone_bound`                                          | `voice_sync_failed`, `voice_publish_failed`, `voice_phone_bind_failed`, `voice_webhook_token_mismatch`, `voice_sync_stale_agent_recreated`, **`retell_config_validation`** |

`retell_config_validation` is the log-only pre-push validator (`apps/gateway/src/retell-sync/config-validator.ts`) — its `findings[].code` values (`mcp_server_no_tools`, `agent_name_missing`, `stale_prompt_prefix`, `da_context_block_missing/_duplicated`, `knowledge_base_ids_nonempty/_missing`, `stale_agent_id_shape`, `stale_llm_id_shape`, `mcp_url_not_absolute`, `webhook_url_not_absolute`) name the exact known-breaking shape that was about to be pushed. If one fired near the call time, that IS the lead.

## Step 4 — DA-intended vs Retell-actual config diff

**Intended** (derived from `tenant_agents.config` by `apps/gateway/src/retell-sync/mapper.ts`):

- `general_prompt` = `config.soul` (legacy `# Voice Agent Operating Rules … --- IDENTITY ---` scaffold stripped) + exactly ONE `## Live context for this call\n{{da_context}}` block (`composeVoicePrompt`).
- `knowledge_base_ids` = `[]` ALWAYS (DA KB uuids are never Retell KB ids — forwarding them 404s every sync).
- `agent_name` = `tenant_agents.name`.
- `mcps[]` = one `delta-voice` entry with url `${GATEWAY_URL}/voice/mcp/{tenantId}/{agentId}` **iff** the webhook token resolved AND ≥1 tool resolved; each tool also declared as a `type:"mcp"` `general_tools` entry.
- `webhook_url` = `${GATEWAY_URL}/voice/retell/post-call/{tenantId}/{agentId}/<token>` (token = final path segment).
- `voice_id`/`language`/`model` etc. pass through from `config.voice.*` (s2s model excludes `model`/`model_high_priority`).

**Actual — path A (preferred, no key handling):** gateway admin proxy, superadmin Bearer from the repo `.env` `ADMIN_API_KEY` (matches the prod ECS secret — read into a shell var, never echo):

```bash
curl -s "https://api.operatorbase.app/admin/tenants/$TENANT_ID/agents/$AGENT_ID/voice/versions" \
  -H "Authorization: Bearer $ADMIN_API_KEY" | jq '.versions[] | {version, is_published, is_current, agent_name}'
# field-level diff of one version vs its predecessor (includes LLM prompt/tools edits):
curl -s ".../voice/versions/<version>/diff" -H "Authorization: Bearer $ADMIN_API_KEY" | jq .
```

**Actual — path B (direct Retell probe).** The tenant's Retell key is NEVER hardcoded — the gateway resolves it (`apps/gateway/src/retell-sync/_shared.ts:resolveRetellKey`) from `tenant_api_keys` where `id = config.voice.retell.apiKeyRef AND provider = 'retell'` (empty `apiKeyRef` ⇒ first `provider='retell'` row by `created_at`). `encrypted_key` is bytea AES-256-GCM (12-byte IV + 16-byte tag + ciphertext), decrypted with the 64-hex `ENCRYPTION_KEY` by `packages/providers/src/config-provider.ts:decryptKey`. Reproduce exactly that:

```sql
SELECT encode(encrypted_key, 'hex') AS enc_hex, key_hint
FROM tenant_api_keys
WHERE tenant_id = '<tenant_id>'::uuid AND provider = 'retell'
  AND (id = '<api_key_ref>'::uuid OR '<api_key_ref>' = '')
ORDER BY created_at LIMIT 1;
```

```bash
cd /Users/zalo/dev/delta-agents   # ENCRYPTION_KEY in .env matches prod
RETELL_KEY=$(node --env-file=.env --input-type=module -e '
  const {decryptKey}=await import("./packages/providers/dist/config-provider.js");
  console.log(decryptKey(Buffer.from(process.argv[1],"hex")));' -- "<enc_hex>")

# Retell GETs (base https://api.retellai.com, header Authorization: Bearer):
curl -s "https://api.retellai.com/get-agent/$RETELL_AGENT_ID" \
  -H "Authorization: Bearer $RETELL_KEY" \
  | jq '{agent_name, version, is_published, voice_id, language, webhook_url, response_engine}'
curl -s "https://api.retellai.com/get-retell-llm/$RETELL_LLM_ID" \
  -H "Authorization: Bearer $RETELL_KEY" \
  | jq '{model, s2s_model, knowledge_base_ids, prompt_head: (.general_prompt|.[0:300]),
         da_context_count: ([.general_prompt | scan("\\{\\{da_context\\}\\}")] | length),
         mcp_servers: [.mcps[]? | {name, url}],
         mcp_tool_decls: [.general_tools[]? | select(.type=="mcp") | .name]}'
curl -s "https://api.retellai.com/list-phone-numbers" \
  -H "Authorization: Bearer $RETELL_KEY" \
  | jq '.[] | select(.phone_number=="<+E164>") | {phone_number, inbound_agents, outbound_agents, inbound_webhook_url}'
unset RETELL_KEY
```

Diff checklist (each mismatch is a concrete root-cause candidate):

1. `agent_name` ≠ `tenant_agents.name` → rename never propagated (sync failing).
2. `general_prompt` doesn't start with the operator's `soul`, or `da_context_count ≠ 1` → prompt regression (stale scaffold / double-stacked block).
3. `knowledge_base_ids ≠ []` → the 404 gotcha; every subsequent sync silently fails.
4. `mcp_servers` empty while the agent has tools enabled → in-call tools invisible (matches empty Step-2 timeline).
5. `is_published: false` on the latest version (or `publishedVersion` stale in config) → inbound callers hear ringing / run stale config.
6. Phone number's `inbound_webhook_url` token segment ≠ current agent token, or `inbound_agents` points at a different `agent_id` → inbound 401s / wrong agent answers.
7. `webhook_url` or `mcps[].url` not absolute `https://` → `GATEWAY_URL` regression.

## openai-live calls (GPT-Live): Steps 1L to 4L

For a row with `engine = 'openai-live'` these steps replace Steps 2 to 4. The call ran on Twilio media streams through the gateway and the `voice-bridge` ECS service, so there is **no Retell config to diff: skip Step 4 entirely.** Code of record (delta-agents `origin/main`): `apps/gateway/src/voice-live/` (webhook, bootstrap, persist, terminal consumer), `apps/voice-bridge/src/` (the live session), `apps/gateway/src/retell-webhooks/booking-claim-audit.ts` (the post-call booking audit, shared by both engines).

**Identifiers.** The Twilio CallSid (`CA...`) is the call id everywhere: `tenant_voice_calls.retell_call_id` AND `twilio_call_sid` both hold it, `tenant_voice_tool_events.retell_call_id` holds it (join on that, never on a `call_id` column, there is none), and log lines carry it as `metadata.callSid`.

**Before the first query:** these columns (`engine`, `twilio_call_sid`, `booking_claim_unbacked`, `booking_claim_detail`) are newer than some checkouts' `docs/SCHEMA-PROD.md`, and sql-guard blocks a column its snapshot lacks. Confirm with `SELECT column_name FROM information_schema.columns WHERE table_name = 'tenant_voice_calls'` (catalog queries always pass), then run the triage from a checkout whose snapshot is current, or refresh it with the `schema-snapshot` skill. Never drop the column from the query to get past the guard.

### Step 1L: the call row and the engine session

```sql
SELECT c.id, c.tenant_id, c.agent_id, c.engine, c.retell_call_id, c.twilio_call_sid, c.direction,
       right(c.from_number, 4) AS from_last4, right(c.to_number, 4) AS to_last4,
       c.call_status, c.disconnection_reason, c.duration_seconds,
       c.started_at, c.ended_at, c.analyzed_at,
       c.booking_claim_unbacked, c.booking_claim_detail,
       c.metadata->'engine_session'->>'backend_model'     AS backend_model,
       c.metadata->'engine_session'->>'tool_calls_count'  AS tool_calls_count,
       c.metadata->'engine_session'->>'close_reason'      AS close_reason,
       c.metadata->'engine_session'->>'greeting_mode'     AS greeting_mode,
       c.metadata->'engine_session'->>'greeting_heard_ms' AS greeting_heard_ms,
       c.metadata->'engine_session'->>'finalized_by'      AS finalized_by,
       c.metadata->'engine_session'->>'post_call_done_at' AS post_call_done_at,
       -- the mask (also used in Step 2L): emails, then any 10+ digit run, then a US number with separators
       left(regexp_replace(regexp_replace(regexp_replace(c.summary,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 300) AS summary
FROM tenant_voice_calls c
WHERE c.retell_call_id = '<CallSid>' OR c.twilio_call_sid = '<CallSid>';
```

Then the transcript as numbered turns (one `Agent: ...` or `User: ...` line per turn; the stored text has NO timestamps, so ordering against tools comes from Step 3L's logs). Callers SPELL their email and number aloud ("rose organics three at gmail dot com"), which no regex masks: redact those turns by hand before quoting them in any report (last 4 digits of a phone at most).

```sql
SELECT n AS turn, left(line, 240) AS line
FROM tenant_voice_calls c,
     LATERAL unnest(string_to_array(c.transcript, E'\n')) WITH ORDINALITY AS u(line, n)
WHERE c.tenant_id = '<tenant_id>'::uuid AND c.retell_call_id = '<CallSid>' AND line <> ''
ORDER BY n;
```

| Observation | Meaning |
| --- | --- |
| `call_status = 'ongoing'` long after the call, no `post_call_done_at` | The terminal job never landed. The reconcile sweep later writes `disconnection_reason = 'error_session_missing_terminal'` with `finalized_by = 'sweep'`. Go to Step 3L for `voice_live_terminal_*` lines. |
| `finalized_by` set (`stream_status`, `status_callback`, `amd_callback`, `amd`, `tenant_cap_busy`, `sweep`) | The row was closed by a Twilio callback or the sweep, not by the terminal job. |
| `disconnection_reason` | Mapped from the bridge's close reason (`VOICE_LIVE_DISCONNECTION_REASON_BY_CLOSE` in `packages/contracts/src/voice-live.ts`): `remote_hangup` gives `user_hangup`, `connection_lost` gives `error_connection_lost`. Compare with `close_reason`. |
| `backend_model` null (with `tool_calls_count` 0 or null) | No delegation completed: the realtime model never handed work to the backend model, so no tool could run. Every booking or lookup the agent claimed on that call was invented. |
| `greeting_mode` | `clip` (pre-recorded greeting played), `commentary`, or `none`. `none` on a call that should have greeted pairs with the `voice_live_greeting_clip_missing` alert (Step 4L). |
| `booking_claim_unbacked` | NULL: never audited (an empty transcript returns before the audit writes). `false`: audited, nothing reportable. `true`: the agent claimed or promised a booking with no backing tool; `booking_claim_detail` has `{kind, phrase, utterance, turnIndex, verdict}`. **It is a whole-call verdict**: a booking tool that succeeds LATER in the call makes it `false` even when the agent told the caller "you're booked" before any booking existed. Ordering is only visible in Step 3L. |

### Step 2L: tool events

```sql
SELECT created_at, engine, tool_name, status, duration_ms, error,
       left(regexp_replace(regexp_replace(regexp_replace(arguments::text,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 220) AS args,
       left(regexp_replace(regexp_replace(regexp_replace(response::text,
              '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+', '<email>', 'g'),
              '\+?[0-9]{6,}([0-9]{4})', '<phone ..\1>', 'g'),
              '(\+?1[-. ]*)?\(?[0-9]{3}\)?[-. ]*[0-9]{3}[-. ]*([0-9]{4})', '<phone ..\2>', 'g'), 260) AS resp,
       response->>'appointmentId' AS appointment_id
FROM tenant_voice_tool_events
WHERE tenant_id = '<tenant_id>'::uuid AND retell_call_id = '<CallSid>'
ORDER BY created_at ASC;
```

- `status` is `ok` or `error`; a guard block is stored as an `error` of `blocked_by_guard`. Tool names carry family prefixes (`get_slots_<calendar>`, `book_appointment_<calendar>`, `update_contact`, `get_contact`, `send_message_to_human`, `schedule_/update_/cancel_followup`, `create_task`).
- A `book_appointment_*` row with `status = 'ok'` and an `appointmentId` in the response is the only proof a booking exists. Read the response's `warning` too (for example "Booked, but this contact has no email on file").
- **Never written as rows:** `end_call` and `transfer_call_*` (they run inside the bridge), `backend_timeout` and `session_closed_before_result`, and the calendar prefetch. Those appear only in Step 3L's logs.
- Zero rows with `backend_model` null in Step 1L: no delegation, see above.

### Step 3L: gateway and voice-bridge logs, by CallSid

Two log groups (checked with `aws logs describe-log-groups --log-group-name-prefix /ecs/delta-agents`): `/ecs/delta-agents/gateway` and `/ecs/delta-agents/voice-bridge`, region `us-east-1`. Read `~/.claude/projects/-Users-zalo-dev/memory/aws-filter-log-events-undercounts.md` first: no `--limit` (it kills pagination), `--output json` piped through `jq -r '.[]?'` (text output tab-joins a page onto one line), and compare `wc -c` with `wc -l` before trusting a count.

```bash
SID='<CallSid>'
START=<started_at - 2 min, epoch ms>; END=<ended_at + 5 min, epoch ms>   # post-call analysis lands ~5 s after hangup
for G in voice-bridge gateway; do
  aws logs filter-log-events --region us-east-1 --log-group-name /ecs/delta-agents/$G \
    --start-time "$START" --end-time "$END" --filter-pattern "\"$SID\"" --max-items 20000 \
    --query 'events[].message' --output json | jq -r '.[]?' > /tmp/call-$G.jsonl
  echo "$G lines=$(wc -l < /tmp/call-$G.jsonl) bytes=$(wc -c < /tmp/call-$G.jsonl)"
  jq -r '[.timestamp, .level, .event] | @tsv' /tmp/call-$G.jsonl | sort
done
```

Lines are JSON with `event`, `level`, `component` and `metadata.callSid`. Three exceptions: the bridge's `voice_live_tool_call` also has `metadata.callId`, which is the OpenAI function call id, not the CallSid; the post-call booking audit lines put the CallSid in `metadata.callId`; the gateway's `voice_mcp_tool_call` carries no call id, so it does not match a CallSid filter.

| Phase | Healthy | Broken |
| --- | --- | --- |
| Call start (gateway) | `voice_live_webhook_received`, `voice_live_thin_row_persisted`, `voice_live_twiml_served`, `voice_live_greeting_clip`, `voice_live_bootstrap_ok`, `voice_live_context_built` | `voice_live_rejected_*`, `voice_live_bootstrap_failed`, `voice_live_greeting_no_clip` (error) |
| Session (bridge) | `voice_live_stream_started`, `voice_live_greeting_mode`, `voice_live_greeting_heard`, `voice_live_session_started`, `voice_live_first_output` | `voice_live_session_refused`, `voice_live_greeting_not_spoken`, `voice_live_openai_auth_failed`, `voice_live_openai_connect_failed`, `voice_live_session_error` |
| Tools (bridge) | `voice_live_backend_usage`, `voice_live_mcp_call`, `voice_live_tool_call` (`metadata.tool`, `status`), `voice_live_tool_result_sent` | `voice_live_mcp_call_failed`, `voice_live_backend_timeout` |
| Booking guard (bridge, in call) | `voice_live_booking_ready_nudge`, `voice_live_booking_claim_backed` | **`voice_live_booking_claim_unbacked` / `voice_live_booking_promise_unbacked`** (warn; `metadata.phrase`, `resolvedBy`), then `voice_live_guard_silence_break` |
| Call end | `voice_live_twilio_stream_ended`, `voice_live_session_closed`, `voice_live_terminal_enqueued` (bridge); `voice_live_stream_status`, `voice_live_status_callback` (gateway) | `voice_live_terminal_handoff_failed` |
| Post-call (gateway) | `voice_live_analysis_done`, `voice_live_terminal_consumed`, `voice_live_recording_stored` | `voice_live_terminal_rejected`, `_row_missing`, `_post_call_failed`, `voice_live_analysis_failed`, `voice_live_postcall_booking_claim_unbacked` / `_promise_unbacked`, `voice_live_postcall_booking_no_backend` |

**The premature booking claim.** Put the bridge's `voice_live_booking_claim_unbacked` timestamp next to the `book_appointment_*` row from Step 2L. A claim logged BEFORE the booking tool's `created_at` means the caller heard "you're booked" before the booking existed, and Step 1L's `booking_claim_unbacked = false` does not clear it (the later booking backed the call as a whole). Find the matching turn in the numbered transcript by the logged `phrase`.

### Step 4L: alerts for the call

```sql
SELECT created_at, alert_type, severity, status, notification_sent, left(message, 200) AS message,
       coalesce(metadata->>'callSid', metadata->>'providerCallId') AS call_sid
FROM tenant_alerts
WHERE tenant_id = '<tenant_id>'::uuid
  AND created_at BETWEEN '<started_at>'::timestamptz - interval '5 minutes'
                     AND '<ended_at>'::timestamptz + interval '1 hour'
  AND (alert_type LIKE 'voice_live_%' OR alert_type LIKE 'voice_booking_%')
ORDER BY created_at;
```

- `voice_live_greeting_clip_missing` (tenant alert, `warning`, `metadata {agentId, callSid, reason}`): the bootstrap had no greeting clip. Throttled to once per tenant per UTC day, so a missing row on a second call that day proves nothing; the gateway's `voice_live_greeting_no_clip` error line is per call.
- `voice_booking_claim_unbacked` / `voice_booking_promise_unbacked` (tenant alerts, throttled per tenant per day): raised by the post-call audit when Step 1L's flag is `true`. Their metadata names the call as `providerCallId` (the CallSid) and `voiceCallId`, plus `engine`, `phrase`, `utterance` and `verdict`; `notification_sent = false` means nobody was told.
- `voice_live_postcall_booking_no_backend` is NOT a tenant alert: it is a gateway `logger.error` line plus one ops Slack message per call (deduped by Redis key `voice:booking_no_backend:<CallSid>` for 7 days). It fires when an openai-live call had a reportable claim or promise and ZERO tool events. Look for it in Step 3L's gateway pull (its CallSid is in `metadata.callId`).

## Output — correlation summary FIRST

Emit a short timeline (call start → inbound webhook → tool events → disconnect → post-call; for openai-live also the bridge's booking guard lines, placed against the tool events), the disconnection reason class, and which of the four evidence layers contains the anomaly — THEN the hypothesis and fix. If all four layers are clean, say so and widen the time window before theorizing.

## Verify (per ~/.claude/rules/gates.md)

- Every table/column used above greps in `docs/SCHEMA-PROD.md` (refresh via `schema-snapshot` if a query 42703s).
- The root cause must be backed by a quoted log line, SQL row, or config-diff mismatch — never "probably".

## Anti-patterns

- ❌ Hypothesizing after only the call row — the 20-iteration loops all started this way. Pull all four layers first.
- ❌ Guessing column names (`scheduled_at`, `agents`, `tenants.name`) — read `docs/SCHEMA-PROD.md`.
- ❌ Local `psql`/pg scripts against prod — Supabase MCP only.
- ❌ Echoing/logging the decrypted Retell key, the `Authorization` header, or the tokened `webhook_url` — key_hint is the only safe identifier to show. `unset RETELL_KEY` when done.
- ❌ Hardcoding any Retell key — always resolve via `apiKeyRef` → `tenant_api_keys` as above.
- ❌ Treating zero tool events on a WEB/orb test call as a bug (`{{call_id}}` absent there by design).
- ❌ Grepping `/ecs/delta-agents/worker` for voice. Retell calls are gateway-only; openai-live calls are gateway plus `/ecs/delta-agents/voice-bridge`.
- ❌ Running the Retell config diff (Step 4) on an openai-live call, or reading `booking_claim_unbacked = false` as "the agent never claimed a booking early" (it is a whole-call verdict; the bridge's guard line has the order).
- ❌ Pasting a caller's email or phone into a report. Show the last 4 digits; the transcript spells emails out in words, so mask those too.

## Edge cases

- **Multi-language agents:** the sibling locale agents have their OWN Retell agent/LLM ids in `config.voice.multiLanguage.agents` — a call answered post-swap runs the SIBLING's config; diff that one, not the main.
- **Transferred calls:** `transfer_target_agent_id` names the destination DA agent; post-call analysis rides the destination (`post_call_analysis_setting: only_destination_agent`).
- **Call row exists under another agent:** numbers can be re-bound; search by `retell_call_id`/number without the `agent_id` filter before concluding "no row".
- **404s during sync:** `voice_sync_stale_agent_recreated` / `voice_sync_stale_llm_recreated` mean the Retell resource was deleted upstream and self-healed — the stored ids CHANGED; re-read Step 0 before diffing.
