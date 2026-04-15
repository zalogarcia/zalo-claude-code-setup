# /ship — Full Feature Delivery

Plan → implement → QA → wait for explicit push approval. The orchestrator owns sequencing; subagents do the work.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/anti-patterns.md
@~/.claude/rules/checkpoints.md

## Workflow

### 1. Plan

If the change touches 3+ files, dispatch `safe-planner`. Otherwise, write a 3-bullet inline plan: affected files, expected behavior, edge cases.

Wait for `## PLAN READY` (or `## NEEDS DECISION` → resolve with user before proceeding).

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
