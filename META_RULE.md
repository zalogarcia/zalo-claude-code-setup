# Operational Meta-Rule

Re-injected on every `startup`, `/clear`, and `/compact`.
Edit this file freely — the `session-start.sh` hook reads it fresh each time.

**After compaction, read `.claude/HANDOFF.md` in the project if present** — it carries the branch/worktree/plan-file state written by the PreCompact hook.

## Available primitives in this `~/.claude/` setup

**Subagents** — fresh-context delegates. Read `~/.claude/rules/agent-contracts.md` for return contract.

- `frontend-specialist`, `qa-agent`, `safe-planner`, `brainstorm`, `live-test`, `bug-fix`, `outcomes-grader`

**Slash commands** — workflow orchestrators (thin; they `@`-include rules + dispatch agents).

- Core delivery: `/autopilot`, `/autopilot-merge`, `/bug`, `/qa-loop`
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
- `fable-insights` — weekly self-audit: one deep-analysis agent per session transcript, args `{days}`; scheduled Mondays 09:12 via launchd (`com.zalo.claude-weekly-insights`), writes report + PROPOSED_CHANGES to `~/.claude/usage-data/`

**Hooks (mechanized rules)** — prose rules that were historically skipped are now enforced at the tool layer:

- `sql-guard.py` (PreToolUse on `mcp__supabase__execute_sql`) — blocks multi-statement SQL; holds the first data query of a session until the schema is consulted
- `gitleaks-guard.py` (PreToolUse on Bash) — secret scan, 120s timeout

**Shared rules** at `~/.claude/rules/` (treat as authoritative reference; `@`-included by commands/agents):

- `agent-contracts.md` — H2 completion markers + DONE/CONCERNS/CONTEXT/BLOCKED status codes
- `gates.md` — 4 gate types (pre-flight / revision / escalation / abort) + the 5-step Verification Gate Function
- `checkpoints.md` — human-in-loop XML schema (human-verify / decision / human-action)
- `verification-patterns.md` — "Existence ≠ Implementation" + stub-detect greps + Common Failures table
- `anti-patterns.md` — universal anti-patterns + No-Placeholders list
- `questioning.md` — collaborative-extraction philosophy for requirements
- `context-budget.md` — PEAK / GOOD / DEGRADING / POOR tier behaviors + degradation warning signs
- `persuasion-principles.md` — Authority/Commitment/Scarcity/Social-Proof/Unity for writing rules that stick
- `when-to-parallelize.md` — 4-criteria decision rule for parallel agent dispatch
- `problem-solving.md` — when-stuck dispatch table (inversion / simplification / meta-pattern)
- `git-safety.md` — gitignore-before-create, no `git add .`, lock-file check

## The discipline

Before acting on a non-trivial task:

1. **Could a subagent handle this with a fresh context?** Prefer dispatching over inline. The main thread is an orchestrator; subagents are workers. If a step needs >2 file reads or >50 LOC of analysis, dispatch.
2. **Does a slash-command match?** Use it instead of reinventing.
3. **Does a rule in `~/.claude/rules/` apply?** Read it first; don't guess.

For independent units of work (3+ failing tests in different subsystems, multiple unrelated research questions), **dispatch in parallel** — multiple Agent calls in a single message run concurrently.

## The philosophy

**Rigor on process, simplicity on design.** Present the direct/simple architectural approach first. Don't add abstractions for hypothetical futures. But never compromise on verification/debugging discipline — those are gates, not preferences.

**Quick inline action for trivial tasks is fine.** Typo fixes, single-line changes, and pure conversation don't need skills/agents/rules. Use judgment — invoke when a skill clearly applies; skip when it's a stretch. Over-invocation wastes time as much as under-invocation.

**Verify before claiming done.** Per `~/.claude/rules/gates.md` Verification Gate Function: run the command in this turn, read the output, then claim. No "should work" / "probably passes" / "Looks good!" without fresh evidence. Coverage claims ("all/every X") additionally need a measured denominator — N of N plus the method (gates.md "Coverage Claims Need Denominators"). Deploy claims use the changed surface's proof signal from the repo's `.claude/VERIFY.md`, never a different pipeline's green.

**Budget the fan-out.** A wave of >5 Fable-bound agents requires the Fable Fan-Out Preflight in `~/.claude/rules/api-retry.md` — surface the limit math as a checkpoint:decision; never comply silently. After limit kills: resume, never restart (workflow cache replay / state.json).

**Subagent returns are contracts.** Subagents end with one of the H2 markers in `~/.claude/rules/agent-contracts.md`. When dispatching, expect the marker; when reporting subagent results, synthesize — don't paste raw output.
