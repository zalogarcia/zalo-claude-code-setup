# Plan Verification Loop

After `safe-planner` emits `## PLAN READY`, run two verification gates **before** acting on the plan. Both gates use fresh-context subagents (the value of brainstorm/grader pass is the second-opinion dynamic — same-model self-critique is weaker).

## When to apply

Any orchestrator that dispatches `safe-planner` and receives `## PLAN READY` MUST run this loop before proceeding to implementation. This includes:

- `/autopilot` Phase 1
- `/ship` (when the conditional safe-planner path is taken)
- `/plan` (standalone)
- Any future command that dispatches `safe-planner`

## Path-agnostic protocol

Each consumer has its own workspace for plans and verification artifacts:

| Orchestrator | Plan path                      | Verification findings path           |
| ------------ | ------------------------------ | ------------------------------------ |
| `/autopilot` | `.autopilot/plan.md`           | `.autopilot/plan_verification.md`    |
| `/plan`      | `.claude/.plan/plan.md`        | `.claude/.plan/plan_verification.md` |
| `/ship`      | conversation context (no file) | inline (no file; surface in report)  |

Below, `{plan_path}` refers to the consumer's stored plan location (or "the plan content verbatim" when the consumer keeps the plan inline). `{findings_path}` refers to its verification findings file (or inline). Substitute when applying.

## Skip heuristic

**Skip both gates if** the plan has **≤ 2 work units**.

Trivial plans don't benefit from verification — the verification cost (~$2-4, 5-7 min) exceeds the marginal improvement. The orchestrator decides by counting `work_units` after parsing the safe-planner output.

Yes, this misses some 1-2 unit plans with big architectural impact (e.g., "add a queue" as a single work unit). Trade-off accepted: the QA loop catches downstream issues, the user can opt-in by running `/plan` explicitly when they want verification on a small task. A more nuanced heuristic would require a structured `architectural_changes` field from `safe-planner` — we may add that later if false negatives matter in practice.

Log the skip to `decisions.log` as `plan_verification_skipped: trivial`.

## The two gates

**Run in parallel** — single message with two Agent calls. They're independent reads of the same plan; no shared state, no data dependency. The orchestrator integrates findings after both return.

### Gate 1 — Brainstorm-vet (correctness & completeness)

Dispatch `brainstorm` agent with this prompt shape:

```
We just produced a plan via safe-planner. Apply your critical-thinking pass.

## Original task
{task_description}

## Plan to evaluate
{full plan content — pass verbatim or read from {plan_path}}

## What I want
- Apply inversion: "what if the opposite assumption were true?"
- Apply simplification cascade: "what would eliminate 5+ steps with one insight?"
- Apply scale game: "would this work at 0.1x and 10x?"
- Apply meta-pattern recognition: "have I seen this shape elsewhere — does the established pattern apply?"
- Identify hidden assumptions, missing considerations, scope creep, premature optimization
- Identify single points of failure, unhandled edge cases, missing rollback paths
- Don't rubber-stamp. If the plan is sound, say so concisely. If you find concerns, list them with severity.

Emit ## EXPLORATION COMPLETE when done.
```

Wait for `## EXPLORATION COMPLETE`. Findings will be parsed alongside Gate 2's after both return.

### Gate 2 — Principles-vet (alignment with stated standards)

Dispatch `outcomes-grader` agent with the plan as the artifact and `~/.claude/rules/engineering-principles.md` as the rubric:

```
You are grading a PLAN (markdown describing intended work, not code).
Apply your "plan-grading mode" per outcomes-grader.md.

## Artifact (the plan to grade)
{full plan content — pass verbatim or read from {plan_path}}

## Rubric
(read ~/.claude/rules/engineering-principles.md)

For each rubric item with an "Applicable when:" clause, first determine
applicability. If not applicable to this plan, mark PASS with reason
"not applicable: {clause condition not met}".

For applicable items, return PASS / FAIL with concrete evidence quoted
from the plan. Use AMBIGUOUS only if applicability itself is unclear.

Evidence must be quoted plan text — do NOT run greps, file checks, or
build commands; the plan describes work that doesn't exist on disk yet.

Emit ## OUTCOMES PASSED if every applicable item passes.
Emit ## OUTCOMES UNMET with per-item FAIL reasons if any fail.
```

Wait for marker.

### Combined revision pass

After both gates return, the **orchestrator** (not the agents) writes a combined `{findings_path}` (when applicable — `/ship` keeps it inline) containing:

```markdown
# Plan Verification Findings — <timestamp>

## Brainstorm findings (Gate 1)

<verbatim from brainstorm return>

## Principles findings (Gate 2)

<failed rubric items + "what's missing" lines>
```

Decision tree:

- **Brainstorm has no significant concerns AND `## OUTCOMES PASSED`** → both gates passed. Log `plan_verification_passed: 0 revisions` to `decisions.log`. Proceed to next phase.
- **Either gate flagged concerns** → re-dispatch `safe-planner` ONCE with combined findings:

  ```
  The plan you produced was reviewed. Issues to address:

  ## Brainstorm critique
  {brainstorm findings, verbatim}

  ## Principles violations
  {failed rubric items + grader's "what's missing" lines}

  Revise the plan to address each issue. Keep what works. Don't expand scope
  beyond the original task. Emit ## PLAN READY when revised.
  ```

  Wait for revised `## PLAN READY`. **Do NOT loop again.** Cap at one revision pass per plan. The user wanted brainstorm-polish, not infinite refinement.

  If the revision still fails the gates (re-running them is optional — most consumers skip and trust the revision), log to `decisions.log` as `plan_verification_max_iterations_hit` and proceed with the best plan available. Surface unresolved items in the consumer's final report under "Plan Verification Concerns".

## Failure modes to avoid

- **Don't loop on revision** — one retry maximum. Iteration is for execution, not planning.
- **Don't bypass Gate 2 when Gate 1 fails** — both gates inform the single revision pass; collect findings from both.
- **Don't substitute self-critique for fresh-context dispatch** — the value of these gates is the second-opinion dynamic; collapsing them into safe-planner's own output loses that.
- **Don't skip the loop because "the task is small"** — apply the explicit skip heuristic (≤2 work units). Other forms of "small" are too vague.
- **Don't have agents write findings to disk** — agents return findings in their response body; the orchestrator collects and writes the combined file.

## Cost & time budget

Per plan-verification loop (full both-gates + 1 revision pass):

- Brainstorm (Opus, effort:high): ~2-3 min, ~$0.50-$1.50
- Outcomes-grader (Opus, effort:high): ~1-2 min, ~$0.50-$1.00
- Revision dispatch (if needed): ~1-2 min, ~$0.30-$0.80
- **Total: 4-7 min, ~$2-4 per loop**

Skip heuristic eliminates this overhead for trivial plans where verification is cargo cult.
