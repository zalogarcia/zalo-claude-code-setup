# Agent Contracts

Completion markers and return contract for `~/.claude/agents/`. Skills/orchestrators detect agent completion by regex-matching these H2 markers in the agent's final output.

## Marker Registry

| Agent                 | Markers                                                                              |
| --------------------- | ------------------------------------------------------------------------------------ |
| `frontend-specialist` | `## IMPLEMENTATION COMPLETE` / `## IMPLEMENTATION DONE_WITH_CONCERNS` / `## BLOCKED` |
| `qa-agent`            | `## VERIFICATION PASSED` / `## ISSUES FOUND` / `## BLOCKED`                          |
| `safe-planner`        | `## PLAN READY` / `## NEEDS DECISION` / `## BLOCKED`                                 |
| `brainstorm`          | `## EXPLORATION COMPLETE`                                                            |
| `live-test`           | `## UI VERIFIED` / `## UI ISSUES FOUND` / `## BLOCKED`                               |
| `bug-fix`             | `## ROOT CAUSE FOUND` / `## INVESTIGATION INCOMPLETE` / `## BLOCKED`                 |
| `image-craft-expert`  | `## IMAGE GENERATED` / `## GENERATION FAILED`                                        |

## Marker Rules

1. Markers must appear as H2 headings (`## `) at the start of a line in the agent's **final** output.
2. Use ALL-CAPS to maximize regex reliability.
3. Exactly one terminal marker per dispatch — agents that need multiple states pick the most recent applicable one.
4. The marker line stands alone; details follow underneath.

## Status Code Body Protocol

After the H2 marker, the agent's body must signal one of four states (adapted from obra/superpowers `subagent-driven-development`):

**DONE** — task complete, all acceptance criteria met. Proceed.

**DONE_WITH_CONCERNS** — work complete but agent flags doubts.

- If concerns are about correctness or scope → orchestrator addresses before proceeding.
- If concerns are observations (e.g., "this file is getting large") → note and proceed.

**NEEDS_CONTEXT** — agent needs information that wasn't provided. Orchestrator supplies it and re-dispatches.

**BLOCKED** — agent cannot complete. Orchestrator assesses:

1. Context problem → provide more context, re-dispatch with same model.
2. Reasoning gap → re-dispatch with more capable model.
3. Task too large → split into smaller pieces.
4. Plan is wrong → escalate to human (use `~/.claude/rules/checkpoints.md` checkpoint:decision).

**Never** ignore an escalation. Never re-dispatch the same model without changing context. If the agent said it's stuck, something must change.

## Standard Return Template

```markdown
## <MARKER>

**Status:** DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED

**Summary:** [1-2 sentences]

**Files changed:** [list]

**Verification:** [what was tested + result]

**Concerns / Blockers:** [if any]
```

## Why This Matters

Without contracts, subagent returns are prose blobs the orchestrator must re-read entirely. Contracts let:

- The main thread regex-detect terminal state and route accordingly.
- Multi-stage pipelines (implementer → spec-reviewer → code-quality-reviewer) chain reliably.
- The user see at a glance what the agent actually decided.

Treat the marker as a public commitment. If the agent emits `## VERIFICATION PASSED`, the verification was actually run.
