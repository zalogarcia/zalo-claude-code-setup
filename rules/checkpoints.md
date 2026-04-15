# Human-in-Loop Checkpoints

Adapted from gsd-build/get-shit-done. When an orchestrator needs human input, emit a `<task type="checkpoint:*">` block and **stop** — do not continue past the gate.

## Three Checkpoint Types

### `checkpoint:human-verify` (~90% of cases)

Claude built/deployed something; human needs to confirm it works.

```xml
<task type="checkpoint:human-verify" gate="blocking">
  <what-built>[What was automated / built / deployed]</what-built>
  <how-to-verify>
    [Exact steps - URLs, commands, expected behavior]
  </how-to-verify>
  <resume-signal>[How to continue - "approved", "yes", or describe issues]</resume-signal>
</task>
```

### `checkpoint:decision` (~9% of cases)

Multiple valid paths; human picks.

```xml
<task type="checkpoint:decision" gate="blocking">
  <decision>[What's being decided]</decision>
  <context>[Why this decision matters]</context>
  <options>
    <option id="option-a">
      <name>[Option name]</name>
      <pros>[Benefits]</pros>
      <cons>[Tradeoffs]</cons>
    </option>
    <option id="option-b">
      <name>[Option name]</name>
      <pros>[Benefits]</pros>
      <cons>[Tradeoffs]</cons>
    </option>
  </options>
  <resume-signal>[How to indicate choice]</resume-signal>
</task>
```

### `checkpoint:human-action` (~1% of cases — auth gates only)

Something only a human can do (enter MFA, click an OAuth consent screen, paste a secret).

```xml
<task type="checkpoint:human-action" gate="blocking">
  <action>[The ONE thing requiring human action]</action>
  <instructions>
    [What Claude already automated]
    [The specific human action needed]
  </instructions>
  <verification>[What Claude can check afterward]</verification>
  <resume-signal>[How to continue]</resume-signal>
</task>
```

## Golden Rules

1. **If Claude can run it, Claude runs it.** Never ask the user to execute CLI commands, start dev servers, or run builds.
2. **Claude sets up the verification environment.** Start dev servers, seed databases, configure env vars before asking the human to look.
3. **The user only does what requires human judgment.** Visual checks, UX evaluation, "does this feel right?" — not mechanical execution.
4. **Secrets come from the user, automation comes from Claude.** Ask for an API key once, then use it via CLI for all subsequent operations.

## Execution Protocol

When emitting a `checkpoint:*` block:

1. **Stop immediately.** Do not proceed to the next task.
2. **Display the checkpoint block** as the last thing in your message.
3. **Wait for user response.** Do not hallucinate completion.
4. **Verify if possible.** After the human responds, run any verification you specified in `<verification>`.
5. **Resume execution** only after explicit confirmation.

## Auth Gate Pattern

Auth gate = Claude tried CLI/API, got auth error. Not a failure — a gate requiring human input to unblock.

Pattern: Claude tries automation → auth error → emits `checkpoint:human-action` → user authenticates → Claude retries → continues.
