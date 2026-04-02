#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Claude Code Setup Installer - Zalo's Configuration
# ============================================================================
# Installs: agents, skills, hooks, MCP servers, and global CLAUDE.md
# Safe: backs up existing configs before modifying
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
CLAUDE_JSON="$HOME/.claude.json"
SETTINGS_JSON="$CLAUDE_DIR/settings.json"
SETTINGS_LOCAL="$CLAUDE_DIR/settings.local.json"
BACKUP_DIR="$CLAUDE_DIR/backups/$(date +%Y%m%d_%H%M%S)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# Prerequisites check
# ============================================================================

check_prerequisites() {
    info "Checking prerequisites..."

    local missing=()

    command -v node >/dev/null 2>&1 || missing+=("node")
    command -v npx >/dev/null 2>&1 || missing+=("npx")
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    command -v jq >/dev/null 2>&1 || missing+=("jq")

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing required tools: ${missing[*]}"
        echo "  Install them before running this script."
        echo "  macOS: brew install ${missing[*]}"
        exit 1
    fi

    # Optional tools (warn but don't block)
    if ! command -v prettier >/dev/null 2>&1; then
        warn "prettier not found globally. Hook will silently skip formatting."
        warn "  Install: npm install -g prettier"
    fi

    if ! command -v ruff >/dev/null 2>&1; then
        warn "ruff not found. Python formatting hook will be inactive."
        warn "  Install: pip install ruff"
    fi

    if ! command -v uvx >/dev/null 2>&1; then
        warn "uvx not found. Qdrant memory MCP won't work."
        warn "  Install: pip install uv"
    fi

    ok "Prerequisites check complete"
}

# ============================================================================
# Backup existing configs
# ============================================================================

backup_configs() {
    info "Backing up existing configs to $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"

    [ -f "$CLAUDE_JSON" ] && cp "$CLAUDE_JSON" "$BACKUP_DIR/claude.json.bak"
    [ -f "$SETTINGS_JSON" ] && cp "$SETTINGS_JSON" "$BACKUP_DIR/settings.json.bak"
    [ -f "$SETTINGS_LOCAL" ] && cp "$SETTINGS_LOCAL" "$BACKUP_DIR/settings.local.json.bak"
    [ -f "$CLAUDE_DIR/CLAUDE.md" ] && cp "$CLAUDE_DIR/CLAUDE.md" "$BACKUP_DIR/CLAUDE.md.bak"

    # Backup existing agents/skills
    [ -d "$CLAUDE_DIR/agents" ] && cp -r "$CLAUDE_DIR/agents" "$BACKUP_DIR/agents.bak" 2>/dev/null || true
    [ -d "$CLAUDE_DIR/skills" ] && cp -r "$CLAUDE_DIR/skills" "$BACKUP_DIR/skills.bak" 2>/dev/null || true

    # Mark what existed before install (for clean uninstall on fresh machines)
    touch "$BACKUP_DIR/.manifest"
    [ -f "$CLAUDE_JSON" ] && echo "claude.json" >> "$BACKUP_DIR/.manifest"
    [ -f "$SETTINGS_JSON" ] && echo "settings.json" >> "$BACKUP_DIR/.manifest"
    [ -f "$SETTINGS_LOCAL" ] && echo "settings.local.json" >> "$BACKUP_DIR/.manifest"
    [ -f "$CLAUDE_DIR/CLAUDE.md" ] && echo "CLAUDE.md" >> "$BACKUP_DIR/.manifest"

    ok "Backup complete"
}

# ============================================================================
# Install agents
# ============================================================================

install_agents() {
    info "Installing agents..."
    mkdir -p "$CLAUDE_DIR/agents"

    for agent_file in "$SCRIPT_DIR/agents"/*.md; do
        [ -f "$agent_file" ] || continue
        local name=$(basename "$agent_file")
        cp "$agent_file" "$CLAUDE_DIR/agents/$name"
        ok "  Agent: $name"
    done
}

# ============================================================================
# Install skills
# ============================================================================

install_skills() {
    info "Installing skills..."
    mkdir -p "$CLAUDE_DIR/skills"

    for skill_dir in "$SCRIPT_DIR/skills"/*/; do
        [ -d "$skill_dir" ] || continue
        local name=$(basename "$skill_dir")
        mkdir -p "$CLAUDE_DIR/skills/$name"
        cp -r "$skill_dir"* "$CLAUDE_DIR/skills/$name/" 2>/dev/null || true
        ok "  Skill: $name"
    done

    # Install ui-ux-pro-max full skill from source repo (includes scripts + data)
    info "  Fetching UI/UX Pro Max scripts and data from GitHub..."
    local UIUX_TMP=$(mktemp -d)
    if git clone --depth 1 https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git "$UIUX_TMP" 2>/dev/null; then
        # Copy scripts and data from src/ into the skill directory
        if [ -d "$UIUX_TMP/src/ui-ux-pro-max/scripts" ]; then
            cp -r "$UIUX_TMP/src/ui-ux-pro-max/scripts" "$CLAUDE_DIR/skills/ui-ux-pro-max/"
            ok "  UI/UX Pro Max scripts installed"
        fi
        if [ -d "$UIUX_TMP/src/ui-ux-pro-max/data" ]; then
            cp -r "$UIUX_TMP/src/ui-ux-pro-max/data" "$CLAUDE_DIR/skills/ui-ux-pro-max/"
            ok "  UI/UX Pro Max data files installed"
        fi
        if [ -d "$UIUX_TMP/src/ui-ux-pro-max/templates" ]; then
            cp -r "$UIUX_TMP/src/ui-ux-pro-max/templates" "$CLAUDE_DIR/skills/ui-ux-pro-max/"
            ok "  UI/UX Pro Max templates installed"
        fi
        rm -rf "$UIUX_TMP"
    else
        warn "  Failed to clone UI/UX Pro Max repo. Install manually:"
        warn "  Run in Claude Code: /install-skill https://github.com/nextlevelbuilder/ui-ux-pro-max-skill"
        rm -rf "$UIUX_TMP"
    fi
}

# ============================================================================
# Install CLAUDE.md
# ============================================================================

install_claude_md() {
    info "Installing global CLAUDE.md..."

    if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
        warn "Existing CLAUDE.md found. Replacing (backup saved)."
    fi

    cp "$SCRIPT_DIR/claude-md/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
    ok "CLAUDE.md installed"
}

# ============================================================================
# Install hooks (merge into settings.json, preserving existing hooks)
# ============================================================================

install_hooks() {
    info "Installing hooks into settings.json..."

    if [ ! -f "$SETTINGS_JSON" ]; then
        # No existing settings — just copy ours
        cp "$SCRIPT_DIR/hooks/settings.json" "$SETTINGS_JSON"
        ok "Created new settings.json with hooks"
        return
    fi

    # Merge hooks into existing settings.json (preserves other hook events, deduplicates)
    export _SETTINGS_JSON="$SETTINGS_JSON"
    export _HOOKS_JSON="$SCRIPT_DIR/hooks/settings.json"
    python3 -c "
import json, os

settings_path = os.environ['_SETTINGS_JSON']
hooks_path = os.environ['_HOOKS_JSON']

with open(settings_path) as f:
    settings = json.load(f)

with open(hooks_path) as f:
    new_hooks_config = json.load(f)

existing_hooks = settings.get('hooks', {})
new_hooks = new_hooks_config.get('hooks', {})

# For each hook event (e.g. PostToolUse), merge arrays with deduplication
for event, new_hook_list in new_hooks.items():
    if event not in existing_hooks:
        existing_hooks[event] = new_hook_list
    else:
        # Deduplicate by comparing the command string of each hook entry
        existing_commands = set()
        for entry in existing_hooks[event]:
            for h in entry.get('hooks', []):
                existing_commands.add(h.get('command', ''))
        for new_entry in new_hook_list:
            is_duplicate = False
            for h in new_entry.get('hooks', []):
                if h.get('command', '') in existing_commands:
                    is_duplicate = True
                    break
            if not is_duplicate:
                existing_hooks[event].append(new_entry)

settings['hooks'] = existing_hooks

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
"
    unset _SETTINGS_JSON _HOOKS_JSON
    ok "Hooks merged into settings.json"
}

# ============================================================================
# Install MCP servers (merge into .claude.json)
# ============================================================================

install_mcp_servers() {
    info "Installing MCP servers..."

    export _CLAUDE_JSON="$CLAUDE_JSON"
    export _MCP_JSON="$SCRIPT_DIR/mcp/mcp-servers.json"
    export _HOME_DIR="$HOME"

    if [ ! -f "$CLAUDE_JSON" ]; then
        # Create minimal .claude.json with MCP servers
        python3 -c "
import json, os

mcp_path = os.environ['_MCP_JSON']
claude_path = os.environ['_CLAUDE_JSON']
home = os.environ['_HOME_DIR']

with open(mcp_path) as f:
    servers = json.load(f)

# Replace __HOME__ placeholder with actual home
servers_str = json.dumps(servers).replace('__HOME__', home)
servers = json.loads(servers_str)

config = {'mcpServers': servers}

with open(claude_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
"
        ok "Created .claude.json with MCP servers"
    else
        # Merge MCP servers into existing .claude.json
        python3 -c "
import json, os

claude_path = os.environ['_CLAUDE_JSON']
mcp_path = os.environ['_MCP_JSON']
home = os.environ['_HOME_DIR']

with open(claude_path) as f:
    config = json.load(f)

with open(mcp_path) as f:
    new_servers = json.load(f)

# Replace __HOME__ placeholder
servers_str = json.dumps(new_servers).replace('__HOME__', home)
new_servers = json.loads(servers_str)

if 'mcpServers' not in config:
    config['mcpServers'] = {}

# Only add servers that don't already exist (don't overwrite user's existing configs)
added = []
skipped = []
for name, server_config in new_servers.items():
    if name not in config['mcpServers']:
        config['mcpServers'][name] = server_config
        added.append(name)
    else:
        skipped.append(name)

with open(claude_path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

if added:
    print('Added: ' + ', '.join(added))
if skipped:
    print('Skipped (already exist): ' + ', '.join(skipped))
"
        ok "MCP servers merged into .claude.json"
    fi

    unset _CLAUDE_JSON _MCP_JSON _HOME_DIR
}

# ============================================================================
# Setup env vars template
# ============================================================================

setup_env_vars() {
    info "Setting up environment variables..."

    if [ -f "$SETTINGS_LOCAL" ]; then
        warn "settings.local.json already exists. Skipping env var setup."
        warn "  Review $SCRIPT_DIR/mcp/env-template.json for required variables."
        return
    fi

    # Create settings.local.json with empty env template
    export _SETTINGS_LOCAL="$SETTINGS_LOCAL"
    export _TEMPLATE_JSON="$SCRIPT_DIR/mcp/env-template.json"
    python3 -c "
import json, os

template_path = os.environ['_TEMPLATE_JSON']
settings_path = os.environ['_SETTINGS_LOCAL']

with open(template_path) as f:
    template = json.load(f)

# Remove the comment key
template.pop('_comment', None)

settings = {
    'permissions': {'allow': []},
    'env': template
}

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
    f.write('\n')
"
    unset _SETTINGS_LOCAL _TEMPLATE_JSON
    chmod 600 "$SETTINGS_LOCAL"
    ok "Created settings.local.json with env var template"
    warn "IMPORTANT: Edit $SETTINGS_LOCAL to add your actual API keys!"
}

# ============================================================================
# Create required directories
# ============================================================================

create_directories() {
    info "Creating required directories..."
    mkdir -p "$HOME/.qdrant/storage"
    ok "Qdrant storage directory ready"
}

# ============================================================================
# Main
# ============================================================================

echo ""
echo "============================================"
echo "  Claude Code Setup Installer"
echo "  Zalo's Configuration Package"
echo "============================================"
echo ""

check_prerequisites
backup_configs
install_agents
install_skills
install_claude_md
install_hooks
install_mcp_servers
setup_env_vars
create_directories

echo ""
echo "============================================"
echo -e "  ${GREEN}Installation complete!${NC}"
echo "============================================"
echo ""
echo "What was installed:"
echo "  - 4 custom agents (qa-agent, safe-planner, live-test, frontend-specialist)"
echo "  - 3 skills (ui-ux-pro-max, frontend-design, cf-crawl)"
echo "  - Global CLAUDE.md with workflow automation"
echo "  - PostToolUse hooks (Prettier + Ruff auto-formatting)"
echo "  - 6 MCP servers (context7, playwright, github, supabase, qdrant-memory, knowledge-graph)"
echo ""
echo "Next steps:"
echo "  1. Edit ~/.claude/settings.local.json to add your API keys"
echo "  2. Install global tools if missing:"
echo "     npm install -g prettier"
echo "     pip install ruff uv"
echo "  3. Restart Claude Code to pick up changes"
echo ""
echo "Backups saved to: $BACKUP_DIR"
echo ""
