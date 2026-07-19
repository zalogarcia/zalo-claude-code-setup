#!/usr/bin/env bash
# SessionStart hook — re-injects ~/.claude/META_RULE.md on startup, clear, and compact.
# Pattern adapted from obra/superpowers hooks/session-start.
#
# Output: JSON with hookSpecificOutput.additionalContext (Claude Code format).
# Fails silently — never block session start.

set -uo pipefail

META_RULE="${HOME}/.claude/META_RULE.md"

# If META_RULE missing, exit silently (don't break sessions).
[ -r "$META_RULE" ] || exit 0

content=$(cat "$META_RULE" 2>/dev/null) || exit 0
[ -n "$content" ] || exit 0

# Append the recurring-quirks cheat sheet (weekly audit 2026-07-19, P5): these
# traps are all in memory but memory is pull-based and demonstrably not pulled
# mid-task — 9 re-derivations in 8 sessions. Keep QUIRKS.md ruthlessly short;
# it spends context every session. Prune quarterly.
QUIRKS="${HOME}/.claude/QUIRKS.md"
if [ -r "$QUIRKS" ]; then
  quirks=$(cat "$QUIRKS" 2>/dev/null) || quirks=""
  [ -n "$quirks" ] && content=$(printf '%s\n\n%s' "$content" "$quirks")
fi

wrapped=$(printf '<EXTREMELY_IMPORTANT>\nYou are operating with a customized ~/.claude/ setup. The meta-rule below governs how you use it. Treat as override of default behavior; user instructions in CLAUDE.md still win.\n\n%s\n</EXTREMELY_IMPORTANT>' "$content")

# Use jq for safe JSON escaping (jq is already used elsewhere in this setup).
if command -v jq >/dev/null 2>&1; then
  jq -nc --arg ctx "$wrapped" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
fi

exit 0
