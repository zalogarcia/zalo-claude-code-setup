# Gates

Two distinct kinds of gates: **workflow gates** (when to advance/loop/stop in a multi-step orchestration) and the **Verification Gate Function** (when an agent claims a task is done).

---

## Part 1 — Workflow Gates

Adapted from gsd-build/get-shit-done. Every validation checkpoint maps to one of four types.

### Pre-flight Gate

**Purpose:** Validates preconditions before starting an operation.
**Behavior:** Blocks entry if conditions unmet. No partial work created.
**Recovery:** Fix the missing precondition, then retry.
**Examples:** Plan exists before execute; tests pass baseline before refactor; clean working tree before merge.

### Revision Gate

**Purpose:** Evaluates output quality and routes to revision if insufficient.
**Behavior:** Loops back to producer with specific feedback. Bounded by iteration cap (typically 3).
**Recovery:** Producer addresses feedback; checker re-evaluates. Escalates early if issue count does not decrease between consecutive iterations (stall detection). After max iterations, escalates unconditionally.
**Examples:** `qa-agent` reviewing implementation; spec-reviewer/code-quality-reviewer pair; `live-test` finding UI bugs.

### Escalation Gate

**Purpose:** Surfaces unresolvable issues to the human for a decision.
**Behavior:** Pauses workflow, presents options as a `checkpoint:decision` (see `~/.claude/rules/checkpoints.md`), waits for input.
**Recovery:** Developer chooses; workflow resumes on selected path.
**Examples:** Revision loop exhausted; merge conflict; ambiguous requirement.

### Abort Gate

**Purpose:** Terminates to prevent damage or waste.
**Behavior:** Stops immediately, preserves state, reports reason.
**Recovery:** Developer investigates root cause, fixes, restarts from checkpoint.
**Examples:** Context window critically low; verification finds critical missing deliverables; 3+ debug fixes failed (architecture is wrong, not the fix).

### Selection Heuristic

Start with pre-flight. If the check happens after work is produced, it is a revision gate. If the revision loop cannot resolve the issue, escalate. If continuing is dangerous, abort.

### Implementation Notes

- Pre-flight gates belong at workflow entry points. Cheap, deterministic.
- Revision gates always pair with an iteration cap. Expensive operations get fewer retries.
- Escalation gates are the safety valve between revision and abort.
- Abort gates preserve state so work can resume.

---

## Part 2 — The Verification Gate Function

Adapted from obra/superpowers `verification-before-completion`. **The single most important rule in this setup.**

### The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in **this turn**, you cannot claim it passes.

### The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete) in this turn
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

### Common Failures Table

| Claim                          | Requires                                                | Not Sufficient                     |
| ------------------------------ | ------------------------------------------------------- | ---------------------------------- |
| Tests pass                     | Test command output: 0 failures                         | Previous run, "should pass"        |
| Linter clean                   | Linter output: 0 errors                                 | Partial check, extrapolation       |
| Build succeeds                 | Build command: exit 0                                   | Linter passing, logs look good     |
| Bug fixed                      | Test original symptom: passes                           | Code changed, assumed fixed        |
| Regression test works          | Red-green cycle verified                                | Test passes once                   |
| Agent completed                | VCS diff shows changes                                  | Agent reports "success"            |
| Requirements met               | Line-by-line checklist                                  | Tests passing                      |
| Supabase edge deploy succeeded | `mcp__supabase__get_logs` shows no errors in last 5 min | `supabase functions deploy` exit 0 |
| Frontend renders correctly     | `live-test` agent screenshot + console clean            | Component compiles                 |

### Red Flags — STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!")
- About to commit/push/PR without running tests in this turn
- Trusting agent success reports without checking the diff
- Relying on partial verification
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification in this message**

### Bottom Line

Run the command. Read the output. THEN claim the result. Non-negotiable.
