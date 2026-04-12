#!/bin/bash
# Reset per-session Stop-hook nudge counter on each new user prompt.
# Runs from UserPromptSubmit. Reads {session_id} from stdin JSON.
SID=$(cat | /usr/bin/env python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("session_id",""))' 2>/dev/null)
if [[ "$SID" =~ ^[A-Za-z0-9_-]{1,128}$ ]]; then
  rm -f "$HOME/.claude/hooks/.stop-state/${SID}.count" 2>/dev/null
fi
exit 0
