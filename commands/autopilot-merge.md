# /autopilot-merge — Consolidate completed autopilot branches onto a target branch

Sequential `--no-ff` merge of every completed `autopilot/*` branch in this repo onto a target branch (default `dev`). Preserves per-run commit history with one merge commit per autopilot run. Pauses on conflicts for human resolution. Does NOT auto-clean worktrees or branches.

## How to invoke

```
/autopilot-merge              # merge all completed autopilots → dev (or main if no dev)
/autopilot-merge main         # merge all completed autopilots → main
/autopilot-merge dev --push   # merge then push origin/dev after confirmation
```

## Authoritative Rules

@~/.claude/rules/git-safety.md
@~/.claude/rules/gates.md
@~/.claude/rules/checkpoints.md
@~/.claude/rules/anti-patterns.md

## Workflow

### Step 1: Resolve target branch

```bash
TARGET="${1:-}"          # first arg, may be empty
PUSH_FLAG=false
for arg in "$@"; do
  [ "$arg" = "--push" ] && PUSH_FLAG=true
done

if [ -z "$TARGET" ] || [ "$TARGET" = "--push" ]; then
  if git show-ref --verify --quiet refs/heads/dev; then
    TARGET="dev"
  elif git show-ref --verify --quiet refs/heads/main; then
    TARGET="main"
  else
    echo "ERROR: no 'dev' or 'main' branch; pass target explicitly" >&2
    exit 1
  fi
fi

if ! git show-ref --verify --quiet "refs/heads/${TARGET}"; then
  echo "ERROR: target branch '${TARGET}' does not exist" >&2
  exit 1
fi
```

### Step 2: Discover completed autopilots (via `autopilot-collect` skill)

Invoke the skill — do NOT reimplement discovery inline:

```bash
TSV=$(~/.claude/skills/autopilot-collect/collect.sh "$TARGET")
```

Parse the TSV (skip header). Filter to `terminal_state ∈ {complete, complete_with_issues}`. Surface skipped rows separately with their state so the user sees what was excluded (e.g. a still-running autopilot must NOT be merged).

```bash
MERGEABLE=$(echo "$TSV" | tail -n +2 | awk -F'\t' '$3 == "complete" || $3 == "complete_with_issues"')
SKIPPED=$(echo "$TSV" | tail -n +2 | awk -F'\t' '$3 != "complete" && $3 != "complete_with_issues"')
```

If `MERGEABLE` is empty → report "No completed autopilot branches to merge." and exit cleanly. Show `SKIPPED` if non-empty so the user knows why nothing matched.

### Step 3: Sort and display

Sort `MERGEABLE` by branch name (the `autopilot/<timestamp>-<pid>` suffix is lexicographically chronological since timestamps are zero-padded). Oldest first — this matches the order the user started them, which is the most natural merge order.

```bash
MERGEABLE_SORTED=$(echo "$MERGEABLE" | sort -t$'\t' -k2)
```

Print a readable summary table to the user. Format the columns; do NOT paste the raw TSV. Example:

```
Found N autopilot branches ready to merge onto <TARGET>:

  1. autopilot/20260518-153313-6334  (7 commits, 22 files)  Build conversations tab
  2. autopilot/20260518-164212-7891  (4 commits, 11 files)  Webhook retry handler
  3. autopilot/20260518-171530-8234  (9 commits, 31 files)  Settings page redesign

Skipped (not in terminal-state {complete, complete_with_issues}):
  - autopilot/20260518-182104-9012  state=running       (do NOT merge — still active)
  - autopilot/20260517-093015-5421  state=aborted       (review .autopilot/report.md)
```

### Step 4: Pre-flight on target

Find the worktree that owns `TARGET` (a branch can be checked out in only ONE worktree). If unowned, use the main repo. `cd` there for the rest of the workflow.

```bash
TARGET_WT=$(git worktree list --porcelain | awk -v t="refs/heads/$TARGET" '
  /^worktree / { wt = substr($0, 10); next }
  /^branch / && $2 == t { print wt; exit }
')

if [ -z "$TARGET_WT" ]; then
  # Target not checked out anywhere — fall back to the main repo and check it out.
  GIT_COMMON=$(git rev-parse --git-common-dir)
  [[ "$GIT_COMMON" = /* ]] || GIT_COMMON="$(pwd)/$GIT_COMMON"
  TARGET_WT=$(dirname "$(cd "$GIT_COMMON" && pwd)")
  cd "$TARGET_WT"
  git checkout "$TARGET"
else
  cd "$TARGET_WT"
fi
```

Verify clean state:

```bash
git status --porcelain  # MUST be empty
```

If not empty → ABORT with a clear message. Don't auto-stash; the user needs to know their target has uncommitted work.

Verify up-to-date with remote (if a remote exists):

```bash
git fetch origin "$TARGET" 2>/dev/null || true
LOCAL=$(git rev-parse "$TARGET")
REMOTE=$(git rev-parse "origin/$TARGET" 2>/dev/null || echo "")
```

If `REMOTE` is non-empty and `LOCAL != REMOTE`:

- If target is BEHIND origin → emit `checkpoint:human-action` asking the user to `git pull` first (or run with `--force-stale`). Don't auto-pull — could merge unexpected changes.
- If target is AHEAD of origin → log a note ("target is ahead of origin by N commits"); continue, the user will decide about push.
- If diverged → ABORT and ask the user to reconcile.

### Step 5: Confirm before merging

Emit `checkpoint:human-verify`:

```markdown
## Checkpoint — Confirm Merge Plan

**Target:** <TARGET> at <SHA>
**Branches to merge (in order):**

1. autopilot/... (N commits, K files) <task>
2. ...

**Conflict policy:** sequential `--no-ff` merge. If any branch conflicts, this workflow pauses and asks you to resolve.

**Cleanup:** worktrees and branches will be LEFT in place after merging. Remove manually when ready.

**Resume:** reply `go` / `yes` to proceed, or describe any change.
```

Wait for user confirmation. Do NOT proceed without an explicit go-ahead.

### Step 6: Sequential merge loop

```
FOR each branch in MERGEABLE_SORTED:
  task = branch's TASK_SUMMARY (from TSV)
  short_id = branch suffix after "autopilot/"

  # Attempt the merge.
  git merge --no-ff "$branch" -m "Merge autopilot/${short_id} — ${task}"

  IF exit 0:
    Print: "✓ Merged autopilot/${short_id}"
    CONTINUE to next branch.

  IF conflict (exit != 0, `git status` shows merge in progress):
    # Surface conflict and stop. Conflict resolution is human work.
    CONFLICT_FILES=$(git diff --name-only --diff-filter=U)

    Emit checkpoint:human-action:
    """
    ## Checkpoint — Merge Conflict in autopilot/${short_id}

    **Conflicting files:**
    ${CONFLICT_FILES}

    **What you need to do:**
    1. Resolve conflicts in the files above (open in editor)
    2. `git add <resolved files>`
    3. `git commit --no-edit` (preserves the merge message above)
    4. Reply `continue` here so I can verify and move to the next branch.

    Alternative: `git merge --abort` to roll back this branch's merge and reply `skip`.

    **After you're done:** I'll run `git status` to verify, then continue with the remaining branches.

    **Resume:** reply `continue` or `skip` when done.
    """

    STOP. Wait for user response.

    On `continue`:
      Verify: `git status --porcelain` is empty AND `git log -1 --pretty=%P | wc -w` shows 2+ parents (merge commit landed)
      If verification fails → re-emit the checkpoint with the current status
      Otherwise log "resolved autopilot/${short_id}" and proceed to next branch

    On `skip`:
      Verify: `git status --porcelain` is empty (user ran `git merge --abort`)
      Log "skipped autopilot/${short_id} — conflict not resolved"
      Proceed to next branch

  IF other error (not exit 0 and not a conflict — shouldn't normally happen):
    ABORT with the git error output. Do NOT swallow.
```

### Step 7: Report + push prompt

After the loop completes:

```bash
MERGED_COUNT=<from loop>
SKIPPED_COUNT=<from loop>
git log --oneline -${MERGED_COUNT} | head -${MERGED_COUNT}
```

Print summary:

```
Merge complete.
  Merged:   N branches
  Skipped:  K branches (conflict, user chose skip)
  Target:   <TARGET> now at <new SHA>

Recent commits on <TARGET>:
  <git log --oneline -N output>
```

If `PUSH_FLAG` is true OR the user explicitly said `--push` in the original invocation → push:

```bash
git push origin "$TARGET"
```

Otherwise, emit `checkpoint:decision`:

```markdown
## Checkpoint — Push Decision

**Target <TARGET> is N commits ahead of origin.** Push now?

**Options:**

**A) Push to origin/<TARGET>**

- Runs `git push origin <TARGET>`
- Make these merges visible to the team / triggers CI

**B) Leave local for now**

- Inspect locally first, push later via `git push origin <TARGET>`

**Resume:** reply `A` or `B`.
```

### Step 8: Promotion to main (out of scope)

This command does NOT promote dev to main. That's a separate decision involving review/CI/release process. If the user asks "now push to main", suggest:

- For trivial promotion: `git checkout main && git merge --ff-only dev && git push origin main`
- For reviewed promotion: open a PR `dev → main` via `gh pr create --base main --head dev`

Surface the recommendation; do not execute without explicit user direction.

## Anti-patterns (will not do)

- Auto-cleanup worktrees or branches without explicit user opt-in (the user chose to leave them)
- Force-push to the target branch
- Skip conflict files silently — every conflict surfaces a `checkpoint:human-action`
- Merge a branch whose `terminal_state` is `running`, `aborted`, or `missing-state` — those are surfaced as skipped, never merged
- Use `git add -A` or `git add .` during conflict resolution — only specific resolved files
- Use `git merge` without `--no-ff` — would lose the per-run boundary the user explicitly chose to preserve
- Promote dev → main automatically — that's a release decision, not a merge decision
- Squash or rebase autopilot branches — the user chose "sequential merge commits" specifically to preserve the N-commit per-run history
- Hand-roll worktree discovery — invoke the `autopilot-collect` skill

## Pair with

- `autopilot-collect` skill — discovery (called by Step 2)
- `/autopilot resume` — if you find a `running` worktree and want to continue it before merging
- `commit-with-heredoc` skill — only if a conflict commit needs a multi-line message; standard merge commits use the inline `-m` form above
