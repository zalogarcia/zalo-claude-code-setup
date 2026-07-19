# Operational Meta-Rule

Re-injected on every `startup`, `/clear`, and `/compact`.
Edit this file freely — the `session-start.sh` hook reads it fresh each time.

**After compaction, read `.claude/HANDOFF.md` in the project if present** — it carries the branch/worktree/plan-file state written by the PreCompact hook.

## Available primitives in this `~/.claude/` setup

**Subagents** — fresh-context delegates. Read `~/.claude/rules/agent-contracts.md` for return contract.

- `frontend-specialist`, `qa-agent`, `safe-planner`, `brainstorm`, `live-test`, `bug-fix`, `outcomes-grader`

**Slash commands** — workflow orchestrators (thin; they `@`-include rules + dispatch agents).

- Core delivery: `/autopilot`, `/autopilot-merge`, `/bug`, `/qa-loop`
- Go-live: `/go-live` — activation & live-verification bridge for built-but-unactivated features (consumes `.autopilot/activation.md`; runs the traffic harness + live-test campaign; the mandatory next step after any `CODE-COMPLETE — NOT LIVE-VERIFIED` autopilot run)
- Thinking: `/brainstorm`, `/plan`

**Skills** — compound tools.

- Workflow helpers: `typecheck-and-build`, `commit-with-heredoc`, `dev-server-restart`, `autopilot-collect`
- Repo scaffolding: `repo-init` — per-repo `.claude/CLAUDE.md`, path-scoped rules, and `.claude/VERIFY.md` (the machine-readable verification manifest: deploy surfaces + THE proof signal each deploy claim requires). Orchestrators read VERIFY.md before claiming anything is tested or live; drift check at `~/.claude/scripts/repo-drift-check.sh`.
- Testing: `live-test-campaign` (post-ship live verification campaign — design-review first, cheapest-first phase ladder, positive-evidence discipline)
- Frontend (opt-in): `frontend-design`
- Meta + integrations: `create-skill`, `cf-crawl`

**Workflows** — deterministic multi-agent scripts at `~/.claude/workflows/`, run via the Workflow tool. Commands fall back to inline agent dispatch when workflows are unavailable.

- `qa-audit` — read-only parallel bug hunt + adversarial verify (backs `/qa-loop`). Its return carries `verdict`/`untrusted`: dead finder or skeptic agents mark the run UNTRUSTED — never treat an untrusted result as a clean pass; resume the run instead.
- `plan-verify` — brainstorm + principles gates with one revision pass (backs `/plan`)
- `fable-insights` — self-audit: one deep-analysis agent per session transcript, args `{days}` (default 7) + `{exclude_session_id}` (REQUIRED: your own session id — the UUID segment of your scratchpad path; only that transcript is skipped, open sessions from other terminals ARE analyzed as in-progress snapshots). Run it interactively when you want a usage audit. The orchestrator then synthesizes per `~/.claude/workflows/fable-insights-synthesis.md` (artifact names, baseline comparison, MECHANIZATION + DEMOTION bias — every proposed change declares its enforcement form, mechanism by default) into `~/.claude/usage-data/`. (Interactive only — the Workflow tool's background-callback model can't complete under a one-shot headless `claude -p`, so it is not cron-scheduled.)

**Hooks (mechanized rules)** — prose rules that were historically skipped are now enforced at the tool layer:

- `sql-guard.py` v2 (PreToolUse on `mcp__supabase__execute_sql`) — blocks multi-statement SQL; holds the first data query until the schema is consulted; validates every query's tables against the repo's `docs/SCHEMA-PROD.md` and flags >7-day-stale snapshots
- `gitleaks-guard.py` (PreToolUse on Bash) — secret scan on commit/push (120s timeout) + destructive-git guard: `reset --hard`, `checkout .`, `restore .`, `clean -f`, `stash` are blocked without explicit user approval (`# user-approved` comment on the re-run). git is READ-ONLY for subagents.
- `agent-model-guard.py` (PreToolUse on Agent/Task) — blocks model-less dispatches of built-in agent types on Fable sessions; pass `model:"opus"` explicitly per the CLAUDE.md split policy (or `model:"fable"` deliberately)
- `prettier-format.sh` (PostToolUse on Edit/Write) — no-op-aware code formatting (ts/js/css/json only; md/html exempt); when it rewrites a file it TELLS you to re-Read before further edits — do so
- `QUIRKS.md` is appended to this injection by `session-start.sh` — the recurring environment traps, front-loaded so they are never re-derived mid-task

**Shared rules** at `~/.claude/rules/` (treat as authoritative reference; `@`-included by commands/agents):

- `agent-contracts.md` — H2 completion markers + DONE/CONCERNS/CONTEXT/BLOCKED status codes
- `gates.md` — 4 gate types (pre-flight / revision / escalation / abort) + the 5-step Verification Gate Function
- `checkpoints.md` — human-in-loop XML schema (human-verify / decision / human-action)
- `verification-patterns.md` — "Existence ≠ Implementation" + stub-detect greps + Common Failures table
- `anti-patterns.md` — universal anti-patterns + No-Placeholders list
- `questioning.md` — collaborative-extraction philosophy for requirements
- `context-budget.md` — PEAK / GOOD / DEGRADING / POOR tier behaviors + degradation warning signs
- `when-to-parallelize.md` — 4-criteria decision rule for parallel agent dispatch
- `problem-solving.md` — when-stuck dispatch table (inversion / simplification / meta-pattern)
- `git-safety.md` — gitignore-before-create, no `git add .`, lock-file check

On-demand references live in `~/.claude/rules-ref/` (NOT auto-loaded — read when the situation applies): `persuasion-principles.md` (authoring rules/skills that stick), `frontend-workflow.md` (UI-design-heavy pipeline).

## The discipline

Before acting on a non-trivial task:

1. **Could a subagent handle this with a fresh context?** Prefer dispatching over inline. The main thread is an orchestrator; subagents are workers. If a step needs >2 file reads or >50 LOC of analysis, dispatch.
2. **Does a slash-command match?** Use it instead of reinventing.
3. **Does a rule in `~/.claude/rules/` apply?** Read it first; don't guess.

For independent units of work (3+ failing tests in different subsystems, multiple unrelated research questions), **dispatch in parallel** — multiple Agent calls in a single message run concurrently.

## The philosophy

**Rigor on process, simplicity on design.** Present the direct/simple architectural approach first. Don't add abstractions for hypothetical futures. But never compromise on verification/debugging discipline — those are gates, not preferences.

**Quick inline action for trivial tasks is fine.** Typo fixes, single-line changes, and pure conversation don't need skills/agents/rules. Use judgment — invoke when a skill clearly applies; skip when it's a stretch. Over-invocation wastes time as much as under-invocation.

**Verify before claiming done.** Per `~/.claude/rules/gates.md` Verification Gate Function: run the command in this turn, read the output, then claim. No "should work" / "probably passes" / "Looks good!" without fresh evidence. Coverage claims ("all/every X") additionally need a measured denominator — N of N plus the method (gates.md "Coverage Claims Need Denominators"). Deploy claims use the changed surface's proof signal from the repo's `.claude/VERIFY.md`, never a different pipeline's green. Behavior claims proven only by on-disk proxies (mocked unit tests, greps, typecheck) cap at **CODE-COMPLETE — NOT LIVE-VERIFIED** — never "COMPLETE"/"works" (gates.md Red Flags; run the repo's traffic harness / `/go-live` to lift the ceiling).

**Budget the fan-out.** A wave of >5 Fable-bound agents requires the Fable Fan-Out Preflight in `~/.claude/rules/api-retry.md` — surface the limit math as a checkpoint:decision; never comply silently. After limit kills: resume, never restart (workflow cache replay / state.json).

**Subagent returns are contracts.** Subagents end with one of the H2 markers in `~/.claude/rules/agent-contracts.md`. When dispatching, expect the marker; when reporting subagent results, synthesize — don't paste raw output.
