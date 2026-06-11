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

    # Backup existing agents/skills/commands/rules
    [ -d "$CLAUDE_DIR/agents" ] && cp -r "$CLAUDE_DIR/agents" "$BACKUP_DIR/agents.bak" 2>/dev/null || true
    [ -d "$CLAUDE_DIR/skills" ] && cp -r "$CLAUDE_DIR/skills" "$BACKUP_DIR/skills.bak" 2>/dev/null || true
    [ -d "$CLAUDE_DIR/commands" ] && cp -r "$CLAUDE_DIR/commands" "$BACKUP_DIR/commands.bak" 2>/dev/null || true
    [ -d "$CLAUDE_DIR/rules" ] && cp -r "$CLAUDE_DIR/rules" "$BACKUP_DIR/rules.bak" 2>/dev/null || true
    [ -d "$CLAUDE_DIR/workflows" ] && cp -r "$CLAUDE_DIR/workflows" "$BACKUP_DIR/workflows.bak" 2>/dev/null || true
    [ -f "$CLAUDE_DIR/META_RULE.md" ] && cp "$CLAUDE_DIR/META_RULE.md" "$BACKUP_DIR/META_RULE.md.bak" 2>/dev/null || true

    # Mark what existed before install (for clean uninstall on fresh machines)
    touch "$BACKUP_DIR/.manifest"
    [ -f "$CLAUDE_JSON" ] && echo "claude.json" >> "$BACKUP_DIR/.manifest"
    [ -f "$SETTINGS_JSON" ] && echo "settings.json" >> "$BACKUP_DIR/.manifest"
    [ -f "$SETTINGS_LOCAL" ] && echo "settings.local.json" >> "$BACKUP_DIR/.manifest"
    [ -f "$CLAUDE_DIR/CLAUDE.md" ] && echo "CLAUDE.md" >> "$BACKUP_DIR/.manifest"

    ok "Backup complete"
}

# ============================================================================
# Install commands (slash commands)
# ============================================================================

install_commands() {
    info "Installing commands..."
    mkdir -p "$CLAUDE_DIR/commands"

    for cmd_file in "$SCRIPT_DIR/commands"/*.md "$SCRIPT_DIR/commands"/*.sh; do
        [ -f "$cmd_file" ] || continue
        local name=$(basename "$cmd_file")
        cp "$cmd_file" "$CLAUDE_DIR/commands/$name"
        ok "  Command: $name"
    done

    # Copy split-screen-video-scripts subdirectory
    if [ -d "$SCRIPT_DIR/commands/split-screen-video-scripts" ]; then
        mkdir -p "$CLAUDE_DIR/commands/split-screen-video-scripts"
        cp -r "$SCRIPT_DIR/commands/split-screen-video-scripts"/* "$CLAUDE_DIR/commands/split-screen-video-scripts/"
        ok "  Command scripts: split-screen-video-scripts/"
    fi
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

    # Install subagent prompt templates (implementer / spec-reviewer / code-quality-reviewer)
    if [ -d "$SCRIPT_DIR/agents/templates" ]; then
        mkdir -p "$CLAUDE_DIR/agents/templates"
        cp "$SCRIPT_DIR/agents/templates"/*.md "$CLAUDE_DIR/agents/templates/" 2>/dev/null || true
        ok "  Agent templates: $(ls "$SCRIPT_DIR/agents/templates"/*.md 2>/dev/null | wc -l | tr -d ' ') files"
    fi
}

# ============================================================================
# Install rules (shared reference docs @-included by commands and agents)
# ============================================================================

install_rules() {
    info "Installing rules..."
    mkdir -p "$CLAUDE_DIR/rules"

    for rule_file in "$SCRIPT_DIR/rules"/*.md; do
        [ -f "$rule_file" ] || continue
        local name=$(basename "$rule_file")
        cp "$rule_file" "$CLAUDE_DIR/rules/$name"
        ok "  Rule: $name"
    done
}

# ============================================================================
# Install META_RULE.md (re-injected by SessionStart hook)
# ============================================================================

install_meta_rule() {
    info "Installing META_RULE.md..."

    if [ -f "$SCRIPT_DIR/META_RULE.md" ]; then
        cp "$SCRIPT_DIR/META_RULE.md" "$CLAUDE_DIR/META_RULE.md"
        ok "META_RULE.md installed"
    fi
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
}

# ============================================================================
# Install workflows
# ============================================================================

install_workflows() {
    info "Installing workflows..."
    mkdir -p "$CLAUDE_DIR/workflows"

    for wf in "$SCRIPT_DIR/workflows"/*.js; do
        [ -f "$wf" ] || continue
        cp "$wf" "$CLAUDE_DIR/workflows/"
        ok "  Workflow: $(basename "$wf")"
    done
}

# ============================================================================
# Install CLAUDE.md
# ============================================================================

install_claude_md() {
    info "Installing global CLAUDE.md..."

    if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
        warn "Existing CLAUDE.md found. Merging Learned Mistakes section..."
        # Extract existing Learned Mistakes entries (lines after the marker)
        local LEARNED=""
        if grep -q "## Learned Mistakes" "$CLAUDE_DIR/CLAUDE.md"; then
            LEARNED=$(sed -n '/^## Learned Mistakes$/,$ p' "$CLAUDE_DIR/CLAUDE.md" | tail -n +2)
        fi
        cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
        # Re-append preserved Learned Mistakes entries if any existed
        if [ -n "$LEARNED" ]; then
            # Remove the empty placeholder from the new file and append the real entries
            sed -i '' '/^<!-- Add entries here when corrected/d' "$CLAUDE_DIR/CLAUDE.md"
            echo "$LEARNED" >> "$CLAUDE_DIR/CLAUDE.md"
            ok "CLAUDE.md installed (Learned Mistakes preserved)"
        else
            ok "CLAUDE.md installed"
        fi
    else
        cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
        ok "CLAUDE.md installed"
    fi
}

# ============================================================================
# Install hooks (merge into settings.json, preserving existing hooks)
# ============================================================================

install_hooks() {
    info "Installing hooks into settings.json..."

    # Copy hook scripts (referenced by settings.json) into ~/.claude/hooks/
    mkdir -p "$CLAUDE_DIR/hooks"
    for script in continue-if-incomplete.py reset-stop-counter.sh gitleaks-guard.py session-start.sh; do
        if [ -f "$SCRIPT_DIR/hooks/$script" ]; then
            cp "$SCRIPT_DIR/hooks/$script" "$CLAUDE_DIR/hooks/$script"
            chmod +x "$CLAUDE_DIR/hooks/$script"
        fi
    done

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

    # Collect API keys interactively (MCP env vars must be actual values, not references)
    local GITHUB_PAT_VAL=""
    local SUPABASE_TOKEN_VAL=""

    # Check if keys already exist in settings.local.json
    if [ -f "$SETTINGS_LOCAL" ]; then
        GITHUB_PAT_VAL=$(python3 -c "import json; d=json.load(open('$SETTINGS_LOCAL')); print(d.get('env',{}).get('GITHUB_PAT',''))" 2>/dev/null || echo "")
        SUPABASE_TOKEN_VAL=$(python3 -c "import json; d=json.load(open('$SETTINGS_LOCAL')); print(d.get('env',{}).get('SUPABASE_ACCESS_TOKEN',''))" 2>/dev/null || echo "")
    fi

    # Prompt for missing keys
    if [ -z "$GITHUB_PAT_VAL" ] || echo "$GITHUB_PAT_VAL" | grep -q "your_"; then
        echo ""
        info "GitHub Personal Access Token needed for GitHub MCP server."
        info "Get one at: https://github.com/settings/tokens?type=beta"
        read -p "  Enter GitHub PAT (or press Enter to skip): " GITHUB_PAT_VAL || GITHUB_PAT_VAL=""
    fi

    if [ -z "$SUPABASE_TOKEN_VAL" ] || echo "$SUPABASE_TOKEN_VAL" | grep -q "your_"; then
        echo ""
        info "Supabase Access Token needed for Supabase MCP server."
        info "Get one at: https://supabase.com/dashboard/account/tokens"
        read -p "  Enter Supabase token (or press Enter to skip): " SUPABASE_TOKEN_VAL || SUPABASE_TOKEN_VAL=""
    fi

    export _CLAUDE_JSON="$CLAUDE_JSON"
    export _MCP_JSON="$SCRIPT_DIR/mcp/mcp-servers.json"
    export _HOME_DIR="$HOME"
    export _GITHUB_PAT="${GITHUB_PAT_VAL:-__GITHUB_PAT__}"
    export _SUPABASE_TOKEN="${SUPABASE_TOKEN_VAL:-__SUPABASE_ACCESS_TOKEN__}"

    if [ ! -f "$CLAUDE_JSON" ]; then
        # Create minimal .claude.json with MCP servers
        python3 -c "
import json, os

mcp_path = os.environ['_MCP_JSON']
claude_path = os.environ['_CLAUDE_JSON']
home = os.environ['_HOME_DIR']
github_pat = os.environ['_GITHUB_PAT']
supabase_token = os.environ['_SUPABASE_TOKEN']

with open(mcp_path) as f:
    servers = json.load(f)

# Replace all placeholders with actual values
servers_str = json.dumps(servers)
servers_str = servers_str.replace('__HOME__', home)
servers_str = servers_str.replace('__GITHUB_PAT__', github_pat)
servers_str = servers_str.replace('__SUPABASE_ACCESS_TOKEN__', supabase_token)
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
github_pat = os.environ['_GITHUB_PAT']
supabase_token = os.environ['_SUPABASE_TOKEN']

with open(claude_path) as f:
    config = json.load(f)

with open(mcp_path) as f:
    new_servers = json.load(f)

# Replace all placeholders with actual values
servers_str = json.dumps(new_servers)
servers_str = servers_str.replace('__HOME__', home)
servers_str = servers_str.replace('__GITHUB_PAT__', github_pat)
servers_str = servers_str.replace('__SUPABASE_ACCESS_TOKEN__', supabase_token)
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

    # Warn about placeholder values (must check before unset due to set -u)
    if [ "${_GITHUB_PAT:-}" = "__GITHUB_PAT__" ] || [ "${_SUPABASE_TOKEN:-}" = "__SUPABASE_ACCESS_TOKEN__" ]; then
        warn "Some MCP servers have placeholder tokens. Edit ~/.claude.json to add real values."
    fi

    unset _CLAUDE_JSON _MCP_JSON _HOME_DIR _GITHUB_PAT _SUPABASE_TOKEN
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
    mkdir -p "$HOME/.claude"
    ok "Claude directory ready"
}

# ============================================================================
# Install orchestrator
# ============================================================================

install_orchestrator() {
    info "Installing orchestrator..."
    local DASH_DIR="$CLAUDE_DIR/orchestrator"
    mkdir -p "$DASH_DIR"

    for f in server.js dashboard.html package.json start.sh stop.sh .gitignore; do
        if [ -f "$SCRIPT_DIR/orchestrator/$f" ]; then
            cp "$SCRIPT_DIR/orchestrator/$f" "$DASH_DIR/$f"
        fi
    done

    # Copy src/ subtree (Run model, harness adapters)
    if [ -d "$SCRIPT_DIR/orchestrator/src" ]; then
        mkdir -p "$DASH_DIR/src/runs" "$DASH_DIR/src/harness"
        cp -R "$SCRIPT_DIR/orchestrator/src/." "$DASH_DIR/src/"
    fi

    # Make scripts executable
    chmod +x "$DASH_DIR/start.sh" "$DASH_DIR/stop.sh" 2>/dev/null || true

    # Create config.json from example if it doesn't exist
    if [ ! -f "$DASH_DIR/config.json" ]; then
        sed "s|\\\$HOME|$HOME|g" "$SCRIPT_DIR/orchestrator/config.example.json" > "$DASH_DIR/config.json"
        ok "  Created config.json (edit to add your project paths)"
    else
        ok "  config.json already exists (preserved)"
    fi

    # Install npm dependencies
    if command -v npm >/dev/null 2>&1; then
        (cd "$DASH_DIR" && npm install --silent 2>/dev/null) || warn "  npm install failed — run manually in $DASH_DIR"
    fi

    ok "Orchestrator installed to $DASH_DIR"
    info "  Start: $DASH_DIR/start.sh"
    info "  Stop:  $DASH_DIR/stop.sh"
    info "  URL:   http://localhost:7890"
}

# ============================================================================
# Install xbar plugins
# ============================================================================

install_xbar_plugins() {
    local XBAR_DIR="$HOME/Library/Application Support/xbar/plugins"

    # Only install if xbar is present
    if [ ! -d "$XBAR_DIR" ]; then
        warn "xbar plugins directory not found. Skipping xbar installation."
        warn "  Install xbar from https://xbarapp.com/ then re-run."
        return
    fi

    info "Installing xbar plugins..."
    mkdir -p "$XBAR_DIR/scripts"

    for plugin in "$SCRIPT_DIR/xbar/plugins"/*.sh; do
        [ -f "$plugin" ] || continue
        local name=$(basename "$plugin")
        cp "$plugin" "$XBAR_DIR/$name"
        chmod +x "$XBAR_DIR/$name"
        ok "  Plugin: $name"
    done

    for script in "$SCRIPT_DIR/xbar/plugins/scripts"/*; do
        [ -f "$script" ] || continue
        local name=$(basename "$script")
        cp "$script" "$XBAR_DIR/scripts/$name"
        chmod +x "$XBAR_DIR/scripts/$name"
    done
    ok "  Helper scripts installed ($(ls "$SCRIPT_DIR/xbar/plugins/scripts" | wc -l | tr -d ' ') files)"

    ok "xbar plugins installed"
    info "  Refresh xbar to see the autoloop status in your menu bar"
}

# ============================================================================
# Install memory files (design principles, learned patterns)
# ============================================================================

install_memory() {
    info "Installing memory files..."
    local MEM_DIR="$CLAUDE_DIR/projects/-Users-$(whoami)/memory"
    mkdir -p "$MEM_DIR"

    for mem_file in "$SCRIPT_DIR/memory"/*.md; do
        [ -f "$mem_file" ] || continue
        local name=$(basename "$mem_file")
        if [ ! -f "$MEM_DIR/$name" ]; then
            cp "$mem_file" "$MEM_DIR/$name"
            ok "  Memory: $name"
        else
            ok "  Memory: $name (already exists, preserved)"
        fi
    done
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
install_commands
install_agents
install_skills
install_workflows
install_rules
install_meta_rule
install_claude_md
install_hooks
install_mcp_servers
setup_env_vars
create_directories
install_orchestrator
install_xbar_plugins
install_memory

echo ""
echo "============================================"
echo -e "  ${GREEN}Installation complete!${NC}"
echo "============================================"
echo ""
echo "What was installed:"
echo "  - 6 slash commands (autopilot, autopilot-merge, bug, qa-loop, plan, brainstorm)"
echo "  - 7 custom agents (qa-agent, safe-planner, live-test, frontend-specialist, bug-fix, outcomes-grader, brainstorm)"
echo "  - 8 skills (typecheck-and-build, commit-with-heredoc, dev-server-restart, autopilot-collect, frontend-design, create-skill, cf-crawl, live-test-campaign)"
echo "  - 2 workflows (qa-audit, plan-verify)"
echo "  - Global CLAUDE.md with workflow automation"
echo "  - Hooks: PostToolUse formatting (Prettier + Ruff) + Vibe Island bridge (all events)"
echo "  - 4 MCP servers (context7, playwright, github, supabase)"
echo "  - xbar plugins (menu bar status for autoloop + quick launchers)"
echo ""
echo "Next steps:"
echo "  1. Edit ~/.claude/settings.local.json to add your API keys"
echo "  2. Install global tools if missing:"
echo "     npm install -g prettier"
echo "     pip install ruff uv"
echo "  3. Restart Claude Code to pick up changes"
echo ""
echo "See how it all fits together:"
echo "  https://zalogarcia.github.io/zalo-claude-code-setup/visualization/"
echo ""
echo "Backups saved to: $BACKUP_DIR"
echo ""
