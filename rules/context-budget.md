# Context Budget

Adapted from gsd-build/get-shit-done `references/context-budget.md`. Use this to self-regulate context usage and to recognize degradation before it becomes catastrophic.

## Context Degradation Tiers

Monitor your context usage and adjust behavior accordingly:

| Tier          | Usage  | Behavior                                                                                                           |
| ------------- | ------ | ------------------------------------------------------------------------------------------------------------------ |
| **PEAK**      | 0–30%  | Full operations. Read bodies, spawn multiple agents, inline results freely.                                        |
| **GOOD**      | 30–50% | Normal operations. Prefer frontmatter / summary reads. Delegate aggressively.                                      |
| **DEGRADING** | 50–70% | Economize. Frontmatter-only reads. Minimal inlining of subagent results. Warn user about budget.                   |
| **POOR**      | 70%+   | Emergency mode. Checkpoint progress immediately. No new reads unless critical. Suggest `/compact` or session save. |

## Degradation Warning Signs

Quality degrades **gradually before** panic thresholds fire. Watch for these early signals:

- **Silent partial completion** — you claim a task is done but implementation is incomplete. Self-check catches file existence but not semantic completeness. **Always verify against the must-haves**, not just that files exist.
- **Increasing vagueness** — you start writing phrases like "appropriate handling" or "standard patterns" instead of specific code. This indicates context pressure even before budget warnings fire.
- **Skipped steps** — you omit protocol steps you'd normally follow. If a procedure has 8 steps but you only report 5, suspect context pressure.
- **Forgetting earlier decisions** — you re-litigate a choice the user already locked in. Stop, re-read the relevant rule or earlier message.
- **Sloppy verification** — you skip the Verification Gate Function (`~/.claude/rules/gates.md` Part 2). This is the most dangerous symptom because it hides itself.

## Mitigation

When you detect degradation:

1. **Surface it to the user.** "Context is getting heavy — I noticed [symptom]. Recommend we [checkpoint / split task / compact]."
2. **Stop starting new complex work.** Finish the current step cleanly, then pause.
3. **Delegate aggressively.** A fresh subagent = clean 200K context.
4. **Read summaries, not bodies.** Frontmatter, exit codes, last 20 lines of output.
5. **At POOR (70%+):** save state via `/session-save` or write a `PLAN.md` checkpoint file before any further work.

## Cannot-Verify-Semantic-Correctness

When delegating to a subagent, the orchestrator cannot verify semantic correctness of the agent's output — only structural completeness (the H2 marker, the diff exists, the test passed). This is a fundamental limitation. Mitigate with:

- Strict acceptance criteria in the dispatch prompt.
- Spot-check verification by the orchestrator on critical paths.
- Two-stage review (spec-compliance then code-quality) for high-stakes work.
