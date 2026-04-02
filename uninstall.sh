#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Claude Code Setup Uninstaller
# ============================================================================
# Restores from the most recent backup created by install.sh
# Files that didn't exist before install are removed (not left orphaned)
# ============================================================================

CLAUDE_DIR="$HOME/.claude"
CLAUDE_JSON="$HOME/.claude.json"
SETTINGS_JSON="$CLAUDE_DIR/settings.json"
SETTINGS_LOCAL="$CLAUDE_DIR/settings.local.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Find the most recent backup
BACKUP_DIR=$(ls -dt "$CLAUDE_DIR/backups"/*/ 2>/dev/null | head -1)

if [ -z "$BACKUP_DIR" ]; then
    error "No backups found in $CLAUDE_DIR/backups/"
    error "Cannot uninstall without a backup to restore from."
    exit 1
fi

echo ""
echo "============================================"
echo "  Claude Code Setup Uninstaller"
echo "============================================"
echo ""
echo "Will restore from backup: $BACKUP_DIR"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Helper: restore or remove a config file
# If backup exists, restore it. If file didn't exist before install, remove it.
restore_or_remove() {
    local backup_name="$1"
    local target_path="$2"
    local manifest_key="$3"

    if [ -f "$BACKUP_DIR/$backup_name" ]; then
        cp "$BACKUP_DIR/$backup_name" "$target_path"
        ok "Restored $target_path"
    elif [ -f "$BACKUP_DIR/.manifest" ] && ! grep -q "^${manifest_key}$" "$BACKUP_DIR/.manifest"; then
        # File didn't exist before install — remove the installed version
        rm -f "$target_path"
        ok "Removed $target_path (did not exist before install)"
    else
        warn "No backup for $target_path and no manifest info — leaving as-is"
    fi
}

# Restore configs
info "Restoring configs from backup..."

restore_or_remove "claude.json.bak" "$CLAUDE_JSON" "claude.json"
restore_or_remove "settings.json.bak" "$SETTINGS_JSON" "settings.json"
restore_or_remove "settings.local.json.bak" "$SETTINGS_LOCAL" "settings.local.json"
restore_or_remove "CLAUDE.md.bak" "$CLAUDE_DIR/CLAUDE.md" "CLAUDE.md"

# Restore agents
if [ -d "$BACKUP_DIR/agents.bak" ]; then
    rm -rf "$CLAUDE_DIR/agents"
    cp -r "$BACKUP_DIR/agents.bak" "$CLAUDE_DIR/agents"
    ok "Restored agents"
else
    # Remove installed agents
    rm -f "$CLAUDE_DIR/agents/qa-agent.md"
    rm -f "$CLAUDE_DIR/agents/safe-planner.md"
    rm -f "$CLAUDE_DIR/agents/live-test.md"
    rm -f "$CLAUDE_DIR/agents/frontend-specialist.md"
    ok "Removed installed agents"
fi

# Restore skills
if [ -d "$BACKUP_DIR/skills.bak" ]; then
    rm -rf "$CLAUDE_DIR/skills"
    cp -r "$BACKUP_DIR/skills.bak" "$CLAUDE_DIR/skills"
    ok "Restored skills"
else
    rm -rf "$CLAUDE_DIR/skills/ui-ux-pro-max"
    rm -rf "$CLAUDE_DIR/skills/frontend-design"
    rm -rf "$CLAUDE_DIR/skills/cf-crawl"
    ok "Removed installed skills"
fi

echo ""
echo -e "${GREEN}Uninstall complete.${NC} Restart Claude Code to apply changes."
echo ""
