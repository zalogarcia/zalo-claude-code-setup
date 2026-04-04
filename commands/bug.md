Trace, diagnose, and fix a bug using the bug-fix agent, then validate with a QA loop.

## Instructions

### Step 1: Gather Context

Ask the user to describe the bug:

- What is the expected behavior?
- What is the actual behavior?
- Steps to reproduce (if known)
- Any relevant error messages or logs

If the user already provided this information in the conversation, skip asking and proceed.

### Step 2: Launch Bug-Fix Agent

Run a `bug-fix` subagent with a detailed prompt that includes:

- The bug description and reproduction steps from Step 1
- The working directory and any relevant file paths mentioned by the user
- Instructions to trace the full user flow, read all related code, identify the root cause, and produce a comprehensive fix plan

The bug-fix agent will:

1. Read all related code and trace the flow
2. Identify the root cause
3. Produce a fix plan with specific file and line changes

### Step 3: Review and Clarify

Review the bug-fix agent's findings. If the root cause is ambiguous or the fix could go multiple ways:

- Present the diagnosis to the user
- Ask which approach they prefer before proceeding

If the diagnosis is clear and the fix is straightforward, proceed directly.

### Step 4: Apply the Fix

Implement the changes identified by the bug-fix agent:

- Apply minimal, targeted fixes — do not refactor surrounding code
- Do not add unrelated improvements
- Run the build/typecheck command after applying changes to verify they compile

### Step 5: Run QA Loop

Invoke the `/qa-loop` skill to validate the fix:

- This will audit the changed files for any regressions or new bugs introduced by the fix
- It will iterate until the code is clean or report remaining issues

### Step 6: Report

Summarize to the user:

- **Root cause**: what was wrong and why
- **Fix applied**: what changed (files and lines)
- **QA result**: clean or any remaining issues
- **How to verify**: manual steps the user can take to confirm the fix

### Guardrails

- **Never fix more than the reported bug** — stay focused on the issue
- **Never refactor or improve surrounding code** while fixing the bug
- **If the root cause is unclear after investigation**, stop and ask the user — don't guess
- **Always run build/typecheck** after applying the fix, before QA
- **If the QA loop finds regressions from the fix**, address them before reporting done
