---
name: voice-call-triage
description: Triage one voice call (or "the last call") on Delta Agents prod — pull the tenant_voice_calls row (status/duration/disconnection reason), the tenant_voice_tool_events timeline, the gateway ECS log window around the call, and a DA-intended vs Retell-actual config diff via the Retell GET endpoints. Use when the user says "it hung up", "call didn't work", "check the last call", "why did the voice agent…", "the call never picked up", or names a phone number + a call symptom. Encodes the call→symptom→logs loop that took ~20 iterations per bug in past voice sessions.
---

Triage a single Delta Agents voice call end-to-end: DB evidence → tool timeline → gateway logs → config diff. Collect ALL FOUR evidence layers BEFORE hypothesizing (the past 20-iteration loops came from fixing the first plausible theory instead of reading the second evidence layer).

Repo root assumed at `/Users/zalo/dev/delta-agents` (adjust if the checkout lives elsewhere). All prod reads go through the Supabase MCP (`mcp__supabase__execute_sql`, project `xbwcziymjfsobaxmanlo`) — never local `psql`. Column names below are verified against `docs/SCHEMA-PROD.md`; re-check there before editing any query.

## When to invoke

- "it hung up" / "the call cut off" / "call didn't work" / "caller just heard ringing"
- "check the last call" / "why did the voice agent do X on that call"
- A tenant reports a voice symptom with a phone number or a call time.
- After a Retell sync change, to confirm what the live agent actually runs.

For a FUZZY tenant symptom that is not call-shaped ("tenant X says things broke"), use the `tenant-triage` skill instead — this skill assumes the symptom is a specific call/agent.

## Inputs

Tenant (slug or id) + agent (name or id), **or** a phone number, **or** a Retell call id. Optional: a time window ("yesterday afternoon").

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

`tenant_voice_calls` — real columns: `retell_call_id` (varchar), `direction`, `from_number`, `to_number`, `call_status`, `disconnection_reason`, `duration_seconds`, `call_successful`, `user_sentiment`, `transfer_target_agent_id`, `started_at`, `ended_at`, `summary`, `transcript`, `metadata`. (`contact_id`/`agent_id` are uuid — cast comparisons `::uuid`.)

```sql
SELECT id, retell_call_id, direction, from_number, to_number,
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

## Output — correlation summary FIRST

Emit a short timeline (call start → inbound webhook → tool events → disconnect → post-call), the disconnection reason class, and which of the four evidence layers contains the anomaly — THEN the hypothesis and fix. If all four layers are clean, say so and widen the time window before theorizing.

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
- ❌ Grepping `/ecs/delta-agents/worker` for voice — the voice path is gateway-only.

## Edge cases

- **Multi-language agents:** the sibling locale agents have their OWN Retell agent/LLM ids in `config.voice.multiLanguage.agents` — a call answered post-swap runs the SIBLING's config; diff that one, not the main.
- **Transferred calls:** `transfer_target_agent_id` names the destination DA agent; post-call analysis rides the destination (`post_call_analysis_setting: only_destination_agent`).
- **Call row exists under another agent:** numbers can be re-bound; search by `retell_call_id`/number without the `agent_id` filter before concluding "no row".
- **404s during sync:** `voice_sync_stale_agent_recreated` / `voice_sync_stale_llm_recreated` mean the Retell resource was deleted upstream and self-healed — the stored ids CHANGED; re-read Step 0 before diffing.
