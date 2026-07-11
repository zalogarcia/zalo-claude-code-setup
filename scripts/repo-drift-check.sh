#!/usr/bin/env bash
# repo-drift-check.sh — audit git repos under ~/dev for missing Claude scaffold pieces
#
# Checks each repo directly under DEV_DIR for .claude/CLAUDE.md and .claude/VERIFY.md.
# One status line per repo, then a summary count.
#
# Usage:
#   repo-drift-check.sh [DEV_DIR]
#   DEV_DIR=/some/path repo-drift-check.sh
#
# Defaults: DEV_DIR = ~/dev
# Skips: autopilot worktrees/clones (*-autopilot-<timestamp>*) — ephemeral copies
#        that inherit their parent repo's scaffold.
# Exit codes: 0 = all repos OK, 1 = at least one repo missing pieces, 2 = setup error

set -uo pipefail

DEV_DIR="${1:-${DEV_DIR:-$HOME/dev}}"

if [ ! -d "$DEV_DIR" ]; then
  echo "ERROR: directory not found: $DEV_DIR" >&2
  exit 2
fi

total=0
ok=0
missing_count=0
skipped=0

for dir in "$DEV_DIR"/*/; do
  [ -d "$dir" ] || continue
  name="$(basename "$dir")"

  # A repo = dir containing .git (dir for normal clones, file for linked worktrees)
  [ -e "${dir}.git" ] || continue

  # Skip ephemeral autopilot worktrees/clones
  case "$name" in
    *-autopilot-*)
      skipped=$((skipped + 1))
      continue
      ;;
  esac

  total=$((total + 1))

  missing=""
  [ -f "${dir}.claude/CLAUDE.md" ] || missing="CLAUDE.md"
  if [ ! -f "${dir}.claude/VERIFY.md" ]; then
    [ -n "$missing" ] && missing="$missing, VERIFY.md" || missing="VERIFY.md"
  fi

  if [ -z "$missing" ]; then
    printf '%-40s OK\n' "$name"
    ok=$((ok + 1))
  else
    printf '%-40s MISSING: %s\n' "$name" "$missing"
    missing_count=$((missing_count + 1))
  fi
done

echo ""
echo "Summary: $total repos scanned — $ok OK, $missing_count missing pieces ($skipped autopilot worktrees skipped)"
if [ "$missing_count" -gt 0 ]; then
  echo "Hint: run /repo-init inside the repo to scaffold."
  exit 1
fi
exit 0
