---
name: multi-edit
description: Heavyweight planning path for refactors, renames, migrations, and cross-module changes that are hard to roll back. Runs safe-planner, optionally brainstorm, then blocks on human approval before any edit. Triggers on "refactor", "rename across", "migrate", "restructure", "move X out of", "extract into shared", or any change that crosses module boundaries. Not for new features (use /ship) or single-file fixes.
---

Purpose: add a stress-test + approval gate on top of the global safe-planner rule, for changes where a wrong plan is expensive to undo.

**Termination contract**: this skill has exactly one success condition — the `qa-loop` skill returns clean after the final edit. Any other exit is a failure. Do not declare the multi-edit complete until qa-loop reports zero findings.

## Step 1 — safe-planner

Launch the `safe-planner` agent with this brief template:

```
REQUEST: <verbatim user ask>
CONTEXT: <1-2 sentences on why + constraints>
SCOPE FENCE: <what is explicitly out of scope>
DELIVERABLE: file list with per-file change summary, dependency graph,
top 3 risks, rollback steps, execution order. Flag any ambiguity you
can't resolve.
```

## Step 2 — brainstorm (conditional)

Run only if safe-planner surfaces design choices, tradeoffs, or unresolved ambiguity. For mechanical changes (pure renames, type additions, obvious extractions) skip and note **why** in the proposal.

Brief: original request + one-paragraph summary of the plan + ask to challenge assumptions, find the cheapest path, and flag second-order effects.

If brainstorm contradicts safe-planner, present **both options** in Step 3 as a choice — do not pick for the user.

## Step 3 — Approval gate

Show:

- **Plan** — files touched + approach
- **Risks** — top 3 + rollback
- **Open questions** — anything the human must decide

Then ask for approval explicitly.

Proceed only on an **unconditional green light with no new constraints or scope changes**. "Yes, but...", "Go ahead and also...", or partial approval = stop and re-confirm the updated plan. If in doubt, ask.

## Step 4 — Execute

Follow the plan. Run typecheck after each logically-complete subset, not just at the end. If reality diverges from the plan mid-execution, stop, report current state (changed / rolled back / untouched), and re-plan before continuing.

## Step 5 — qa-loop (mandatory, non-skippable)

Invoke the `qa-loop` skill. This is the terminal step of multi-edit and it is non-negotiable.

- Do **not** substitute the global CLAUDE.md "Verification & QA" section for this step. That section covers single-file edits; multi-edit requires the full iterative qa-loop.
- If qa-loop surfaces bugs, fix them and re-invoke qa-loop. Repeat until it returns clean.
- Only after qa-loop reports zero findings may you declare the multi-edit complete.
- A passing typecheck/build alone is not sufficient — qa-loop must run and terminate clean.
