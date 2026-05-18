#!/usr/bin/env bash
# autopilot-collect: list all autopilot/* worktrees + branches in the current
# repo with their terminal_state, commit count ahead of a base branch, file
# count touched, and task summary.
#
# Usage:
#   collect.sh [BASE_BRANCH]
#
# Default BASE_BRANCH is `dev` if it exists, else `main`.
#
# Output: TSV. First line is the header. Designed to be parsed by the
# /autopilot-merge command or read by Claude directly.

set -euo pipefail

# ── Resolve repo + base branch ──
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not in a git repository" >&2
  exit 1
fi

BASE_BRANCH="${1:-}"
if [ -z "$BASE_BRANCH" ]; then
  if git show-ref --verify --quiet refs/heads/dev; then
    BASE_BRANCH="dev"
  elif git show-ref --verify --quiet refs/heads/main; then
    BASE_BRANCH="main"
  else
    echo "ERROR: no 'dev' or 'main' branch found; pass BASE_BRANCH explicitly" >&2
    exit 1
  fi
fi

if ! git show-ref --verify --quiet "refs/heads/${BASE_BRANCH}"; then
  echo "ERROR: base branch '${BASE_BRANCH}' does not exist" >&2
  exit 1
fi

# ── Discover worktrees on autopilot/* branches ──
# git worktree list --porcelain output:
#   worktree /path
#   HEAD <sha>
#   branch refs/heads/<branchname>
#   (blank line)
WORKTREES_TSV=$(git worktree list --porcelain | awk '
  /^worktree / { wt = substr($0, 10); next }
  /^branch refs\/heads\// {
    br = substr($0, 19)
    if (br ~ /^autopilot\//) print wt "\t" br
    wt = ""
  }
')

# ── Emit header ──
printf 'PATH\tBRANCH\tTERMINAL_STATE\tCOMMITS_AHEAD_OF_%s\tFILES_TOUCHED\tTASK_SUMMARY\n' "$BASE_BRANCH"

# ── No autopilot worktrees? ──
if [ -z "$WORKTREES_TSV" ]; then
  exit 0
fi

# ── For each, read state.json and compute git stats ──
while IFS=$'\t' read -r wt_path branch; do
  [ -z "$wt_path" ] && continue
  state_file="${wt_path}/.autopilot/state.json"

  if [ -f "$state_file" ]; then
    terminal=$(jq -r '.terminal_state // "running"' "$state_file" 2>/dev/null || echo "?")
    task=$(jq -r '.task_summary // "(no summary)"' "$state_file" 2>/dev/null || echo "?")
  else
    terminal="missing-state"
    task="(no state.json)"
  fi

  # Commits ahead of base. `git rev-list --count` returns the integer.
  # `cmd || echo "?"` is safe under `set -e` because the OR short-circuits.
  ahead=$(git rev-list --count "${BASE_BRANCH}..${branch}" 2>/dev/null || echo "?")

  # File count touched on this branch relative to merge-base with target.
  # `...` (three dots) gives changes from the merge-base, which is what merging
  # actually applies, so it matches what the user will see in the merge commit.
  #
  # The `{ git diff ... || true; } | wc -l | tr -d ' '` shape is NOT optional
  # under `set -euo pipefail`. A bare `git diff ... 2>/dev/null | wc -l` would
  # trip pipefail when git exits non-zero (bad ref, missing merge-base, etc.)
  # and `set -e` would abort the whole script mid-loop — silently truncating
  # the TSV. The brace-group + `|| true` masks git's failure inside the
  # pipeline so `wc` always runs on (possibly empty) input.
  files=$( { git diff --name-only "${BASE_BRANCH}...${branch}" 2>/dev/null || true; } | wc -l | tr -d ' ')

  # Trim task to 80 chars and squash any tabs/newlines so the TSV stays valid.
  task_short=$(printf '%s' "$task" | tr -s '[:space:]' ' ' | cut -c1-80)

  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$wt_path" "$branch" "$terminal" "$ahead" "$files" "$task_short"
done <<< "$WORKTREES_TSV"
