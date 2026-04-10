# /ship - Full Feature Delivery

You are executing a complete plan-build-QA-push workflow. Follow every step — do NOT skip QA.

## Workflow

1. **Plan** — Summarize the planned changes: list affected files, expected behavior, and edge cases. For complex changes (3+ files), use `safe-planner` agent.

2. **Implement** — Make all code changes across all files. Use `frontend-specialist` agent for any UI work.

3. **QA Loop** — Run this sequence and fix ALL issues before proceeding:
   - Kill stale processes: `pkill -f 'next dev' || true`
   - TypeScript: `npx tsc --noEmit`
   - Build: `npm run build`
   - Tests: run relevant test suite if it exists
   - For frontend changes: use `live-test` agent to verify visually
   - Repeat until zero errors

4. **Report** — Present a summary of all changes to the user:
   - Files changed with brief description of each
   - QA results (all green)
   - Any design decisions you made

5. **Wait for approval** — **STOP HERE.** Do NOT push, deploy, or merge. Ask the user:
   - "Ready to push? Which branch?"
   - Only proceed when they explicitly approve

## Rules

- Never push without explicit user approval
- Never skip the QA loop — zero tolerance for shipping broken code
- If QA reveals issues, fix them silently and re-run. Only report when everything passes.
- Commit with clear messages as you go, but do NOT push until approved
