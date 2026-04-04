#!/bin/bash

# xbar metadata
# <xbar.title>Clipboard Snippets</xbar.title>
# <xbar.desc>Click to copy pre-loaded text snippets</xbar.desc>
# <xbar.version>1.0</xbar.version>

SCRIPTS="$HOME/Library/Application Support/xbar/plugins/scripts"

# ── Menu bar icon ──
echo "📋"
echo "---"

echo "🧠 Plan | bash='${SCRIPTS}/clip-plan-first.sh' terminal=false"
echo "✅ Verify | bash='${SCRIPTS}/clip-verify.sh' terminal=false"
echo "🐞 Bug Fix | bash='${SCRIPTS}/clip-bug-fix.sh' terminal=false"

echo "---"
echo "Refresh | refresh=true"
