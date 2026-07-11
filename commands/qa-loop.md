# /qa-loop — Iterative Audit-and-Fix Loop

Revision Gate that converges on a clean state. Each iteration runs a parallel, adversarially-verified audit (the `qa-audit` workflow) + minimal fixes, until no real bugs remain.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md
@~/.claude/rules/anti-patterns.md

## Workflow

### Step 1: Determine Scope

Identify what changed: `git diff` (or `git diff HEAD~1` if already committed). Note affected files and modules.

Tier note: /qa-loop IS the full tier of the multi-file QA mandate. If the change set qualifies for the light tier (≤150 changed lines, behavior-preserving, no auth/payment/data-deletion/migration paths, no new deps — see `~/.claude/CLAUDE.md` "3+ file edits"), the orchestrator may run a single `qa-agent` dispatch instead of invoking this loop. Once /qa-loop is invoked, run the full loop — don't downgrade mid-flight.

### Step 2: QA Loop (MAX_ITERATIONS = 10)

```
iteration = 0

LOOP:
  iteration += 1

  # 1. Audit — parallel fan-out + adversarial verify
  Invoke the read-only `qa-audit` workflow:
      Workflow(name="qa-audit", args={ files: <changed files>, base: <HEAD or HEAD~1> })
  It runs 6 finder agents (correctness, wiring, error-handling, security, stubs,
  types-edges) in parallel, then has two skeptics adversarially verify each finding,
  returning ONLY confirmed bugs, pre-sorted critical-first:
      { verdict, untrusted, deadFinders, confirmed: [ {file, line, severity, title,
        description, evidence, suggestedFix} ], unverified: [...], stats, scope }
  Map the structured result — CHECK `untrusted` BEFORE `confirmed` (false-green guard):
    - untrusted == true → NOT a pass, regardless of confirmed.length. Finder or
      skeptic agents died mid-run (usage limit / API error) and their portions never
      ran. Resume the SAME run: Workflow(scriptPath, resumeFromRunId=<run id>) —
      cached agents replay free, only dead ones re-run. Does not consume an
      iteration. Never report "clean" from an untrusted verdict (2026-07 audit:
      this exact false green nearly shipped real bugs twice).
    - untrusted == false AND confirmed.length == 0 → BREAK, success (clean)
    - confirmed.length  > 0  → continue to Fix step (fix confirmed; `unverified`
      findings re-verify on the resumed/next audit — they are neither confirmed
      nor refuted)
    - workflow disabled / errors → FALLBACK to a single qa-agent dispatch:
        Pass changed files + standard QA prompt; wait for
        ## VERIFICATION PASSED / ## ISSUES FOUND / ## BLOCKED (prior behavior).

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

### Detection backend (`qa-audit` workflow)

The audit step delegates to `~/.claude/workflows/qa-audit.js` — fan-out across 6 bug dimensions + 2-skeptic adversarial verification. A finding is confirmed only if **neither** skeptic refutes it (uncertain → refuted), so the loop only ever fixes high-confidence bugs. The workflow is **read-only**: it never edits files. The Fix step below owns all mutations, kept sequential and minimal per `~/.claude/rules/when-to-parallelize.md` (no parallel implementation agents on shared files).

- Dynamic workflows are a research preview and may be disabled — the loop falls back to a single `qa-agent` automatically (no behavior change when off).
- In default permission mode the first run prompts for approval; choose "don't ask again for qa-audit in this project" so it doesn't prompt every iteration.

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
