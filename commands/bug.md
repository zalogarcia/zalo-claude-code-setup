# /bug — Trace, Diagnose, Fix, Validate

Trace the full flow → identify root cause → fix narrowly → QA. Built around the `bug-fix` agent's 4-phase systematic debugging.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/problem-solving.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md

## Workflow

### Step 0: Triage — is this actually a code bug?

Before dispatching the heavyweight `bug-fix` agent, classify the report. The 4-phase agent is for **code defects** (wrong logic, crash, regression). It is wasteful overkill for:

- **Config / data issues** — "user is on the wrong account/tenant", "the record has bad data", "the env var is unset", "this customer's settings are off". → Run a **read-only query/check first** (`mcp__supabase__execute_sql`, a log read, a config grep). Often the "bug" is a data state, fixable without touching code.
- **Support / how-does-this-work questions** — answer directly or trace the relevant code yourself; no agent needed.
- **"It's slow" / infra** — check logs/metrics before assuming a code defect.

Only proceed to Step 1 when the evidence points to a genuine code defect. If a quick read-only check would confirm or refute the code-bug hypothesis, do that check first and report what you found — don't spin up the agent on a hunch.

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

- `## ROOT CAUSE FOUND — CONFIDENCE 10/10` — proceed to Step 2.5.
- `## INVESTIGATION INCOMPLETE — CONFIDENCE <N>/10` (N ∈ 1..9) — proceed to Step 2.5 for routing.
- `## BLOCKED` — investigate the block (missing access, can't repro, etc.) and provide the missing context.

### Step 2.5: Confidence Verification (orchestrator gate)

After `bug-fix` returns, parse the H2 marker line via regex (single source of truth — do NOT parse body text for confidence values). The canonical separator emitted by `bug-fix` is the em-dash (—); the parser below also accepts an ASCII hyphen (-) as defensive coding in case the agent emits a hyphen by mistake. **Em-dash is the canonical form; hyphen-tolerance is defensive, not endorsed.**

```bash
# Capture the agent's last H2 marker line (defensive: accepts em-dash OR ASCII hyphen)
marker_line=$(grep -oE '^## (ROOT CAUSE FOUND|INVESTIGATION INCOMPLETE|BLOCKED).*$' "$agent_return_file" | tail -1)

# Strict canonical match (em-dash, confidence-suffixed):
#   ^## (ROOT CAUSE FOUND|INVESTIGATION INCOMPLETE) — CONFIDENCE [0-9]+/10\s*$
# Defensive variant (accepts em-dash OR ASCII hyphen):
#   ^## (ROOT CAUSE FOUND|INVESTIGATION INCOMPLETE)( —| -) CONFIDENCE [0-9]+/10\s*$
```

**Routing by parsed marker (confidence value extracted from the marker line itself):**

- `^## ROOT CAUSE FOUND( —| -) CONFIDENCE 10/10\s*$` → proceed to Step 3 ONLY if the body contains a `### Confidence Block` section with all four subsections (Reproducibility Class, Evidence, Test-the-theory, Confidence rationale). If the block is missing or incomplete → re-dispatch ONCE with a surgical reminder prompt (do NOT re-walk the 4 phases):

  > "Your previous return emitted `## ROOT CAUSE FOUND — CONFIDENCE 10/10` but the required Confidence Block was missing or incomplete. Re-emit with the full block per the Confidence Gate. If you cannot reach 10/10 with Test-the-theory evidence captured in this turn, emit `## INVESTIGATION INCOMPLETE — CONFIDENCE <N>/10` instead."

  If the second dispatch still fails the gate → present the agent's competing hypotheses to the user and ask which lead to pursue. Do NOT proceed to Step 3 with sub-10/10 confidence.

- `^## INVESTIGATION INCOMPLETE( —| -) CONFIDENCE [1-9]/10\s*$` → present the agent's competing hypotheses to the user and ask which lead to pursue. Do NOT auto-fix. Do NOT proceed to Step 3.

- `^## BLOCKED\s*$` → present the blocker to the user.

- Marker missing or malformed (no match) → re-dispatch ONCE with a surgical reminder prompt asking the agent to emit the canonical confidence-suffixed marker line. Do NOT re-walk the 4 phases.

If marker matches `## ROOT CAUSE FOUND — CONFIDENCE 10/10` and Confidence Block validates → proceed to Step 3.

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

If the fix ships (user says push/deploy): prove it went live using the changed
surface's proof signal from `.claude/VERIFY.md` — never a different pipeline's
green status. If VERIFY.md is missing, derive the signal from the CI config for
the changed paths, say so explicitly, and recommend `/repo-init`.

## Anti-Patterns (will not do)

- Patch the symptom without finding the root cause.
- Refactor surrounding code "while in there."
- Fix unrelated bugs found along the way (report them; don't auto-fix).
- Continue trying fixes after the 3+ Fixes Rule fires.
- Claim "fix verified" without running the verification command in this turn.
