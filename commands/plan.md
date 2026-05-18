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

Each `/plan` invocation gets its own subdirectory under `.claude/.plan/<run-id>/` so concurrent runs in the same repo can't clobber each other. The parent `.claude/.plan/` is shared (separate from autopilot's `.autopilot/`); each run writes only inside its own `<run-id>` dir.

```bash
mkdir -p .claude/.plan
# `$$` PID suffix prevents same-wallclock-second RUN_ID collisions between
# concurrent /plan invocations (timestamp alone has 1s resolution).
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
RUN_DIR=".claude/.plan/${RUN_ID}"
mkdir -p "$RUN_DIR"
echo "<task verbatim>" > "${RUN_DIR}/task.md"

# Atomic "latest" symlink update — `mv` over a symlink is rename(2), POSIX-atomic.
# Per-PID temp name (`latest.tmp.$$`) prevents two concurrent runs from racing
# on a shared temp filename and producing dangling or mis-pointing symlinks.
ln -sfn "$RUN_ID" ".claude/.plan/latest.tmp.$$" \
  && mv -f ".claude/.plan/latest.tmp.$$" .claude/.plan/latest
```

Throughout the rest of this workflow, `${RUN_DIR}` refers to the resolved path `.claude/.plan/<run-id>/` for this invocation. The orchestrator substitutes the actual path when constructing agent prompts — agents see the literal path (e.g. `.claude/.plan/20260518-093015/plan.md`), not the placeholder.

### Step 2: Dispatch safe-planner

Dispatch `safe-planner` (model: "opus") with:

```
Task: (read ${RUN_DIR}/task.md)

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

Output as structured markdown to ${RUN_DIR}/plan.md.

Emit ## PLAN READY when written.
```

Wait for `## PLAN READY`. Verify file exists and is non-empty before proceeding.

### Step 3: Skip heuristic check

Parse `${RUN_DIR}/plan.md` and count work units.

If `work_units ≤ 2` → **skip verification**. Log decision to `${RUN_DIR}/decisions.log` and jump to Step 6. (See `~/.claude/rules/plan-verification.md` for rationale on the simple count-based heuristic.)

### Step 4: Plan Verification Loop (per `~/.claude/rules/plan-verification.md`)

Run **Gate 1 (brainstorm-vet)** and **Gate 2 (principles-vet via outcomes-grader)** in **parallel** — they're independent reads of the same plan, no shared state, no data dependency. Single message with two Agent calls.

**Gate 1 — Brainstorm:**

```
Dispatch brainstorm (model: "opus"):

  Apply your critical-thinking pass to this plan.

  Original task: (read ${RUN_DIR}/task.md)
  Plan: (read ${RUN_DIR}/plan.md)

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

  Artifact: (read ${RUN_DIR}/plan.md)
  Rubric: (read ~/.claude/rules/engineering-principles.md)

  Per-item PASS / FAIL / AMBIGUOUS with quoted evidence from the plan.
  Mark items not applicable to this plan as PASS.

  Emit ## OUTCOMES PASSED if every applicable item passes.
  Emit ## OUTCOMES UNMET with FAIL details if any fail.
```

### Step 5: Combined revision pass (if needed)

Wait for both markers. Combine findings:

- If brainstorm has no significant concerns AND grader emits `## OUTCOMES PASSED` → both gates passed, no revision needed. Skip to Step 6.
- If either flagged concerns → write `${RUN_DIR}/plan_verification.md` with combined findings, then re-dispatch `safe-planner` ONCE with:

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

If the revision still has unresolved concerns from the original review, log `plan_verification_max_iterations_hit` to `${RUN_DIR}/decisions.log` and proceed with the best version. Note unresolved concerns in the final output.

### Step 6: Output the plan

Substitute the resolved `${RUN_DIR}` (e.g. `.claude/.plan/20260518-093015`) into every path below — print real paths, not placeholders. The `.claude/.plan/latest` symlink updated in Step 1 always points at the most-recent run, so users get a stable shortcut even though each invocation lives in its own dir.

Print to terminal:

```
Plan ready: <RUN_DIR>/plan.md
Shortcut:   .claude/.plan/latest/plan.md  (symlink → this run)
Verification: <PASSED in 0 revisions | PASSED after revision | SKIPPED (trivial) | CONCERNS REMAIN — see plan_verification.md>

Summary:
  Work units: <N>
  Batches: <M>
  Files touched: <K>
  Migrations: <yes/no>
  Testing strategy: <one line>

Next steps:
  - Review the full plan: cat <RUN_DIR>/plan.md   (or: cat .claude/.plan/latest/plan.md)
  - To execute, copy the task description (not the plan) and run /autopilot <task>.
    It will produce its own plan from the task — but since it includes the same
    Plan Verification Loop, the result will converge with what /plan produced here.
  - The plan in <RUN_DIR>/plan.md is for your review/handoff/reference.
    It is NOT auto-consumed by /autopilot.
```

## Anti-Patterns (will not do)

- Skip the verification loop when work_units > 2 (the only skip criterion is the count — see `~/.claude/rules/plan-verification.md`)
- Loop the revision pass more than once (one retry max — avoid infinite refinement)
- Run gates 1 and 2 sequentially when they can run in parallel
- Use AskUserQuestion or any checkpoint type — /plan is autonomous within a single conversation
- Write to autopilot's `.autopilot/` directory — /plan uses its own `.claude/.plan/` workspace
- Auto-execute the plan after producing it — /plan stops at the plan, leaves execution to the user / `/autopilot`
