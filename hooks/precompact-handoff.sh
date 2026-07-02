#!/usr/bin/env bash
# PreCompact hook — writes/overwrites .claude/HANDOFF.md in the current project
# so the post-compaction context can recover branch/worktree/plan state.
# Companion line lives in ~/.claude/META_RULE.md ("After compaction, read
# .claude/HANDOFF.md ...") — META_RULE.md is re-injected by session-start.sh
# on every compact.
#
# Input: hook JSON on stdin ({"cwd": "...", "trigger": "manual"|"auto", ...}).
# Output: none required — PreCompact proceeds regardless.
# Fails open — ANY error exits 0 silently; never blocks compaction. No network.

set -Euo pipefail
trap 'exit 0' ERR

main() {
  local input="" cwd=""

  # Read hook JSON from stdin (skip when stdin is a TTY, e.g. standalone runs).
  if [ ! -t 0 ]; then
    input=$(cat 2>/dev/null || true)
  fi
  if [ -n "$input" ] && command -v jq >/dev/null 2>&1; then
    cwd=$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null || true)
  fi
  [ -n "$cwd" ] && [ -d "$cwd" ] || cwd="$PWD"

  local is_repo=0
  if git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    is_repo=1
  fi

  # Nothing project-like to hand off to (e.g. /tmp): skip silently.
  if [ "$is_repo" -eq 0 ] && [ ! -d "$cwd/.claude" ]; then
    return 0
  fi

  mkdir -p "$cwd/.claude" 2>/dev/null || return 0

  local out="$cwd/.claude/HANDOFF.md"
  local tmp="$out.tmp.$$"

  {
    echo "# Session Handoff (auto-written by PreCompact hook)"
    echo
    echo "- Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
    if [ "$is_repo" -eq 1 ]; then
      echo "- Branch: $(git -C "$cwd" branch --show-current 2>/dev/null || echo unknown)"
    fi
    echo "- test identities: see .claude/test-identities.md"
    echo

    if [ "$is_repo" -eq 1 ]; then
      echo "## Worktrees"
      echo '```'
      git -C "$cwd" worktree list 2>/dev/null || echo "(unavailable)"
      echo '```'
      echo
    fi

    echo "## Plan / goal pointers (.claude/)"
    local found=0 f
    for f in "$cwd"/.claude/PLAN-*.md "$cwd/.claude/GOAL.md"; do
      [ -f "$f" ] || continue
      echo "- .claude/$(basename "$f")"
      found=1
    done
    [ "$found" -eq 1 ] || echo "- (none)"

    if [ "$is_repo" -eq 1 ]; then
      echo
      echo "## Last 3 commits"
      echo '```'
      git -C "$cwd" log --oneline -3 2>/dev/null || echo "(unavailable)"
      echo '```'
    fi
  } >"$tmp" 2>/dev/null || {
    rm -f "$tmp" 2>/dev/null
    return 0
  }

  mv -f "$tmp" "$out" 2>/dev/null || rm -f "$tmp" 2>/dev/null
  return 0
}

main "$@"
exit 0
