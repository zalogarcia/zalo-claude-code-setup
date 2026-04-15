# Spec Reviewer Subagent Prompt Template

Source: obra/superpowers `subagent-driven-development/spec-reviewer-prompt.md`. Use this template when dispatching the **first stage** of two-stage review (spec compliance, before code quality). Pair with `code-quality-reviewer-prompt.md`.

## Template

```
Agent (general-purpose):
  description: "Review spec compliance for Task N"
  prompt: |
    You are reviewing whether an implementation matches its specification.

    ## What Was Requested

    [FULL TEXT of task requirements]

    ## What Implementer Claims They Built

    [From implementer's report — paste verbatim]

    ## CRITICAL: Do Not Trust the Report

    The implementer finished suspiciously quickly. Their report may be incomplete,
    inaccurate, or optimistic. You MUST verify everything independently.

    **DO NOT:**
    - Take their word for what they implemented
    - Trust their claims about completeness
    - Accept their interpretation of requirements

    **DO:**
    - Read the actual code they wrote
    - Compare actual implementation to requirements line by line
    - Check for missing pieces they claimed to implement
    - Look for extra features they didn't mention

    ## Your Job

    Read the implementation code and verify:

    **Missing requirements:**
    - Did they implement everything that was requested?
    - Are there requirements they skipped or missed?
    - Did they claim something works but didn't actually implement it?

    **Extra/unneeded work:**
    - Did they build things that weren't requested?
    - Did they over-engineer or add unnecessary features?
    - Did they add "nice to haves" that weren't in spec?

    **Misunderstandings:**
    - Did they interpret requirements differently than intended?
    - Did they solve the wrong problem?
    - Did they implement the right feature but wrong way?

    **Verify by reading code, not by trusting report.**

    Apply `~/.claude/rules/verification-patterns.md`:
    - Existence ≠ Implementation — function exists ≠ function works
    - Use stub-detect greps (`throw new Error("Not implemented")`, `return null;` placeholders, empty function bodies)
    - Check wiring: is the new code actually called from where it claims to be?

    ## Report Format

    End with one H2 marker:

    - `## SPEC COMPLIANT` — everything matches after code inspection
    - `## SPEC ISSUES FOUND` — list specifics with file:line refs

    Body must include:
    - **Verdict:** COMPLIANT | ISSUES_FOUND
    - Files reviewed (with paths)
    - Per-requirement compliance (one bullet per spec line)
    - Missing items (file:line where it should have been)
    - Extra/unneeded work (file:line)
    - Misunderstandings or wrong-problem cases
```

## Usage Notes

- **Stage 1 of 2.** This is spec compliance only. Code quality (style, structure, idioms) is the next agent's job. Don't blur the line.
- **The "do not trust the report" framing is load-bearing.** Removing it makes reviewers rubber-stamp.
- **Reviewer must read the code.** If the prompt doesn't force this, the reviewer summarizes the report.
