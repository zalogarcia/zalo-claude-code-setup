#!/bin/bash

# xbar metadata
# <xbar.title>My Shortcuts</xbar.title>
# <xbar.desc>Quick launcher for automation scripts</xbar.desc>
# <xbar.version>1.0</xbar.version>

# ── Menu bar icon (rocket emoji, or change to any text/emoji) ──
echo "⚡"
echo "---"

# ── NSTBrowser Cookie Warmup (launches app + profile + warmup) ──
echo "🍪 NSTBrowser Launch & Warmup | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-nst-warmup.sh' terminal=true"

# ── Claude Code (no folder, skip permissions) ──
echo "🤖 Claude Code (Bare) | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-bare.sh' terminal=true"

# ── Claude Code (xbar plugins dir) ──
echo "🤖 Claude Code (Plugins) | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude.sh' terminal=true"

# ── Claude Code Project Launchers ──
echo "---"
echo "🤖 Claude: Delta Agents | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-delta-agents.sh' terminal=true"
echo "🤖 Claude: Delta Agents ×4 | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-4x.sh' param1=\"$HOME/Documents/AI Projects/delta-agents\" terminal=false"
echo "🤖 Claude: Operator Base | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-operator-base.sh' terminal=true"
echo "🤖 Claude: Operator Base ×4 | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-4x.sh' param1=\"$HOME/Documents/AI Projects/Operator Base\" terminal=false"
echo "🤖 Claude: Black Umbrella | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-black-umbrella.sh' terminal=true"
echo "🤖 Claude: Black Umbrella ×4 | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/launch-claude-4x.sh' param1=\"$HOME/Documents/AI Projects/black-umbrella\" terminal=false"

echo "---"
echo "📐 Capture Window Layout | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/capture-layout.sh' terminal=false"
echo "📐 Restore Window Layout | bash='/Users/zalo/Library/Application Support/xbar/plugins/scripts/restore-layout.sh' terminal=false"

echo "---"
echo "Edit Shortcuts… | bash='/usr/bin/open' param1='-a' param2='TextEdit' param3='${HOME}/Library/Application Support/xbar/plugins/002-shortcuts.1d.sh' terminal=false"
echo "Refresh | refresh=true"
