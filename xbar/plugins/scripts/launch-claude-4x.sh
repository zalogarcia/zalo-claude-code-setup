#!/bin/bash
# Opens 4 terminal windows each running claude in the given directory
DIR="${1:-.}"
for i in 1 2 3 4; do
  osascript -e "
    tell application \"Terminal\"
      activate
      do script \"cd '$DIR' && claude --dangerously-skip-permissions\"
    end tell
  "
done
