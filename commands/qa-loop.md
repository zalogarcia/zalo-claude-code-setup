Run a QA loop that iteratively finds and fixes bugs until the codebase is clean.

## Instructions

After a multi-file code update, run this loop to catch and fix all bugs:

### Step 1: Determine Scope

Identify what changed. Use `git diff` (or `git diff HEAD~1` if already committed) to understand the scope of recent changes. Note the affected files and modules.

### Step 2: QA Loop

Run the following loop. **MAX_ITERATIONS = 10** (safety cap to prevent infinite loops).

```
iteration = 0

LOOP:
  iteration += 1

  # 1. Launch QA agent
  Run a `qa-agent` subagent with this prompt:
    "Audit the following files for real, reproducible bugs: {list of changed files}.
     Focus on: logic errors, off-by-one, null/undefined access, race conditions,
     missing error handling at boundaries, broken imports, type mismatches,
     and integration issues between the changed files.
     Do NOT flag style issues, naming preferences, or hypothetical concerns.
     Only report bugs you are confident are real and reproducible.
     For each bug, report: file, line, description, and severity (critical/major/minor).
     If you find NO bugs, explicitly say: NO_BUGS_FOUND"

  # 2. Parse results
  IF qa-agent reports NO_BUGS_FOUND:
    BREAK — loop is done, report success

  IF iteration >= MAX_ITERATIONS:
    BREAK — report remaining unfixed bugs to user

  # 3. Fix found bugs
  For each bug reported (ordered by severity: critical first):
    a. Read the file and understand the bug in context
    b. Apply the minimal fix — do NOT refactor surrounding code
    c. If a fix is unclear or risky, skip it and note it for the user

  # 4. Verify fixes compile/build
  Run the project's build/typecheck command (if available).
  If build breaks, fix the build error before continuing the loop.

  # 5. Expand scope
  Re-run git diff to capture any newly-touched files from the fixes.
  Merge them into the file list for the next QA pass.

  # 6. Back to top — run QA again on expanded scope
  GOTO LOOP
```

### Step 3: Report

When the loop exits, summarize:

- **Iterations run**: how many QA passes were needed
- **Bugs found and fixed**: list each with file, line, and what was wrong
- **Bugs skipped**: any that were too risky or ambiguous to auto-fix
- **Final state**: clean (no bugs) or remaining issues needing manual attention

### Guardrails

- **Never fix style issues** — only real bugs
- **Never refactor** — minimal fixes only
- **Never modify tests** unless the bug is in the test itself
- **If the same bug appears 3 times**, skip it — it likely needs human judgment
- **Always run build/typecheck after fixes** before the next QA pass
