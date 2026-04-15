# /tdd — Test-Driven Development

Strict RED → GREEN → REFACTOR. Adapted from obra/superpowers `test-driven-development`.

## Authoritative Rules

@~/.claude/rules/gates.md
@~/.claude/rules/anti-patterns.md
@~/.claude/rules/verification-patterns.md

## The Iron Law

```
┌─────────────────────────────────────────────────────────────┐
│  WRITE THE TEST FIRST. WATCH IT FAIL. WRITE MINIMAL CODE.   │
│                                                             │
│  Wrote code before the test? DELETE IT. Start over.         │
│  No exceptions.                                             │
└─────────────────────────────────────────────────────────────┘
```

## Red Flags — STOP if you find yourself thinking:

- "I'll write the test after, the implementation is obvious"
- "This is too simple to need a test"
- "I'll skip the failing-test step and just verify it passes"
- "The test is hard to write, I'll just implement and check manually"
- "I'll write a few tests upfront and implement them all at once"

Each red flag = you're about to break the law. Stop, delete what you wrote, restart at RED.

## Rationalization Table

| What you'll think                        | Reality                                                                |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| "The test will be obvious from the code" | The test reveals the API. Writing code first locks in the wrong API.   |
| "It's just a small helper"               | Small helpers are where untested edge cases hide.                      |
| "I already know it works"                | If you didn't watch it fail, you didn't prove the test tests anything. |
| "Tests would slow me down here"          | The 2 minutes you save now costs 20 minutes when the regression hits.  |
| "I'll batch the tests at the end"        | Batched tests = tests written to pass, not tests that reveal design.   |

## The 5-Step Bite-Sized Template

For each behavior:

### 1. RED — Write ONE failing test

- Pick the smallest behavior worth its own test.
- Write the test.
- Run the test. **Watch it fail.** If it doesn't fail → the test isn't testing new behavior; fix the test before continuing.

### 2. GREEN — Write minimal code to pass

- Write the simplest implementation that makes that one test pass. No more.
- Run the test. Confirm it passes.
- Run the full test suite. Confirm no regressions.

### 3. REFACTOR — Clean up while green

- Improve names, extract duplication, simplify branches.
- Run the full test suite after each refactor step.
- If a test fails during refactor: revert the refactor, don't "fix" the test.

### 4. COMMIT

- Commit the increment with a message describing the behavior added.
- One test + impl per commit when practical.

### 5. NEXT BITE

- Move to the next behavior. Repeat from step 1.

## Anti-Patterns (will not do)

- Write impl before test (per Iron Law — delete and restart).
- Write 5 tests upfront, then 5 implementations.
- Skip the failing-test step ("I know it'll fail").
- Modify the test to make it pass (if the impl is wrong, fix the impl).
- Ignore the full suite after a GREEN — regressions hide in adjacent tests.

## Verification Before Done

Apply `~/.claude/rules/gates.md` Part 2 Verification Gate Function:

- Run the full test suite — capture the actual output.
- Confirm the count of new tests added matches the count of behaviors implemented.
- Report: tests added (file:line for each), commands run, outputs.

Never claim TDD complete without showing the final test-suite output.
