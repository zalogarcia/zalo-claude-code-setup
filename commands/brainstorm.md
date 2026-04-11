Deeply analyze a problem, plan, or decision using first principles, inversion, and structured elimination before committing to action.

## Instructions

Launch a `brainstorm` subagent with the user's problem or question. Pass along:

- The full problem description as stated by the user
- Any relevant context from the conversation (constraints, prior attempts, goals)
- The working directory and any relevant file paths if the problem involves code

If the user didn't provide a clear problem statement, ask them what they want to brainstorm before launching the agent.

When the agent returns, relay its analysis directly to the user. Do not summarize or filter — the reasoning is the value.
