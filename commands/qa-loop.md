# /qa-loop — Iterative Audit-and-Fix Loop

Revision Gate that converges on a clean state. Iterates `qa-agent` audits + minimal fixes until no real bugs remain.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md
@~/.claude/rules/anti-patterns.md

## Workflow

### Step 1: Determine Scope

Identify what changed: `git diff` (or `git diff HEAD~1` if already committed). Note affected files and modules.

### Step 2: QA Loop (MAX_ITERATIONS = 10)

```
iteration = 0

LOOP:
  iteration += 1

  # 1. Dispatch qa-agent
  Pass: list of changed files + standard QA prompt
  Wait for one of:
    - ## VERIFICATION PASSED → BREAK, success
    - ## ISSUES FOUND → continue to Fix step
    - ## BLOCKED → investigate (env, scope, missing access), provide context, re-dispatch

  IF iteration >= MAX_ITERATIONS:
    BREAK — report unfixed bugs to user

  # 2. Fix found bugs (severity-ordered: critical first)
  For each bug:
    a. Read the file, understand the bug in context
    b. Apply minimal fix — NO refactoring of surrounding code
    c. If fix is unclear/risky, skip and note for user

  # 3. Verify build (Verification Gate Function)
  Run typecheck/build. If broken, fix the build error.

  # 4. Expand scope
  Re-run git diff. Add newly-touched files to the list.

  # 5. Loop
  GOTO LOOP
```

### Step 3: Report

- **Iterations run:** count
- **Bugs found and fixed:** file, line, what was wrong (one bullet each)
- **Bugs skipped:** any that were too risky or ambiguous
- **Final state:** clean / remaining issues with severity

## Verification Gate Function (per iteration)

Apply `~/.claude/rules/gates.md` Part 2 — every fix needs evidence:

1. State the verification command.
2. Run it in this turn.
3. Capture the actual output.
4. Evaluate against expected.
5. Report with the captured output.

"Should pass" / "looks fine" without a fresh command output = the gate failed and you must repeat.

## Anti-Patterns (will not do)

- Fix style issues (only real bugs).
- Refactor (minimal fixes only).
- Modify tests (unless the bug is in the test).
- Re-dispatch the same agent without changing context after a `## BLOCKED`.
- Loop indefinitely on the same bug — if it appears 3 times, skip and surface to user.
