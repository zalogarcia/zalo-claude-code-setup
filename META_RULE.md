# Operational Meta-Rule

Re-injected on every `startup`, `/clear`, and `/compact`.
Edit this file freely — the `session-start.sh` hook reads it fresh each time.

## Available primitives in this `~/.claude/` setup

**Subagents** — fresh-context delegates. Read `~/.claude/rules/agent-contracts.md` for return contract.

- `frontend-specialist`, `qa-agent`, `safe-planner`, `brainstorm`, `live-test`, `bug-fix`, `image-craft-expert`

**Slash commands** — workflow orchestrators (thin; they `@`-include rules + dispatch agents).

- `/ship`, `/tdd`, `/bug`, `/qa-loop`, `/deploy-validate`, `/brainstorm`, `/build-fix`, `/refactor-clean`, `/learn`, `/session-save`, `/autoloop`, `/autotest`, `/e2e`, `/redesign`, ...

**Skills** — compound tools.

- `frontend-design`, `multi-edit`, `cf-crawl`, `telegram`

**Shared rules** at `~/.claude/rules/` (treat as authoritative reference; `@`-included by commands/agents):

- `agent-contracts.md` — H2 completion markers + DONE/CONCERNS/CONTEXT/BLOCKED status codes
- `gates.md` — 4 gate types (pre-flight / revision / escalation / abort) + the 5-step Verification Gate Function
- `checkpoints.md` — human-in-loop XML schema (human-verify / decision / human-action)
- `verification-patterns.md` — "Existence ≠ Implementation" + stub-detect greps + Common Failures table
- `anti-patterns.md` — universal anti-patterns + No-Placeholders list
- `questioning.md` — dream extraction philosophy for requirements
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

**Verify before claiming done.** Per `~/.claude/rules/gates.md` Verification Gate Function: run the command in this turn, read the output, then claim. No "should work" / "probably passes" / "Looks good!" without fresh evidence.

**Subagent returns are contracts.** Subagents end with one of the H2 markers in `~/.claude/rules/agent-contracts.md`. When dispatching, expect the marker; when reporting subagent results, synthesize — don't paste raw output.
