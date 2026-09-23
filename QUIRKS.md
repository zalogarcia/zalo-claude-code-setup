# Environment Quirks (each one has cost a re-derivation before)

- zsh exit codes: `cmd > /tmp/out 2>&1; echo $?` — never trust `$?` after a pipe; for tsc/build use the typecheck-and-build skill.
- `status` is a RESERVED zsh variable — assignments silently no-op (caused a false 50-min stall alarm); pick another name.
- cwd resets between Bash calls and relative `cd` compounds — use absolute paths in every command.
- Telegram creds: `jq` them from `~/.claude/settings.local.json` (the telegram skill does this) — don't hunt env vars.
- Python urllib/requests hits SSL cert errors on this Mac — use `curl` for HTTP in scripts.
- Scripts in the scratchpad can't resolve a project's `node_modules` — run node from the project dir.
- delta-agents monorepo: rebuild the shared package's dist before gateway/worker tests — stale dist = phantom type errors.
- Long/background work (interactive sessions only; a headless bridge run keeps Bash and Agent calls in the foreground): `run_in_background: true` + completion notification or a DONE-marker file — foreground `sleep`/pgrep polling is blocked.
- Playwright MCP writes screenshots to `.playwright-mcp/` under the project, not the scratchpad.
- Git worktrees need a real `npm install` — never symlink the parent's `node_modules`.
- Apply the additive migration BEFORE deploying code that reads the new schema (migrate-before-deploy).
- Two failed guesses against an external API → the next action is a ground-truth probe (validate_only / dry-run / GET the live resource), never a third guess.
- Formatter hooks rewrite ts/js/css/json on save — if an Edit fails "String not found", re-Read the file first (md/html are exempt).
- git is read-only for subagents; destructive git ops (`reset --hard`, `checkout .`, `clean -f`, `stash`) are hook-blocked without explicit user approval.
- Dual Homebrew: `/usr/local/bin` (Intel/Rosetta) precedes `/opt/homebrew/bin` (arm64/Metal) in PATH — bare tool names can resolve to CPU-only Intel builds (whisper-cli cost a ~50x-slower run, 2026-07-27). For compute-heavy CLIs, use the `/opt/homebrew/bin/...` absolute path and verify with `file $(command -v <tool>)` → must say arm64.
