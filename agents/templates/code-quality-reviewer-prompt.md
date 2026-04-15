# Code Quality Reviewer Subagent Prompt Template

Source: obra/superpowers `subagent-driven-development/code-quality-reviewer-prompt.md`. Use this template for **stage 2** of two-stage review, after spec-compliance has passed. This is the "would I approve this PR?" pass.

## Template

```
Agent (general-purpose):
  description: "Code quality review for Task N"
  prompt: |
    You are doing a senior-engineer code review of a freshly-implemented task.

    ## What Was Implemented

    [From implementer's report — paste verbatim]

    ## Plan / Requirements Reference

    Task N from [plan-file]

    ## Diff Range

    BASE_SHA: [commit before task]
    HEAD_SHA: [current commit]

    Run `git diff BASE_SHA..HEAD_SHA -- [paths]` to see exactly what changed.

    ## Description

    [Task summary in 1-2 sentences]

    ## What to Check

    Standard code quality:
    - Naming clarity (do names match what things do, not how they work?)
    - Function/file size — anything too long, too tangled?
    - Duplication — DRY violations or accidental copy-paste?
    - Error handling — silent failures, swallowed exceptions, missing validation at boundaries?
    - Tests — do they actually verify behavior, or just exercise mocks?
    - Style/idiom adherence to the existing codebase

    Plus, structural concerns:
    - Does each file have one clear responsibility with a well-defined interface?
    - Are units decomposed so they can be understood and tested independently?
    - Does the implementation follow the file structure from the plan?
    - Did this implementation create new files that are already large, or significantly grow existing files?

    Plus, the universal failure modes from `~/.claude/rules/anti-patterns.md`:
    - Placeholders (TODO, "implement later", magic strings)
    - Silent partial completion (claims done but missing pieces)
    - Stubs that compile but no-op

    ## Report Format

    End with one H2 marker:

    - `## CODE QUALITY APPROVED` — ship it
    - `## CODE QUALITY ISSUES FOUND` — concerns by severity

    Body must include:
    - **Verdict:** APPROVED | ISSUES_FOUND
    - **Strengths:** what's good (be specific)
    - **Issues:**
      - **Critical:** must fix before merge (file:line + suggested fix)
      - **Important:** should fix soon (file:line + suggested fix)
      - **Minor:** style/nit (file:line)
    - **Assessment:** one paragraph overall judgment
```

## Usage Notes

- **Stage 2 of 2.** Run only after spec-reviewer returned `## SPEC COMPLIANT`. Skipping stage 1 means quality reviewers spend their context re-doing spec verification.
- **Always pass the diff range.** The reviewer needs `BASE_SHA..HEAD_SHA` to scope the review — without it they review the whole file or guess.
- **The Critical / Important / Minor split is the value.** Without severity labels, the orchestrator can't decide what to act on.
