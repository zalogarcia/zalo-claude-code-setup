---
name: dev-server-restart
description: Kill any stale dev server on a given port, restart it cleanly in the project, poll until it accepts connections, and smoke-test a route — returning HTTP status + log tail. Use before testing UI in the browser, after env changes, or whenever Claude wrote "pkill -f 'next dev'" in a previous turn and needs the server back up. Replaces the 100+ hand-written kill+sleep+curl variants.
---

Get a dev server into a known-good state — killed, restarted, listening, responding — via a deterministic shell script. Do not hand-write the kill+sleep+curl chain; invoke `restart.sh`.

## When to invoke

- Before a `live-test` agent run when the dev server might be stale or down
- After `.env*` / `next.config.*` / `vite.config.*` / `package.json` changes (config needs reload)
- After installing/removing dependencies
- When the user says "restart the dev server" / "the dev server is stuck"
- Any time you wrote a `pkill -f 'next dev'` and need it back up

Skip for: production builds (use the deploy flow), one-shot scripts that don't host a server.

## Invocation

```bash
~/.claude/skills/dev-server-restart/restart.sh [PORT] [CWD] [PROBE_PATH]
```

**Defaults:** `PORT=3000`, `CWD=$(pwd)`, `PROBE_PATH=/`

**Examples:**

```bash
# Restart on default port 3000, probe root
~/.claude/skills/dev-server-restart/restart.sh

# Restart on port 5173 (Vite default)
~/.claude/skills/dev-server-restart/restart.sh 5173

# Restart in a specific project, probe /admin
~/.claude/skills/dev-server-restart/restart.sh 3000 /path/to/project /admin

# Or via env vars
PORT=4321 CWD=/path/to/astro-project PROBE=/blog \
  ~/.claude/skills/dev-server-restart/restart.sh
```

## What the script does

1. Detects package manager from lockfile (npm / pnpm / yarn / bun)
2. Kills anything listening on the port (`lsof -ti tcp:PORT -sTCP:LISTEN` — by port, not process name)
3. Belt-and-suspenders kill of `next dev`, `vite`, `react-scripts start`
4. Starts `$PM run dev` detached via `nohup`, logs to `/tmp/dev-server-<PORT>.log`
5. Polls every 500ms for up to `TIMEOUT_S` (default 30s) until the port responds
6. Smoke-tests the probe path, reports HTTP status + response size + elapsed time
7. On 5xx, greps the log for error lines and surfaces the first 10

## Exit codes

- `0` — server up, probe returned 2xx/3xx/4xx
- `1` — server failed to start within timeout (last 30 log lines printed to stderr)
- `2` — server up but probe returned 5xx (log error region printed to stderr)

## Output shape

Success: `READY in Xs | :PORT/probe → HTTP 200 (NNNN bytes) | log=/tmp/dev-server-PORT.log`

Do NOT paste the full log into the conversation — the script already extracts the relevant region.

## Edge cases handled by the script

- **Port already held by a non-dev process** — `lsof` kills whatever is there; if you don't want that, check before invoking
- **HTTPS-only dev** — script probes HTTP; if your dev runs HTTPS, modify the curl line in `restart.sh`
- **Different package manager** — auto-detected from lockfile
- **Hot-reload triggered by kill** — the poll loop handles this naturally
- **Tunneled dev (ngrok / Cloudflare Tunnel)** — only probes localhost; tunnel is downstream

## Pair with

- `live-test` agent — call this skill first to ensure the server is up, then dispatch `live-test` to interact via Playwright
- `typecheck-and-build` skill — if types/build fail, the dev server likely won't compile either; fix types first
