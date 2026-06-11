# /plan — Plan Something (with Brainstorm + Principles Verification)

Standalone planning command. Dispatches `safe-planner`, then runs the Plan Verification Loop — the `plan-verify` workflow (brainstorm critique + principles grader in parallel, plus one revision pass) — before returning the final plan.

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

If `work_units ≤ 2` → **skip verification**. Log decision to `${RUN_DIR}/decisions.log` and jump to Step 5. (See `~/.claude/rules/plan-verification.md` for rationale on the simple count-based heuristic.)

### Step 4: Plan Verification Loop (via the `plan-verify` workflow)

The two gates + the single revision pass are autonomous (no user input), so they run as a deterministic workflow instead of hand-dispatched agents:

```
Workflow(name="plan-verify", args={ runDir: "${RUN_DIR}" })
```

The workflow (`~/.claude/workflows/plan-verify.js`) faithfully encodes `~/.claude/rules/plan-verification.md`:

- Runs **Gate 1 (brainstorm)** and **Gate 2 (outcomes-grader)** in parallel, both reading `${RUN_DIR}/task.md` + `${RUN_DIR}/plan.md`, returning schema-validated findings (model: opus, same as the prior inline dispatch).
- If brainstorm reports `hasSignificantConcerns` OR the grader reports any applicable item not passing, it dispatches `safe-planner` **once** to revise `${RUN_DIR}/plan.md` **in place** (cap: one revision — never loops).
- Returns:
  ```
  { passed, revised, revisionSummary, unresolvedConcerns[], brainstorm, principles, verificationMarkdown }
  ```

Handle the result:

1. **Write findings** — if the workflow ran the gates (no `error` field), write `result.verificationMarkdown` to `${RUN_DIR}/plan_verification.md`.
2. **Map the verification status** for Step 5:
   - `passed && !revised` → `PASSED in 0 revisions`
   - `revised && unresolvedConcerns.length == 0` → `PASSED after revision`
   - `revised && unresolvedConcerns.length > 0` → `CONCERNS REMAIN — see plan_verification.md`
3. **Log** the outcome (and any `unresolvedConcerns`) to `${RUN_DIR}/decisions.log`.

`safe-planner` overwrites `${RUN_DIR}/plan.md` in place, so Step 5 reads the final plan from the same path whether or not a revision happened. **Do NOT loop the revision** — one pass max, per `~/.claude/rules/plan-verification.md`.

**Fallback (workflows disabled / errored):** if the `plan-verify` workflow is unavailable, or returns an `error` field, fall back to the inline loop — dispatch `brainstorm` and `outcomes-grader` in parallel (single message, two Agent calls), then re-dispatch `safe-planner` once if either flags concerns, exactly as specified in the @-included `~/.claude/rules/plan-verification.md` (which has the verbatim gate prompts). Same opus model pins, same one-revision cap, then write `${RUN_DIR}/plan_verification.md` yourself from the combined findings.

### Step 5: Output the plan

Substitute the resolved `${RUN_DIR}` (e.g. `.claude/.plan/20260518-093015`) into every path below — print real paths, not placeholders. The `.claude/.plan/latest` symlink updated in Step 1 always points at the most-recent run, so users get a stable shortcut even though each invocation lives in its own dir.

**Build the copy-pasteable autopilot command:** read `${RUN_DIR}/task.md`, collapse all whitespace runs (including newlines) into single spaces, trim leading/trailing whitespace. The result is the task string to print after `/autopilot `. Example construction:

```bash
TASK_ONE_LINE=$(tr -s '[:space:]' ' ' < "${RUN_DIR}/task.md" | sed -e 's/^ //' -e 's/ $//')
```

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

Review the full plan: cat <RUN_DIR>/plan.md   (or: cat .claude/.plan/latest/plan.md)

To execute, copy-paste the line below. The `--plan=` flag tells /autopilot
to consume this exact plan, skipping its own Phase 1 (safe-planner decompose)
and Phase 1.5 (verification loop) — that work has already been done here.
Phase 0 (workspace, inventory, rubric) and Phase 2+ (implement, QA, commit)
still run normally.

/autopilot ${TASK_ONE_LINE} --plan=${RUN_DIR}/plan.md
```

**This last block is mandatory.** Every /plan invocation that reaches Step 5 (whether verification passed, was skipped as trivial, or finished with concerns remaining) MUST end with the literal `/autopilot ${TASK_ONE_LINE} --plan=${RUN_DIR}/plan.md` line as the final printed line. No exceptions — the user grabs this command without re-reading the task. Use the **resolved RUN_DIR**, not the `.claude/.plan/latest` symlink — a later `/plan` run would shift the symlink and silently re-target the user's autopilot invocation at a different plan. If `${RUN_DIR}/task.md` is somehow empty (Step 1 ABORT should have caught this), print `/autopilot <TASK MISSING — re-invoke /plan with a task description>` as a visible failure rather than skipping the line.

## Anti-Patterns (will not do)

- Skip the verification loop when work_units > 2 (the only skip criterion is the count — see `~/.claude/rules/plan-verification.md`)
- Loop the revision pass more than once (one retry max — avoid infinite refinement)
- Run gates 1 and 2 sequentially when they can run in parallel (the workflow runs them in parallel; the fallback must too)
- Use AskUserQuestion or any checkpoint type — /plan is autonomous within a single conversation
- Write to autopilot's `.autopilot/` directory — /plan uses its own `.claude/.plan/` workspace
- Auto-execute the plan after producing it — /plan stops at the plan, leaves execution to the user / `/autopilot`
