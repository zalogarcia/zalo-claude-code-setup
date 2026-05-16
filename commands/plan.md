# /plan — Plan Something (with Brainstorm + Principles Verification)

Standalone planning command. Dispatches `safe-planner`, then runs the Plan Verification Loop (brainstorm critique + principles grader) before returning the final plan.

Use this when you want a high-quality plan but **don't** want the full `/autopilot` execution pipeline — e.g., scoping a feature for a future session, getting a second opinion on an approach, or producing a plan to hand off.

For trivial single-file edits, skip /plan and just write the change. The verification overhead isn't worth it for plans with ≤2 work units (the loop's skip heuristic catches this anyway, but you can save the safe-planner dispatch by going inline).

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/plan-verification.md
@~/.claude/rules/engineering-principles.md
@~/.claude/rules/anti-patterns.md
@~/.claude/rules/questioning.md

## Invocation

```
/plan <task description>
```

Examples:

- `/plan add Stripe Connect onboarding to the operator settings page`
- `/plan migrate the auth middleware off NextAuth and onto Supabase Auth`
- `/plan implement push notifications for the mobile app`

## Workflow

### Step 1: Pre-flight

Verify a task description was provided. If empty → ABORT: "Usage: /plan <task description>".

Save task to `.claude/.plan/task.md` (working directory `.claude/.plan/` — separate from autopilot's `.autopilot/`).

```bash
mkdir -p .claude/.plan
echo "<task verbatim>" > .claude/.plan/task.md
```

### Step 2: Dispatch safe-planner

Dispatch `safe-planner` (model: "opus") with:

```
Task: (read .claude/.plan/task.md)

Decompose into work units. For each:
1. ID (wu-1, wu-2, ...)
2. Description (one line)
3. Files to create or modify (relative from repo root, no globs)
4. Dependencies (which work unit IDs must complete first, or "none")
5. Agent type: frontend-specialist (UI/styling) or general-purpose (backend/logic)
6. Complexity: trivial / moderate / complex

Group into parallelizable batches (Batch 0: shared types; Batch 1: no deps; etc.)

Identify:
- Database migrations needed (must follow ~/.claude/rules/database-safety.md)
- Testing strategy
- Risks and rollback plan for irreversible changes

Output as structured markdown to .claude/.plan/plan.md.

Emit ## PLAN READY when written.
```

Wait for `## PLAN READY`. Verify file exists and is non-empty before proceeding.

### Step 3: Skip heuristic check

Parse `.claude/.plan/plan.md` and count work units.

If `work_units ≤ 2` → **skip verification**. Log decision to `.claude/.plan/decisions.log` and jump to Step 6. (See `~/.claude/rules/plan-verification.md` for rationale on the simple count-based heuristic.)

### Step 4: Plan Verification Loop (per `~/.claude/rules/plan-verification.md`)

Run **Gate 1 (brainstorm-vet)** and **Gate 2 (principles-vet via outcomes-grader)** in **parallel** — they're independent reads of the same plan, no shared state, no data dependency. Single message with two Agent calls.

**Gate 1 — Brainstorm:**

```
Dispatch brainstorm (model: "opus"):

  Apply your critical-thinking pass to this plan.

  Original task: (read .claude/.plan/task.md)
  Plan: (read .claude/.plan/plan.md)

  - Apply inversion, simplification cascade, scale game, meta-pattern recognition
  - Identify hidden assumptions, missing considerations, scope creep
  - Identify single points of failure, unhandled edge cases, missing rollback
  - If the plan is sound, say so concisely. If concerns exist, list with severity.

  Emit ## EXPLORATION COMPLETE.
```

**Gate 2 — Principles grader:**

```
Dispatch outcomes-grader (model: "opus"):

  Grade this PLAN (not code) against the engineering-principles rubric.

  Artifact: (read .claude/.plan/plan.md)
  Rubric: (read ~/.claude/rules/engineering-principles.md)

  Per-item PASS / FAIL / AMBIGUOUS with quoted evidence from the plan.
  Mark items not applicable to this plan as PASS.

  Emit ## OUTCOMES PASSED if every applicable item passes.
  Emit ## OUTCOMES UNMET with FAIL details if any fail.
```

### Step 5: Combined revision pass (if needed)

Wait for both markers. Combine findings:

- If brainstorm has no significant concerns AND grader emits `## OUTCOMES PASSED` → both gates passed, no revision needed. Skip to Step 6.
- If either flagged concerns → write `.claude/.plan/plan_verification.md` with combined findings, then re-dispatch `safe-planner` ONCE with:

```
The plan you produced was reviewed. Issues to address:

## Brainstorm critique
{brainstorm findings, verbatim}

## Principles violations
{grader's failed rubric items}

Revise plan.md to address each issue. Keep what works. Don't expand scope.
Emit ## PLAN READY when revised.
```

Wait for revised `## PLAN READY`. **Do NOT loop again** — cap at one revision per plan.

If the revision still has unresolved concerns from the original review, log `plan_verification_max_iterations_hit` to `.claude/.plan/decisions.log` and proceed with the best version. Note unresolved concerns in the final output.

### Step 6: Output the plan

Print to terminal:

```
Plan ready: .claude/.plan/plan.md
Verification: <PASSED in 0 revisions | PASSED after revision | SKIPPED (trivial) | CONCERNS REMAIN — see plan_verification.md>

Summary:
  Work units: <N>
  Batches: <M>
  Files touched: <K>
  Migrations: <yes/no>
  Testing strategy: <one line>

Next steps:
  - Review the full plan: cat .claude/.plan/plan.md
  - To execute, copy the task description (not the plan) and run /autopilot <task>.
    It will produce its own plan from the task — but since it includes the same
    Plan Verification Loop, the result will converge with what /plan produced here.
  - The plan in .claude/.plan/plan.md is for your review/handoff/reference.
    It is NOT auto-consumed by /autopilot.
```

## Anti-Patterns (will not do)

- Skip the verification loop when work_units > 2 (the only skip criterion is the count — see `~/.claude/rules/plan-verification.md`)
- Loop the revision pass more than once (one retry max — avoid infinite refinement)
- Run gates 1 and 2 sequentially when they can run in parallel
- Use AskUserQuestion or any checkpoint type — /plan is autonomous within a single conversation
- Write to autopilot's `.autopilot/` directory — /plan uses its own `.claude/.plan/` workspace
- Auto-execute the plan after producing it — /plan stops at the plan, leaves execution to the user / `/autopilot`
