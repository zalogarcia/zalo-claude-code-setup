# Human-in-Loop Checkpoints

Adapted from gsd-build/get-shit-done. When an orchestrator needs human input, emit a **readable markdown checkpoint block** and **stop** — do not continue past the gate.

Checkpoint blocks are rendered to the user in the terminal. Use clean markdown (headings, bullets, bold) — **never raw XML tags**. XML renders as literal `<tag>` text and is unreadable.

## Three Checkpoint Types

### `checkpoint:human-verify` (~90% of cases)

Claude built/deployed something; human needs to confirm it works.

**Format:**

```markdown
## Checkpoint — Human Verification Needed

**What I built:** [one-line summary]

**How to verify:**

- [step 1 — URL, command, expected behavior]
- [step 2]
- [step 3]

**Resume:** reply `approved` / `yes` to continue, or describe any issues.
```

### `checkpoint:decision` (~9% of cases)

Multiple valid paths; human picks.

**Format:**

```markdown
## Checkpoint — Decision Needed

**Decision:** [what's being decided in one line]

**Why it matters:** [one-sentence context]

**Options:**

**A) [Option name]**

- Pros: [benefits]
- Cons: [tradeoffs]

**B) [Option name]**

- Pros: [benefits]
- Cons: [tradeoffs]

**Resume:** reply `A` / `B` (or describe a different path). Nothing runs until you confirm.
```

### `checkpoint:human-action` (~1% of cases — auth gates only)

Something only a human can do (enter MFA, click an OAuth consent screen, paste a secret).

**Format:**

```markdown
## Checkpoint — Action Required

**Action needed:** [the ONE thing only you can do]

**Context:**

- Already automated: [what Claude did]
- What you need to do: [specific human action]

**After you're done:** I'll verify with [check Claude will run].

**Resume:** reply `done` when finished.
```

## Rendering Rules

1. **Never emit raw XML tags** (`<task>`, `<option>`, `<pros>`, etc.). The terminal shows them as literal text. Use markdown headings, bold labels, and bullet lists instead.
2. **Lead with a clear `## Checkpoint — <Type>` heading** so the user sees at a glance that the workflow is paused.
3. **Keep option names short** (≤ 40 chars) — they're read quickly.
4. **Always include a `**Resume:**` line** as the last line of the block so the user knows the exact signal to unblock.

## Golden Rules

1. **If Claude can run it, Claude runs it.** Never ask the user to execute CLI commands, start dev servers, or run builds.
2. **Claude sets up the verification environment.** Start dev servers, seed databases, configure env vars before asking the human to look.
3. **The user only does what requires human judgment.** Visual checks, UX evaluation, "does this feel right?" — not mechanical execution.
4. **Secrets come from the user, automation comes from Claude.** Ask for an API key once, then use it via CLI for all subsequent operations.

## Execution Protocol

When emitting a checkpoint block:

1. **Stop immediately.** Do not proceed to the next task.
2. **Display the checkpoint block** as the last thing in your message.
3. **Wait for user response.** Do not hallucinate completion.
4. **Verify if possible.** After the human responds, run any check you promised under "After you're done".
5. **Resume execution** only after explicit confirmation.

## Auth Gate Pattern

Auth gate = Claude tried CLI/API, got auth error. Not a failure — a gate requiring human input to unblock.

Pattern: Claude tries automation → auth error → emits `checkpoint:human-action` → user authenticates → Claude retries → continues.
