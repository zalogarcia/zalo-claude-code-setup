# When to Parallelize Subagents

Adapted from obra/superpowers `dispatching-parallel-agents`. Claude Code's `Agent` tool runs multiple invocations concurrently when called in a single message — use this rule to decide when that's appropriate.

## The Four Criteria

Dispatch agents in parallel only when **ALL FOUR** are true:

1. **2+ independent task domains** — failures, files, or questions belong to different subsystems.
2. **No shared state** — agents won't read or write the same files.
3. **Each problem is self-describable** — you can give each agent everything it needs without reference to the others' work.
4. **You only need to coordinate afterward** — the orchestrator integrates results once they all return; no mid-stream handoff.

If any criterion fails → sequential or single agent.

## When to Parallelize

- 3+ test files failing with **different root causes** (separate subsystems).
- Multiple subsystems broken independently.
- Multiple research questions with no overlap (e.g., "what does library X do" + "how does file Y work" + "what's the API contract for Z").
- Multiple non-interacting code-quality audits (one agent per directory).

## When NOT to Parallelize

- Failures are related — fixing one might fix others.
- You need to understand full system state first — investigation is sequential.
- Agents would touch the same files (merge conflicts, race conditions on writes).
- One agent's output is another's input — that's a pipeline, not parallel.
- High-stakes implementation work — single careful agent beats two confused ones.

## Agent Prompt Structure for Parallel Dispatch

Each parallel agent prompt must be:

1. **Focused** — one clear problem domain.
2. **Self-contained** — all context needed; no "see the other agent" references.
3. **Specific about output** — what marker to emit, what to return.

Common mistakes:

- Too broad → agent gets lost.
- No context → agent doesn't know where the code lives.
- No constraints → agent refactors everything.
- Vague output → orchestrator doesn't know what changed.

## Coordination Pattern

```
1. Identify Independent Domains — group failures/questions by subsystem.
2. Create Focused Agent Tasks — each gets specific scope, clear goal, expected marker.
3. Dispatch in Parallel — multiple Agent tool calls in ONE message.
4. Review and Integrate — read each return, verify no conflict, run full suite.
```

## Implementation Subagents — Special Rule

**Never** dispatch multiple **implementation** subagents in parallel on the same codebase region. Conflicts on writes, ordering issues, broken assumptions. For code changes, parallelize only when each agent's files are disjoint.

Research, review, audit, and analysis agents have no such restriction.
