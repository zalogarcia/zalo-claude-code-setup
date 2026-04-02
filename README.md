# Claude Code Pro Setup

A complete Claude Code configuration package with custom agents, skills, hooks, MCP servers, and workflow automation. One command to install a production-grade Claude Code environment.

## What's Included

### Custom Agents (5)

| Agent                   | Purpose                                                       |
| ----------------------- | ------------------------------------------------------------- |
| **qa-agent**            | Audits code for real, reproducible bugs with severity ratings |
| **safe-planner**        | Maps dependencies and risks before complex changes            |
| **live-test**           | Visual verification in browser via Playwright                 |
| **frontend-specialist** | Production-quality UI with a11y, responsiveness, edge states  |
| **image-craft-expert**  | Crafts optimized text-to-image prompts                        |

### Skills (4)

| Skill               | Purpose                                                                                      |
| ------------------- | -------------------------------------------------------------------------------------------- |
| **ui-ux-pro-max**   | Design intelligence: 50 styles, 21 palettes, 50 font pairings, 20 chart types, 8 tech stacks |
| **frontend-design** | Anti-slop frontend aesthetics with bold design direction                                     |
| **telegram**        | Send messages/files/images via Telegram Bot API                                              |
| **cf-crawl**        | Website crawling via Cloudflare Browser Rendering API                                        |

### MCP Servers (6)

| Server              | Purpose                                        |
| ------------------- | ---------------------------------------------- |
| **context7**        | Documentation lookup for any library/framework |
| **playwright**      | Browser automation for testing                 |
| **github**          | GitHub API integration                         |
| **supabase**        | Supabase database/functions management         |
| **qdrant-memory**   | Semantic search memory (local)                 |
| **knowledge-graph** | Structured entity/relationship memory (local)  |

### Hooks (Auto-formatting)

- **Prettier** — Auto-formats `.ts`, `.tsx`, `.js`, `.jsx`, `.css`, `.json`, `.md`, `.html` on every edit
- **Ruff** — Auto-formats and lints `.py` files on every edit

### Global CLAUDE.md

- Self-learning protocol (learns from corrections)
- Project init protocol (auto-scaffolds `.claude/` config for new projects)
- Automated frontend workflow (design -> build -> verify pipeline)
- Verification-first workflow (always prove it works)
- Subagent orchestration rules
- Context survival strategies

## Quick Install

```bash
git clone https://github.com/YOUR_USERNAME/claude-install-zalo.git
cd claude-install-zalo
./install.sh
```

## What the Installer Does

1. **Backs up** all existing Claude Code configs to `~/.claude/backups/`
2. **Copies** agents to `~/.claude/agents/`
3. **Copies** skills to `~/.claude/skills/`
4. **Installs** global `CLAUDE.md` to `~/.claude/`
5. **Merges** hooks into `~/.claude/settings.json` (preserves existing settings)
6. **Merges** MCP servers into `~/.claude.json` (skips servers that already exist)
7. **Creates** `~/.claude/settings.local.json` with env var template (if not exists)

## Post-Install Setup

### 1. Add Your API Keys

Edit `~/.claude/settings.local.json` and replace placeholder values:

```json
{
  "env": {
    "GITHUB_PAT": "your_github_personal_access_token",
    "SUPABASE_ACCESS_TOKEN": "your_supabase_access_token",
    "TELEGRAM_BOT_TOKEN": "your_token (optional)",
    "TELEGRAM_CHAT_ID": "your_chat_id (optional)",
    "CF_ACCOUNT_ID": "your_cloudflare_account_id (optional)",
    "CLOUDFLARE_API_TOKEN": "your_cloudflare_token (optional)"
  }
}
```

### 2. Install Global Tools

```bash
# Required for hooks
npm install -g prettier
pip install ruff

# Required for qdrant-memory MCP
pip install uv

# Optional but recommended
brew install jq
```

### 3. Restart Claude Code

Close and reopen Claude Code to pick up all changes.

## Uninstall

Restores from the backup created during install:

```bash
./uninstall.sh
```

## File Structure

```
.
├── README.md
├── install.sh              # One-command installer
├── uninstall.sh            # Restore from backup
├── claude-md/
│   └── CLAUDE.md           # Global instructions
├── agents/
│   ├── qa-agent.md
│   ├── safe-planner.md
│   ├── live-test.md
│   ├── frontend-specialist.md
│   └── image-craft-expert.md
├── skills/
│   ├── ui-ux-pro-max/
│   │   └── SKILL.md
│   ├── frontend-design/
│   │   └── SKILL.md
│   ├── telegram/
│   │   └── SKILL.md
│   └── cf-crawl/
│       └── SKILL.md
├── hooks/
│   └── settings.json       # Hook configurations
└── mcp/
    ├── mcp-servers.json    # MCP server configs
    └── env-template.json   # API key template
```

## Default Tech Stack

This setup defaults to:

- **Frontend**: React + TypeScript + Tailwind CSS
- **Backend**: Supabase (Edge Functions, Auth, RLS, Storage)
- **Payments**: Stripe
- **Deployment**: Vercel or Supabase hosting
- **Package manager**: npm
- **Testing**: Vitest for unit, Playwright for e2e

## Automated Frontend Workflow

When you ask Claude to build any UI, it automatically chains:

1. `/ui-ux-pro-max` — Design intelligence (palette, fonts, style)
2. `/frontend-design` — Anti-slop aesthetics
3. `frontend-specialist` agent — Production implementation
4. `live-test` agent — Visual verification in browser

No manual invocation needed.

## License

MIT
