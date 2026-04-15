# /brainstorm — Deep Thinking, Challenge, Clarify

Dispatch the `brainstorm` agent to apply first principles, inversion, and second-order thinking. Surfaces the real problem, not just the presented one.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/questioning.md
@~/.claude/rules/problem-solving.md

## Workflow

### Step 1: Confirm the problem

If the user provided a clear problem statement → proceed.

If the problem is vague → ask **one** open question to surface the real shape, applying `~/.claude/rules/questioning.md` dream-extraction philosophy:

- Start open ("what does success look like?")
- Follow the user's energy
- Don't pile on multiple questions — wait for the answer first

### Step 2: Dispatch `brainstorm`

Pass to the agent:

- The user's problem statement (verbatim)
- Any constraints, prior attempts, or goals from the conversation
- Working directory + file paths if the problem involves code
- Explicit instruction: "Apply `~/.claude/rules/problem-solving.md` when-stuck dispatch table if you find yourself spiraling."

Wait for `## EXPLORATION COMPLETE`.

### Step 3: Relay, don't filter

When the agent returns, **relay its analysis directly to the user**. Do not summarize, compress, or filter — the reasoning is the value, not just the conclusion.

If the agent says "I don't know" or "stop and rethink" → that is a valid result. Don't paper over it.

## Anti-Patterns (will not do)

- Skip the brainstorm and answer the user yourself ("I think I can answer this").
- Compress the agent's reasoning into a single recommendation.
- Solve the presented problem when the agent flagged it as the wrong problem.
- Treat "I don't know" as a failure — it's calibrated honesty.
