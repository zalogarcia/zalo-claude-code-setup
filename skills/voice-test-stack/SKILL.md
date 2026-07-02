---
name: voice-test-stack
description: Bring the full Delta Agents local voice-test stack into a known-good state — kill stale gateway/dashboard listeners, start both from a named checkout/worktree with nohup + readiness polling, start the tunnel (cloudflared or ngrok, auto-picked from GATEWAY_URL), and print the callable state (tunnel URL, gateway health, dashboard URL, webhook URL shapes). Use before any live voice/webhook test against the local gateway, when the user says "spin up the voice test stack", or whenever a Retell/CRM webhook needs to reach localhost. Replaces the hand-assembled kill+build+node+vite+tunnel ritual.
---

Get the Delta Agents voice-test stack — gateway (:3000), dashboard (:5174), tunnel —
killed, restarted, listening, publicly reachable — via one deterministic script. Do not
hand-write the kill+build+nohup+curl+tunnel chain; invoke `voice-test-stack.sh`.

## When to invoke

- Before a live voice call test (Retell webhooks / in-call MCP tools must reach the local gateway)
- Before webhook testing (`POST /hooks/:crm_type/:tenant_slug`) against a local gateway
- After switching branches/worktrees — pass the checkout path to run the stack from it
- When the user says "start the voice test stack" / "get the tunnel up" / "expose the local gateway"

Skip for: prod testing (use `https://api.operatorbase.app` directly), dashboard-only UI
work (use the `dev-server-restart` skill on :5174 alone).

## Invocation

```bash
~/.claude/skills/voice-test-stack/voice-test-stack.sh up   [REPO_DIR] [--tunnel auto|cloudflared|ngrok|none] [--no-build]
~/.claude/skills/voice-test-stack/voice-test-stack.sh down [REPO_DIR]
~/.claude/skills/voice-test-stack/voice-test-stack.sh status
```

**Defaults:** `REPO_DIR=/Users/zalo/dev/delta-agents`, `--tunnel auto`, build ON.

**Examples:**

```bash
# Full stack from main, tunnel auto-picked from GATEWAY_URL in .env
~/.claude/skills/voice-test-stack/voice-test-stack.sh up

# From a worktree, no tunnel (local-only webhook curls)
~/.claude/skills/voice-test-stack/voice-test-stack.sh up /path/to/worktree --tunnel none

# Skip the tsc chain when dist/ is known-fresh
~/.claude/skills/voice-test-stack/voice-test-stack.sh up --no-build

# Tear down everything the script started
~/.claude/skills/voice-test-stack/voice-test-stack.sh down
```

## What the script does (verified against the repo 2026-07-02)

1. Preconditions: `$REPO_DIR/.env` exists; `node_modules` present (fresh worktrees need
   `npm ci` first — known gotcha)
2. Kills anything listening on :3000 and :5174 (`lsof -ti tcp:PORT -sTCP:LISTEN` — by
   port, not process name; same approach as `dev-server-restart`)
3. Builds the tsc chain shared → providers → core → mcp-servers → gateway (mirrors
   `scripts/dev.sh` standard mode), then verifies `apps/gateway/dist/index.js` exists
4. Starts the gateway detached: `node --env-file=.env dist/index.js` (built-JS mode —
   more reliable than `tsx watch`, per `dev.sh`), logs to `/tmp/voice-stack-gateway.log`,
   polls `/health` until 200 (45s cap), then reports `/ready` (sticky pool-warm boot gate)
5. Starts the dashboard detached: `npx vite --port 5174 --strictPort` in
   `apps/dashboard`, polls until responding
6. Starts the tunnel (see below), polls `https://<host>/health` until 200
7. Prints the **callable state block**: branch + checkout, gateway/dashboard/tunnel
   health codes, `GATEWAY_URL` match/mismatch, webhook URL shapes
   (`POST $BASE/hooks/:crm_type/:tenant_slug[/:agent_slug]`,
   `POST $BASE/voice/mcp/:tenantId/:agentId`, retell inbound/post-call), and a pointer to
   `.claude/test-identities.md`

## Tunnel modes

`--tunnel auto` (default) derives the mode from `GATEWAY_URL` in `$REPO_DIR/.env`:

- `*ngrok*` host → **ngrok**: `ngrok http --url=<host> 3000` (static domain
  `wanting-saddlebag-rocklike.ngrok-free.dev`; authtoken already in
  `~/Library/Application Support/ngrok/ngrok.yml` — non-interactive)
- `*blackumbrella.app*` host (or cloudflared config present) → **cloudflared**:
  `cloudflared tunnel run` (named tunnel `4199e388…` → `da-local.blackumbrella.app` →
  `localhost:3000`; credentials already in `~/.cloudflared/` — non-interactive)
- neither → `none` with a warning

**Critical invariant:** Retell-sync builds the in-call MCP/webhook URLs from
`GATEWAY_URL` (`apps/gateway/src/retell-sync/_shared.ts`). The script prints
MATCH/MISMATCH between the running tunnel and `GATEWAY_URL` — on MISMATCH, fix `.env`
and re-sync the voice agents under test, or Retell will call a dead URL mid-call.

## Exit codes

- `0` — gateway + dashboard up (and tunnel 200 if started)
- `1` — gateway failed `/health` within timeout (last 30 log lines on stderr)
- `2` — dashboard failed to respond (last 30 log lines on stderr)
- `3` — gateway+dashboard fine but tunnel never returned 200 (tunnel log tail on stderr)
- `64` — bad arguments

## Output shape

Ends with a `CALLABLE STATE` block. Do NOT paste service logs into the conversation —
the script surfaces the failure region itself. Logs stay at
`/tmp/voice-stack-{gateway,dashboard,tunnel}.log`, PIDs at `/tmp/voice-stack-*.pid`.

## Edge cases

- **Port 3000 held by another project's dev server** — it gets killed (by-port kill is
  the point); mention it to the user if the process wasn't a delta-agents one
- **`/ready` stays 503** — Supabase pooler / Redis not reachable; check
  `.env` `REDIS_URL` (local dev Redis, NOT prod) and `/tmp/voice-stack-gateway.log`
- **Fresh worktree** — script refuses to run without `node_modules`; run `npm ci` first
- **ngrok free plan** — one simultaneous agent session; a session running elsewhere
  (another machine) makes the local one fail — the tunnel log tail shows it
- **Only gateway is tunneled** — the dashboard stays local-only; the tunnel ingress maps
  the public host to `localhost:3000` only
- **wa-bailey (:3002) is NOT started** — voice testing doesn't need WhatsApp; use
  `scripts/dev.sh` if you need the full trio

## Pair with

- `.claude/test-identities.md` (in the repo) — admin account, test phone +17867810250,
  Retell test agents (Ava / zalito uno), dashboard token-mint recipe
- `dev-server-restart` skill — single-port restarts when you don't need the full stack
- `live-test` agent / `live-test-campaign` skill — bring the stack up first, then test
