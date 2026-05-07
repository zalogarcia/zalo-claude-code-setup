# /ship — Full Feature Delivery

Plan → implement → QA → wait for explicit push approval. The orchestrator owns sequencing; subagents do the work.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/anti-patterns.md
@~/.claude/rules/checkpoints.md
@~/.claude/rules/plan-verification.md
@~/.claude/rules/engineering-principles.md

## Workflow

### 1. Plan

If the change touches 3+ files, dispatch `safe-planner`. Otherwise, write a 3-bullet inline plan: affected files, expected behavior, edge cases.

Wait for `## PLAN READY` (or `## NEEDS DECISION` → resolve with user before proceeding).

### 1.5. Plan Verification (only when safe-planner was dispatched)

If you wrote an inline plan in step 1, skip this step.

If `safe-planner` was dispatched, run the Plan Verification Loop per `~/.claude/rules/plan-verification.md` BEFORE moving to Implement:

- **Skip heuristic** — if the plan has ≤ 2 work units, skip verification. Note the skip in the report. (See `~/.claude/rules/plan-verification.md` for rationale.)
- Otherwise, run **both gates in parallel** (single message, two Agent calls):
  - **Gate 1 — Brainstorm-vet**: dispatch `brainstorm` with the task + plan; ask for inversion / simplification / scale-game / meta-pattern critique. Expect `## EXPLORATION COMPLETE`.
  - **Gate 2 — Principles-vet**: dispatch `outcomes-grader` with the plan as artifact and `~/.claude/rules/engineering-principles.md` as rubric. Expect `## OUTCOMES PASSED` or `## OUTCOMES UNMET`.
- **If both pass** → proceed to Implement. Note "verification passed" in the eventual report.
- **If either flags concerns** → re-dispatch `safe-planner` ONCE with combined findings. Wait for revised `## PLAN READY`. **No second revision pass** — cap at one. If concerns remain, note them and proceed; the QA loop and final report capture residual risk.

### 2. Implement

- All UI work goes through `frontend-specialist`. Never inline.
- All other code can be inline if scope is single-file; dispatch a general-purpose implementer (template at `~/.claude/agents/templates/implementer-prompt.md`) when scope is multi-file.
- Wait for `## IMPLEMENTATION COMPLETE`. Treat `## IMPLEMENTATION DONE_WITH_CONCERNS` as a soft block — read concerns, decide whether to proceed.

### 3. QA Loop (Revision Gate)

This is a Revision Gate — must reach a clean state before exit. Apply `~/.claude/rules/gates.md` Part 2 Verification Gate Function.

- Kill stale processes: `pkill -f 'next dev' || true`
- TypeScript: `npx tsc --noEmit`
- Build: `npm run build`
- Tests: relevant suite
- For frontend: dispatch `live-test`. Wait for `## UI VERIFIED`.
- Dispatch `qa-agent`. Wait for `## VERIFICATION PASSED` (or `## ISSUES FOUND` → fix all CRITICAL/HIGH, decide on MEDIUM/LOW with user).

If any check fails → fix silently and re-run. Do not report until everything is green.

### 4. Report

Present:

- Files changed (with one-line summaries)
- QA evidence (commands run + their output, not "should pass")
- **Plan Verification status** (one line):
  - "Plan verification skipped (≤2 work units)" — if skip heuristic fired, OR
  - "Plan verification passed (no revisions)" — both gates clean on first pass, OR
  - "Plan verification passed (after 1 revision)" — gates fired, revision applied, accepted, OR
  - "Plan verification concerns remained" — list residual concerns that the revision didn't resolve, OR
  - "Inline plan (no verification)" — when step 1 wrote the 3-bullet inline plan instead of dispatching safe-planner
- Any design decisions that were judgment calls
- Decisions deferred to user (if any)

### 5. Push Decision Gate (4-option terminal menu)

**STOP. Do not push. Ask the user to choose:**

1. **Push** — confirm target branch, then `git push` (per `~/.claude/CLAUDE.md` Git & Deployment).
2. **Hold** — leave commits local, no push, end session.
3. **Fix more** — reopen the loop with new findings.
4. **Discard** — destructive. Requires the user to literally type `discard` to confirm. Then `git reset --hard <pre-ship-sha>`.

Default to **Hold** if the user is ambiguous. Never default to Push.

## Anti-Patterns (will not do)

- Skip QA because "the change is small."
- Push because "the user said ship" (ship ≠ push — ship means "ready to push").
- Auto-fix MEDIUM/LOW QA findings without user input (silently expanding scope).
- Compress the report to "all green" without showing the actual commands and outputs.
