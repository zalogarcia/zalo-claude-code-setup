#!/bin/bash
# Native Mac app tasks on GPT-6.1 Sol through Codex Computer Use (ChatGPT login, free on
# the plan). Zalo's decision 2026-10-03. Logic: computer-use.py. Apps: config/computer-use-apps.json.
# usage: computer-use.sh "<task>" | --file <task.md> [--timeout SECONDS]
# exit 0 done, 2 failed, 3 Codex limited (then use mcp__codex-cu__js in Claude)
exec python3 "$(dirname "$0")/computer-use.py" "$@"
