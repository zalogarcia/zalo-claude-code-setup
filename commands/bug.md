# /bug — Trace, Diagnose, Fix, Validate

Trace the full flow → identify root cause → fix narrowly → QA. Built around the `bug-fix` agent's 4-phase systematic debugging.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/problem-solving.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md

## Workflow

### Step 1: Gather Context

Ask the user:

- Expected behavior?
- Actual behavior?
- Steps to reproduce (if known)?
- Relevant errors or logs?

If the user already provided this, skip and proceed.

If the user said "I just reproduced this" → the bug is real. Skip re-verification per `~/.claude/CLAUDE.md` Debugging Protocol — go straight to logs.

### Step 2: Dispatch `bug-fix`

Pass:

- The bug description and reproduction steps from Step 1
- Working directory + relevant file paths
- Instruction to follow the 4-phase debugging in `~/.claude/agents/bug-fix.md`
- Instruction to check live logs first if Supabase/infrastructure is involved (`mcp__supabase__get_logs`)

Wait for one of:

- `## ROOT CAUSE FOUND` — proceed to Step 3.
- `## INVESTIGATION INCOMPLETE` — present competing hypotheses to user, ask which lead to pursue, re-dispatch with that lead.
- `## BLOCKED` — investigate the block (missing access, can't repro, etc.) and provide the missing context.

### Step 3: 3+ Fixes Rule (Architecture Gate)

If `bug-fix` reports it has already attempted 3+ failed fixes:

- **STOP fixing.**
- Apply `~/.claude/rules/problem-solving.md` 3+ Fixes Rule: question the architecture, not the fix.
- Dispatch `brainstorm` to challenge the assumption that the bug is where you've been looking.

### Step 4: Review with User

If root cause is clear and fix is narrow → proceed.
If root cause has alternatives → present diagnosis + options, wait for user choice.

### Step 5: Apply the Fix

- Minimal, targeted changes only.
- No surrounding refactor, no "while we're here" cleanup.
- Run build/typecheck after applying — verify it compiles.

### Step 6: QA Loop

Invoke `/qa-loop` to validate the fix and catch any regressions introduced by the fix itself.

### Step 7: Report

- **Root cause:** what was wrong and why (file:line)
- **Fix applied:** what changed
- **QA result:** clean or remaining issues
- **How to verify manually:** steps the user can take to confirm

## Anti-Patterns (will not do)

- Patch the symptom without finding the root cause.
- Refactor surrounding code "while in there."
- Fix unrelated bugs found along the way (report them; don't auto-fix).
- Continue trying fixes after the 3+ Fixes Rule fires.
- Claim "fix verified" without running the verification command in this turn.
