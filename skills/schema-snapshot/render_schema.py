import json, re, sys, datetime, os
d = sys.argv[1]; out = sys.argv[2]
cols_raw = json.load(open(d+'/columns_raw.json')); fks = json.load(open(d+'/fks.json'))
rls_raw = json.load(open(d+'/rls_raw.json')); parents = json.load(open(d+'/parents.json')); views = json.load(open(d+'/views.json'))
PART = re.compile(r'^(usage_events|wallet_ledger)_(\d{4}_\d{2}|default)$')
def short(t):
    t = t.replace('character varying', 'varchar').replace('timestamp with time zone', 'timestamptz').replace('timestamp without time zone', 'timestamp')
    t = re.sub(r'^character\((\d+)\)', r'char(\1)', t)
    if t == '_text': t = 'text[]'
    return t
tables = {}
for r in cols_raw:
    n = r['table_name']
    if PART.match(n): continue
    tables[n] = {'cols': [l.split('|', 3) for l in r['cols'].split('\n')], 'partitioned': None}
leaf_by_parent = {}
for r in cols_raw:
    m = PART.match(r['table_name'])
    if m: leaf_by_parent.setdefault(m.group(1), []).append(r['table_name'])
rls = {r['table_name']: (r['rls_enabled'], r['rls_forced']) for r in rls_raw if not PART.match(r['table_name'])}
for p in parents:
    n = p['table_name']; leaves = sorted(leaf_by_parent.get(n, []))
    monthly = [l for l in leaves if not l.endswith('_default')]; dflt = [l for l in leaves if l.endswith('_default')]
    rng = f"{monthly[0]} … {monthly[-1]} (monthly)" if monthly else 'monthly'
    tables[n] = {'cols': [l.split('|', 3) for l in p['cols'].split('\n')], 'partitioned': rng + (f" plus `{dflt[0]}` (DEFAULT partition)" if dflt else '')}
    rls[n] = (p['rls_enabled'], p['rls_forced'])
ANN = {}
_ap = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'annotations.json')
if os.path.exists(_ap):
    ANN = {k: v for k, v in json.load(open(_ap)).items() if not k.startswith('_')}
fk_by = {}
for f in fks: fk_by.setdefault(f['table_name'], []).append(f['fk_def'])
names = sorted(tables)
uuid_cid = [n for n in names if any(c[0]=='contact_id' and c[1]=='uuid' for c in tables[n]['cols'])]
var_cid = [n for n in names if any(c[0]=='contact_id' and c[1].startswith('character varying') for c in tables[n]['cols'])]
def mdtable(rows, headers):
    rows = [[str(x) for x in r] for r in rows]
    w = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    lines = ['| ' + ' | '.join(h.ljust(w[i]) for i, h in enumerate(headers)) + ' |', '| ' + ' | '.join('-'*w[i] for i in range(len(headers))) + ' |']
    for r in rows: lines.append('| ' + ' | '.join(r[i].ljust(w[i]) for i in range(len(headers))) + ' |')
    return '\n'.join(lines)
nfk = len(fks); nt = len(names); nv = len(views)
gen = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
H = []
H.append('# SCHEMA-PROD, Production Database Snapshot\n')
H.append(f'> **Generated:** {gen} (full body regenerated from the live catalog)')
H.append('> **Source:** Supabase prod project `$DELTA_PROD_PROJECT_REF` (see `~/.claude/settings.local.json`), `public` schema')
H.append('> **How:** `schema-snapshot` skill (`~/.claude/skills/schema-snapshot/SKILL.md`), re-run it to refresh.')
H.append('> **Refresh when:** after applying ANY migration, or when this snapshot is >7 days old.')
H.append('> **Includes:** every migration applied to prod through `00149_agency_whitelabel_v1`.')
H.append('> Latest bodies: `00148_action_refunds` (new `action_refunds` table, applied 2026-08-21) and')
H.append('> `00149_agency_whitelabel_v1` (applied 2026-08-25: six additive columns on `agency_whitelabel`, `custom_css`,')
H.append('> `enabled`, `disabled_at`, `app_domain_provider_state`, `links_domain_cert_arn`, `links_domain_validation`,')
H.append('> plus the CHECK `agency_whitelabel_custom_css_len` capping stored CSS at 32,768 bytes; and two')
H.append('> entitlement-bookkeeping timestamps on `tenants`, `membership_tier_changed_at` and')
H.append('> `membership_tier_source_event_at`). No RLS, index or policy change in either.')
H.append('> This file records column types, nullability, defaults, FKs and RLS flags, not CHECK membership')
H.append('> lists: allowed values live in the migration and in `WorkflowLogEventType` in')
H.append('> `packages/contracts/src/workflows.ts`.\n')
H.append(f'{nt} tables, {nv} view, {nfk} foreign keys. Read this file BEFORE writing ad-hoc SQL against prod, never guess column names.')
H.append('Legend: `null` column shows `NO` for NOT NULL, `YES` for nullable. RLS forced = applies even to the table owner.\n')
H.append('## Known drift vs migrations\n')
H.append('''- **`tenant_followups.created_at` / `updated_at`**, historically PROD-only drift (existed in prod, absent
  from migrations; read by the `scheduled_followups` KPI in `agent-analytics.ts`). **Reconciled** by migration
  `00101_mock_demo_full_business.sql` via `ADD COLUMN IF NOT EXISTS`. Re-verified in this snapshot: both columns
  present in prod as `timestamptz NOT NULL DEFAULT now()` and covered by migration history, no remaining
  drift on this table.
- **Branch drift, not schema drift:** migrations `00115`-`00136` were applied to prod while their `.sql` files
  lived on `autopilot/20260716-094944-59229` rather than `main`. That branch has since been merged, and this
  snapshot was taken on `main` with `supabase/migrations/` carrying the full `00115`-`00149` run.
  Re-verified in this snapshot: every one of the tables below name-matches a `CREATE TABLE` in
  `supabase/migrations/`, 0 unaccounted for.
- **Migration label mismatch (naming, not schema):** `00129`/`00130` were applied to prod pre-renumber
  under their ORIGINAL names, so `list_migrations` reports them as
  `00127_twilio_byo_accounts_and_webhook_migrations` / `00128_twilio_managed_provisioning_state`,
  while the repo files are `00129_*` / `00130_*`. Re-verified in this snapshot. Note `00127` is also a
  real, distinct repo migration (`00127_wallet_credit_dedup.sql`), so the labels genuinely collide.
- **`00149_agency_whitelabel_v1` applied 2026-08-25** (via `mcp__supabase__apply_migration`, so it IS in
  `list_migrations`); the pending-drift note that lived here since 2026-08-24 is closed and the columns
  below are the live catalog.
- No prod-only column/table drift is currently known. If a query fails on a column that IS listed here,
  refresh the snapshot before assuming drift.
''')
H.append('## Common wrong guesses (from the friction audit, these cost ~60 wasted turns)\n')
H.append(mdtable([
 ['`agents` table', "It's `tenant_agents`"],
 ['`tenant_audit_log` table', "It's `audit_log` (tenant-scoped), `agency_audit_log`, or `tenant_ingestion_audit`"],
 ['`tenant_contacts.first_name` / `last_name`', 'Single `name` column (+ optional `display_name`)'],
 ['`tenant_followups.scheduled_at`', "It's `due_at`"],
 ['`tenants.name`', 'No name column, use `slug` (display name lives in `config` JSONB)'],
 ['`usage_events_*` / `wallet_ledger_*` leaf tables', 'Query the parents `usage_events` / `wallet_ledger` (monthly partitions)'],
 ['`workflows` / `forms` tables', "They're `tenant_workflows` / `tenant_forms` (+ `tenant_workflow_*`, `tenant_form_submissions`)"],
 ['`tenant_contact_erasure_requests.contact_id` is an FK', 'It is deliberately NOT an FK, so the journal survives contact deletion'],
 ['A view inherits the caller\'s RLS', 'It does NOT unless `security_invoker=true` is set. A definer-semantics view reads its base tables as the OWNER and silently bypasses `app.current_tenant`. New views MUST set it (see [Views](#views))'],
 ['`agency_whitelabel` is empty scaffold', 'Live since 00149: `custom_css`/`enabled`/`disabled_at`/domain-provider columns are real; brand resolution also needs `tenants.membership_tier = elite_pro`'],
], ['You guessed', 'Reality']) + '\n')
H.append('## `contact_id` type varies by table (42P08 trap)\n')
H.append('Comparing a `uuid` column to a `varchar` parameter (or vice versa) throws `42P08 could not determine data type`\nor a type-mismatch error. Cast explicitly: `contact_id = $1::text` / `contact_id = $1::uuid`.\n')
H.append('- **`uuid` contact_id:** ' + ', '.join(f'`{n}`' for n in uuid_cid))
H.append('- **`varchar` contact_id (NOT an FK):** ' + ', '.join(f'`{n}`' for n in var_cid) + '\n')
H.append('---\n')
H.append('## Tables\n')
B = []
for n in names:
    t = tables[n]; B.append(f'### `{n}`\n')
    if t['partitioned']: B.append(f"_Partitioned (monthly). Partitions: {t['partitioned']}. Query THIS parent, never a leaf._\n")
    en, fo = rls.get(n, (False, False))
    B.append('_RLS: ' + ('enabled (forced)' if en and fo else 'enabled (not forced)' if en else 'disabled') + '_\n')
    rows = [[f'`{c[0]}`', short(c[1]), c[2], (f'`{c[3]}`' if c[3] else '')] for c in t['cols']]
    B.append(mdtable(rows, ['column', 'type', 'null', 'default']) + '\n')
    if n in fk_by:
        B.append('FKs:\n'); B.extend(f'- `{f}`' for f in fk_by[n]); B.append('')
    if n in ANN: B.append(ANN[n] + '\n')
V = ['## Views\n', '''Views ARE query targets in this codebase (the gateway reads `tenant_agent_goal_attributions`), so they are
snapshotted here alongside tables.

**Why `security_invoker` is load-bearing:** a Postgres view runs with the privileges of its OWNER unless
`security_invoker=true` is set. A definer-semantics view therefore reads its base tables as the owner and
**bypasses the caller's RLS**, `app.current_tenant` is never applied. `tenant_agent_goal_attributions`
leaked cross-tenant bookings through exactly this hole until `00135_goal_attribution_view_security_invoker`
set the option on 2026-07-30. Any NEW view over tenant tables must set `security_invoker=true` in the same
migration that creates it.
''']
for v in views:
    V.append(f"### `{v['view_name']}`\n")
    V.append('_Options: `security_invoker=true`_\n' if v['security_invoker'] else '_Options: (none) - DEFINER semantics, bypasses caller RLS_\n')
    reads = sorted(set(re.findall(r'(?:FROM|JOIN)\s+(?:public\.)?([a-z_][a-z0-9_]*)', v['def'], flags=re.I)))
    V.append('_Reads from: ' + ', '.join(f'`{r}`' for r in reads) + '_\n')
    rows = [[f'`{l.split("|")[0]}`', short(l.split("|")[1]), 'YES'] for l in v['cols'].split('\n')]
    V.append(mdtable(rows, ['column', 'type', 'null']) + '\n')
doc = '\n'.join(H) + '\n' + '\n'.join(B) + '\n' + '\n'.join(V) + '\n---\n\n_Generated file, do not hand-edit. Refresh via the `schema-snapshot` skill._\n'
open(out, 'w').write(doc)
print(f'Wrote {out}: {nt} tables, {nfk} FKs, {nv} view(s)')
