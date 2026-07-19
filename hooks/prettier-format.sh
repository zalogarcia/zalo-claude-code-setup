#!/usr/bin/env bash
# PostToolUse formatter (Edit|Write|MultiEdit) — replaces the inline prettier one-liner.
# Weekly audit 2026-07-19 (P1): unconditional `prettier --write` invalidated in-flight
# edit sequences in 9 of 37 sessions; markdown reflow was the worst offender.
#   - md/html excluded (plan files, memory notes, generated reports were the victims)
#   - no-op aware: --check first, --write only when the file would actually change
#   - on a real rewrite: exit 2 + stderr notice so the next edit re-reads, not retries blind
set -uo pipefail

FILE=$(cat | jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0
[ -n "$FILE" ] || exit 0
[ -f "$FILE" ] || exit 0

case "$FILE" in
  *.ts | *.tsx | *.js | *.jsx | *.css | *.json) ;;
  *) exit 0 ;;
esac

command -v prettier >/dev/null 2>&1 || exit 0

# Already formatted (or unparseable — --write would fail on those too): nothing to do.
if prettier --check "$FILE" >/dev/null 2>&1; then
  exit 0
fi

if prettier --write "$FILE" >/dev/null 2>&1; then
  echo "prettier-format: reformatted $FILE — the file on disk now differs from your last Edit/Write; re-Read it before further edits." >&2
  exit 2
fi

exit 0
