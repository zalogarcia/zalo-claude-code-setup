<p align="center">
  <img src="assets/banner.png" alt="Claude Code Pro Setup" width="100%">
</p>

# Claude Code Pro Setup

> One command to turn Claude Code into a production-grade AI engineering environment.

Custom agents, skills, commands, MCP servers, auto-formatting hooks, agentic RAG, and workflow automation — all preconfigured and ready to go.

---

## Recommended Workflow

This is how I use Claude Code to get the best results on any task:

```
Plan + Research  -->  Optimize Plan  -->  Execute in Phases  -->  Verify + Test  -->  Repeat
```

1. **Plan + Research** — Before touching code, have Claude research the problem and produce a written plan (`safe-planner` agent or `/plan`). Understand the blast radius.
2. **Optimize the plan** — Review the plan, ask questions, refine. Get alignment before execution.
3. **Execute in phases** — Break the work into small, shippable phases. Implement one phase at a time.
4. **Verify + test after each phase** — Run builds, tests, and visual checks (`live-test` agent) after every phase. Never stack unverified changes.
5. **Continue implementing** — Move to the next phase only after the current one passes.
6. **Run QA multiple times** — Use the `qa-agent` repeatedly until all bugs are fixed. Don't ship until it passes clean.

This loop ensures nothing slips through. Plan first, execute small, verify always.

---

## Quick Install

### Prerequisites

Make sure these are installed first:

| Tool              | Install Command                                          | Purpose                                           |
| ----------------- | -------------------------------------------------------- | ------------------------------------------------- |
| **Node.js + npm** | [nodejs.org](https://nodejs.org/) or `brew install node` | Required for MCP servers and npx                  |
| **Python 3**      | `brew install python3`                                   | Required for UI/UX Pro Max skill search engine    |
| **jq**            | `brew install jq`                                        | Required for hook JSON parsing                    |
| **Prettier**      | `npm install -g prettier`                                | Auto-formats TS/JS/CSS/JSON/MD/HTML on every edit |
| **Ruff**          | `pip install ruff`                                       | Auto-formats and lints Python on every edit       |
| **uv**            | `pip install uv`                                         | Required for Qdrant memory MCP and repo-graphrag  |
| **Git**           | `brew install git`                                       | Required for cloning UI/UX Pro Max data           |

### Run the Installer

```bash
git clone https://github.com/zalogarcia/zalo-claude-code-setup.git
cd zalo-claude-code-setup
./install.sh
```

The installer will:

1. **Back up** all your existing Claude Code configs to `~/.claude/backups/`
2. **Copy** agents to `~/.claude/agents/`
3. **Copy** commands to `~/.claude/commands/` (21 workflow automations)
4. **Copy** skills to `~/.claude/skills/` (clones UI/UX Pro Max data from GitHub)
5. **Install** global `CLAUDE.md` to `~/.claude/`
6. **Merge** hooks into `~/.claude/settings.json` (preserves your existing hooks)
7. **Merge** MCP servers into `~/.claude.json` (skips servers you already have)
8. **Prompt for API keys** — enters them directly into MCP server configs where they're needed
9. **Create** `~/.claude/settings.local.json` with env var placeholders for Bash tools (if not exists)
10. **Install** repo-graphrag — clones, installs dependencies, configures global git hook for auto-updating code knowledge graphs

Safe to run multiple times — it deduplicates and never overwrites your existing configs.

> **Important:** MCP servers need actual API key values directly in `~/.claude.json`. The `${VAR}` syntax does NOT work for MCP env vars — it only works for Bash tool sessions. The installer handles this for you by prompting during setup.

---

## API Keys: How to Get Them

The installer will prompt you for these during setup. Here's how to get each one:

### GitHub Personal Access Token (required for GitHub MCP)

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens?type=beta)
2. Click **"Generate new token"** (Fine-grained token recommended)
3. Give it a name like `claude-code`
4. Set expiration (90 days recommended)
5. Under **Repository access**, select the repos you want Claude to access
6. Under **Permissions**, grant: `Contents` (read/write), `Pull requests` (read/write), `Issues` (read/write)
7. Click **Generate token** and copy it

### Supabase Access Token (required for Supabase MCP)

1. Go to [supabase.com/dashboard/account/tokens](https://supabase.com/dashboard/account/tokens)
2. Click **"Generate new token"**
3. Give it a name like `claude-code`
4. Copy the token (starts with `sbp_`)

### Cloudflare API Token (optional — for cf-crawl website scraping skill)

1. Go to [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click **"Create Token"**
3. Use the **"Edit Cloudflare Workers"** template (or create custom with Browser Rendering permissions)
4. Copy the token
5. Find your Account ID in the Cloudflare dashboard sidebar

### Telegram Bot Token (optional — for Telegram notifications)

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token
4. Send a message to your bot, then call `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your Chat ID

### n8n API Key (optional — for n8n workflow automation)

1. Open your n8n instance settings
2. Go to API > API Keys
3. Generate a new key

### Where Keys End Up

| Key              | Location                                   | Used By                   |
| ---------------- | ------------------------------------------ | ------------------------- |
| GitHub PAT       | `~/.claude.json` > mcpServers.github.env   | GitHub MCP server         |
| Supabase token   | `~/.claude.json` > mcpServers.supabase.env | Supabase MCP server       |
| Cloudflare token | `~/.claude/settings.local.json` > env      | cf-crawl skill (via Bash) |
| Telegram token   | `~/.claude/settings.local.json` > env      | Telegram skill (via Bash) |
| n8n API key      | `~/.claude.json` > mcpServers.n8n-api.env  | n8n MCP server            |

`~/.claude.json` is local-only and never committed to git. `settings.local.json` is `chmod 600` (owner-only).

### Restart Claude Code

Close and reopen Claude Code to pick up all changes.

---

## What's Included

### Custom Agents (7)

| Agent                   | What It Does                                                                                                                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **qa-agent**            | Audits code for real, reproducible bugs. Categorizes by severity (critical/high/medium/low). Run it after every feature.                                                                    |
| **safe-planner**        | Reads all related code, maps dependencies and risks, produces a rollback-ready plan. Use before any non-trivial change.                                                                     |
| **live-test**           | Opens the app in a real browser via Playwright. Screenshots happy path, edge cases, and 3 responsive breakpoints.                                                                           |
| **frontend-specialist** | Builds production-quality UI with Aceternity UI and shadcn/ui MCP access. Reads Apple HIG principles before coding.                                                                         |
| **bug-fix**             | Traces the full user flow to find root cause. Reads all related code and crafts a comprehensive fix plan before changes.                                                                    |
| **image-craft-expert**  | Crafts optimized prompts and generates images on both Gemini Pro (nano-banana) and ChatGPT (gpt-image-1.5) in parallel.                                                                     |
| **brainstorm**          | Deep-thinking agent that challenges assumptions, eliminates complexity, and stress-tests plans using first principles, Elon Musk's 5-step philosophy, inversion, and second-order thinking. |

### Commands (24)

Slash commands for workflow automation. Invoke with `/<command-name>`.

| Command                | What It Does                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| **ship**               | Full feature delivery: plan → implement → QA loop → wait for push approval                             |
| **deploy-validate**    | Self-healing deployment: pre-deploy QA → deploy → smoke test → validate → approval gate                |
| **autoloop**           | Autonomous optimization loop (Karpathy autoresearch pattern) — iteratively improves code               |
| **autotest**           | Autonomous Playwright-based testing harness — systematically tests web apps                            |
| **bug**                | Bug-fix workflow with agent delegation and QA validation                                               |
| **build-fix**          | Iterative build error detection and fixing                                                             |
| **e2e**                | Generate and run Playwright end-to-end tests                                                           |
| **enhance-audio**      | Audio enhancement using FFmpeg filters (noise removal, normalization)                                  |
| **ghl-upload**         | Upload media to GoHighLevel                                                                            |
| **learn**              | Extract reusable patterns and lessons from the current session into memory                             |
| **nano-banana**        | AI image generation with Gemini (multi-resolution, style transfer, green screen)                       |
| **optimize-video**     | Video optimization and upload to Supabase Storage                                                      |
| **qa-loop**            | Iterative QA loop — finds and fixes bugs until the codebase is clean                                   |
| **redesign**           | UI redesign workflow: brainstorm, mockup generation, implement, visual verification                    |
| **refactor-clean**     | Detect and safely remove dead code, unused dependencies, unnecessary complexity                        |
| **session-save**       | Save session context for continuity across sessions                                                    |
| **split-screen-video** | Create split-screen video from talking-head footage with B-roll and subtitles                          |
| **tdd**                | Strict Test-Driven Development (RED-GREEN-REFACTOR)                                                    |
| **transcribe**         | Audio/video transcription using OpenAI Whisper (99 languages)                                          |
| **view-video**         | Extract frames from video for visual analysis                                                          |
| **brainstorm**         | Deep-analyze a problem, plan, or decision with first principles, inversion, and structured elimination |
| **graph**              | Build or rebuild the repo-graphrag knowledge graph for the current project                             |

### Skills (4)

| Skill               | What It Does                                                                                                                                |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **ui-ux-pro-max**   | Searchable design database: 50 UI styles, 21 color palettes, 50 font pairings, 20 chart types, 8 tech stacks. Invoke with `/ui-ux-pro-max`. |
| **frontend-design** | Anti-slop aesthetic guidelines. Bold design direction, distinctive typography, no generic AI look. Invoke with `/frontend-design`.          |
| **cf-crawl**        | Scrape websites via Cloudflare Browser Rendering API. Single page (sync) or multi-page crawl (async). Invoke with `/cf-crawl`.              |
| **telegram**        | Send messages, files, and images to Telegram via Bot API. Invoke with `/telegram`.                                                          |

### Shared Rules (11)

Authoritative reference docs at `~/.claude/rules/`. Commands and agents `@`-include them; the main thread reads them when the situation applies. Built from the best of `gsd-build/get-shit-done` + `obra/superpowers`.

| Rule                         | What It Governs                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------------- |
| **agent-contracts.md**       | H2 completion markers + DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED status protocol     |
| **gates.md**                 | 4 workflow gate types (pre-flight / revision / escalation / abort) + 5-step Verification Gate   |
| **checkpoints.md**           | Human-in-loop XML schema (`checkpoint:human-verify` / `:decision` / `:human-action`)            |
| **verification-patterns.md** | "Existence ≠ Implementation" — stub-detection greps + wiring checks                             |
| **anti-patterns.md**         | Universal failure modes (placeholders, silent partial completion, drift) + No-Placeholders list |
| **questioning.md**           | Dream-extraction philosophy for requirements gathering                                          |
| **context-budget.md**        | PEAK / GOOD / DEGRADING / POOR tier behaviors + degradation warning signs                       |
| **persuasion-principles.md** | Cialdini-derived patterns for writing rules that actually get followed                          |
| **when-to-parallelize.md**   | 4-criteria decision rule for parallel agent dispatch                                            |
| **problem-solving.md**       | When-stuck dispatch table (inversion / simplification / meta-pattern) + 3+ Fixes Rule           |
| **git-safety.md**            | Staging discipline, pre-op checks, destructive-op approval                                      |

### Meta-Rule (Session-Start Re-injection)

`~/.claude/META_RULE.md` is automatically re-injected at every `startup`, `/clear`, and `/compact` via the `session-start.sh` hook. It names the available primitives (subagents, slash commands, skills, shared rules) and the discipline for routing work — so the orchestrator never forgets the system's shape. Edit freely; the hook reads it fresh each time.

### Agent Prompt Templates (3)

Reusable subagent dispatch templates at `~/.claude/agents/templates/` (from `obra/superpowers` two-stage review pattern):

| Template                            | Used By                                                                   |
| ----------------------------------- | ------------------------------------------------------------------------- |
| **implementer-prompt.md**           | Standard fresh-context implementation dispatch with H2 marker integration |
| **spec-reviewer-prompt.md**         | Stage 1 of two-stage review — verifies spec compliance only               |
| **code-quality-reviewer-prompt.md** | Stage 2 of two-stage review — ship-it judgment with severity buckets      |

### MCP Servers (8)

| Server              | What It Does                                                                                                    |
| ------------------- | --------------------------------------------------------------------------------------------------------------- |
| **context7**        | Documentation lookup for any library or framework (React, Next.js, Supabase, etc.). Always up-to-date.          |
| **playwright**      | Browser automation — navigate, click, fill forms, screenshot. Powers the `live-test` agent.                     |
| **github**          | Full GitHub API — create PRs, manage issues, search code, push files. Requires `GITHUB_PAT`.                    |
| **supabase**        | Manage Supabase projects — run SQL, deploy edge functions, manage migrations. Requires `SUPABASE_ACCESS_TOKEN`. |
| **qdrant-memory**   | Local semantic search memory. Stores patterns, solutions, and decisions across conversations.                   |
| **knowledge-graph** | Local structured memory. Stores entity relationships, configs, and facts across conversations.                  |
| **repo-graphrag**   | Code-aware knowledge graph. Uses Tree-sitter + LightRAG for structural code understanding and planning.         |
| **n8n-api**         | n8n workflow automation API. Trigger workflows, manage executions. Requires `N8N_API_KEY`.                      |

### Agentic RAG — repo-graphrag

Code-aware knowledge graph that gives Claude structural understanding of your codebase — call chains, class hierarchies, cross-file dependencies — not just text search.

**How it works:**

1. **Tree-sitter** parses code into structural entities (classes, functions, methods)
2. **LightRAG** builds a knowledge graph from those entities + documentation
3. Claude uses `graph_query` and `graph_plan` to answer architecture questions and plan implementations

**Automatic updates via git hook:**

A global `post-commit` hook (`~/.git-hooks/post-commit`) incrementally updates the graph after every commit. It's smart about when to run:

| Repo size                   | Behavior                  |
| --------------------------- | ------------------------- |
| **< 30 code/doc files**     | Skipped (grep is enough)  |
| **30+ files**               | Auto-enabled              |
| **Has `.graphrag` file**    | Force enabled (any size)  |
| **Has `.no-graphrag` file** | Force disabled (any size) |

The hook runs in the background — commits are never blocked. Each repo gets its own storage (`storage_<repo-name>`).

**Manual usage:**

```bash
# Build/rebuild graph for current project
claude /graph

# CLI (outside Claude Code)
cd ~/repo-graphrag-mcp && uv run python cli_create.py /path/to/repo storage_my-repo
```

**Requires:** Anthropic API key in `~/repo-graphrag-mcp/.env`

### Autoloop Dashboard

<p align="center">
  <img src="assets/autoloop-infographic.png" alt="Autoloop — Autonomous Code Optimization Loop" width="100%">
</p>

The autoloop system lets Claude Code run autonomous optimization loops on your codebase — think [Karpathy's autoresearch](https://x.com/karpathy/status/1886192184808149383) but for any project. The `/autoloop` command starts a loop that iteratively improves code against a target metric (test scores, performance, quality) without human intervention.

The **dashboard** is the monitoring and control center for these loops:

```
┌─────────────────────────────────────────────────────────────────┐
│  Autoloop                                        ● ONLINE  ⌘   │
├─────────────────────────────────────────────────────────────────┤
│  0 ACTIVE  │  2 COMPLETED  │  18 EXPERIMENTS  │  38h 6m DUR.  │
├──────────────────────────────────────┬──────────────────────────┤
│  STATUS  PROJECT     PROG  SCORE    │  Initializing agent...   │
│  ● my-api       ■■■■■■  94    │  Loading dataset...      │
│  ● frontend     ■■■■■■  100   │  Epoch 12/25 Acc: 91.3%  │
│  ● ml-pipeline  ■■■□□□  87    │  Training model...       │
└──────────────────────────────────────┴──────────────────────────┘
```

**How it works:**

1. You run `/autoloop` in a project with a `briefing.md` (target metric, constraints, approach)
2. The autoloop harness spawns Claude Code in a loop: analyze → plan → implement → test → evaluate score
3. Each iteration is an "experiment" — if the score improves, changes are committed; if not, they're rolled back
4. The loop continues until the target score is reached or you stop it
5. The dashboard shows all active loops, their phases, scores, agent terminal output, and git history

**Dashboard features:**

- **Real-time monitoring** — See which loops are running, their current phase (init → baseline → iterate → evaluate), and live agent output
- **Score tracking** — Each experiment's score is recorded and charted over time
- **Agent terminal** — Live streaming output from the Claude Code agent running each loop
- **Controls** — Start, stop, restart, or reset any loop from the web UI
- **Auto-discovery** — Scans configured directories for `.autoloop/` folders and picks up new projects automatically
- **REST API** — `GET /api/loops`, `GET /api/loop/:id/log`, `POST /api/loop/:id/stop`, etc.

**Architecture:**

- **Server:** Node.js HTTP server on port 7890 (`server.js`)
- **Dashboard:** Single-file SPA with all CSS/JS inline (`dashboard.html`) — Bloomberg-terminal "Mission Control" aesthetic
- **Harness:** Bash script (`autoloop-harness.sh`) that orchestrates the Claude Code loop per-project
- **Config:** `config.json` with watched directories and scan paths

**Getting started:**

```bash
# Start the dashboard server
~/.claude/autoloop-dashboard/start.sh

# Open in browser
open http://localhost:7890

# In any project, create a briefing and start a loop
cd ~/my-project
claude /autoloop
```

### xbar Menu Bar Plugins

macOS menu bar integration via [xbar](https://xbarapp.com/) — see autoloop status at a glance without opening the dashboard.

The autoloop xbar plugin (`003-autoloop.5s.sh`) polls every 5 seconds:

- **Menu bar shows:** `AL:2` (green) when 2 loops are running, `AL` (green) when loops completed, `AL` (gray) when idle
- **Dropdown lists:** Each project with status emoji (🟢 running, ✅ completed, ⚫ stopped) and current phase
- **Quick action:** Click "Open Dashboard" to launch the web UI (auto-starts server if needed)

Additional xbar plugins:

| Plugin                           | What It Does                                                      |
| -------------------------------- | ----------------------------------------------------------------- |
| **001-shortcuts.1d.sh**          | Custom keyboard shortcuts menu for common Claude Code operations  |
| **002-clipboard-snippets.1d.sh** | Clipboard snippet manager for reusable prompts and code fragments |

Plus 21 helper scripts in `scripts/` for launching Claude Code sessions in specific project contexts, clipboard-based prompt workflows (plan-first, bug-fix, verify), and window layout capture/restore.

### Memory Files

Curated design principles and learned patterns that persist across all conversations:

| File                                 | What It Contains                                                                                          |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| **apple_hig_design_principles.md**   | 87 standards across 26 sections from Apple HIG — the frontend agent reads this before writing any UI code |
| **apple_hig_menu_bar_principles.md** | Menu bar anatomy, ordering, labeling, shortcuts from Apple HIG                                            |
| **feedback_finetuning_style.md**     | Learned response style preferences for training data generation                                           |

### Auto-Formatting Hooks

Every time Claude edits a file, it's automatically formatted before you see it:

| File Types                                             | Formatter                    | Install                   |
| ------------------------------------------------------ | ---------------------------- | ------------------------- |
| `.ts` `.tsx` `.js` `.jsx` `.css` `.json` `.md` `.html` | **Prettier**                 | `npm install -g prettier` |
| `.py`                                                  | **Ruff** (format + lint fix) | `pip install ruff`        |

### Vibe Island Integration

Full lifecycle monitoring via hooks — bridges every major event to the Vibe Island notification/telemetry system:

- Session start/end
- Tool use (pre/post)
- Permission requests
- Subagent start/stop
- Compaction events
- User prompt submission
- Stop events
- Status line display

### Global CLAUDE.md

Behavioral rules that make Claude Code significantly more effective:

- **Self-learning** — When you correct Claude, it saves the lesson to prevent repeating mistakes
- **Project init** — Auto-scaffolds `.claude/CLAUDE.md` and `.claude/rules/` for new projects
- **Frontend auto-chain** — Building UI automatically triggers: design search -> aesthetic guidelines -> specialist agent (with Aceternity UI + shadcn/ui MCP access + Apple HIG principles) -> visual verification
- **Verification-first** — Claude proves changes work (build, test, screenshot) instead of saying "this should work"
- **Context survival** — Plans are written to files so they survive compaction and session transfers
- **Subagent orchestration** — Complex work is delegated to specialized agents, keeping the main context clean
- **Persistent memory** — Qdrant (semantic search) + Knowledge Graph (structured facts) + repo-graphrag (code structure) survive across conversations

---

## Automated Frontend Workflow

When you ask Claude to build any UI (page, component, dashboard, landing page), it automatically chains these steps without you asking:

1. **`/ui-ux-pro-max`** — Searches the design database for the right palette, fonts, and style
2. **`/frontend-design`** — Applies anti-slop aesthetic principles (no generic Inter + purple gradient)
3. **`frontend-specialist` agent** — Builds production-quality code with Aceternity UI + shadcn/ui component libraries, reads Apple HIG design principles before writing any code
4. **`live-test` agent** — Opens a browser and screenshots the result for visual verification

No manual invocation needed. Just say "build me a pricing page" and the pipeline runs.

---

## Default Tech Stack

When you don't specify, Claude defaults to:

| Layer               | Default                                       |
| ------------------- | --------------------------------------------- |
| **Frontend**        | React + TypeScript + Tailwind CSS             |
| **Backend**         | Supabase (Edge Functions, Auth, RLS, Storage) |
| **Payments**        | Stripe                                        |
| **Deployment**      | Vercel or Supabase hosting                    |
| **Package manager** | npm                                           |
| **Testing**         | Vitest for unit, Playwright for e2e           |

---

## Dependencies Summary

Everything you need to install for the full setup to work:

```bash
# System tools (macOS)
brew install node python3 jq git

# Global npm packages
npm install -g prettier

# Python packages
pip install ruff uv
```

| Dependency    | Required By                                                 | Required?   |
| ------------- | ----------------------------------------------------------- | ----------- |
| Node.js + npm | MCP servers (github, supabase, playwright, knowledge-graph) | Yes         |
| Python 3      | UI/UX Pro Max search, installer scripts                     | Yes         |
| jq            | Hook JSON parsing                                           | Yes         |
| Git           | Installer (clones UI/UX Pro Max data)                       | Yes         |
| Prettier      | Auto-format hook (TS/JS/CSS/JSON/MD/HTML)                   | Recommended |
| Ruff          | Auto-format hook (Python)                                   | Recommended |
| uv/uvx        | Qdrant memory MCP server                                    | Recommended |

If a recommended tool is missing, the relevant hook or MCP will silently skip — nothing breaks.

---

## File Structure

```
.
├── README.md
├── install.sh                        # One-command installer (backs up first)
├── uninstall.sh                      # Restore from backup
├── claude-md/
│   └── CLAUDE.md                     # Global behavioral instructions
├── agents/
│   ├── qa-agent.md                   # Bug auditor
│   ├── safe-planner.md               # Risk-aware planner
│   ├── live-test.md                  # Browser verification
│   ├── frontend-specialist.md        # UI builder (Aceternity + shadcn MCPs)
│   ├── bug-fix.md                    # Root cause tracer
│   ├── image-craft-expert.md         # AI image generation
│   └── brainstorm.md                 # Deep-thinking problem analyzer
├── commands/
│   ├── autoloop.md                   # Autonomous optimization
│   ├── autotest.md                   # Autonomous testing
│   ├── bug.md                        # Bug-fix workflow
│   ├── build-fix.md                  # Build error fixer
│   ├── e2e.md                        # E2E test generator
│   ├── enhance-audio.md              # Audio enhancement
│   ├── ghl-upload.md                 # GHL media upload
│   ├── learn.md                      # Pattern extraction
│   ├── nano-banana.md                # Image generation
│   ├── optimize-video.md             # Video optimization
│   ├── qa-loop.md                    # QA iteration loop
│   ├── redesign.md                   # UI redesign workflow
│   ├── refactor-clean.md             # Dead code removal
│   ├── session-save.md               # Session persistence
│   ├── split-screen-video.md         # Split-screen video
│   ├── tdd.md                        # Test-driven development
│   ├── transcribe.md                 # Audio transcription
│   ├── view-video.md                 # Video frame extraction
│   ├── brainstorm.md                 # Deep-analyze problems and plans
│   ├── graph.md                      # Build/rebuild code knowledge graph
│   ├── autoloop-harness.sh           # Autoloop shell harness
│   └── split-screen-video-scripts/   # Video processing scripts
│       ├── build_video.sh
│       ├── annotate_broll.py
│       └── generate_subtitles.py
├── skills/
│   ├── ui-ux-pro-max/
│   │   └── SKILL.md                  # Design database
│   ├── frontend-design/
│   │   └── SKILL.md                  # Anti-slop aesthetics
│   ├── cf-crawl/
│   │   └── SKILL.md                  # Web scraper
│   ├── multi-edit/
│   │   └── SKILL.md                  # Heavyweight planning path for refactors/migrations
│   └── telegram/
│       └── SKILL.md                  # Telegram notifications
├── hooks/
│   ├── settings.json                 # Hooks + Vibe Island integration
│   ├── continue-if-incomplete.py     # Stop hook: nudge Claude if it halts mid-task
│   ├── reset-stop-counter.sh         # UserPromptSubmit hook: reset nudge counter
│   └── gitleaks-guard.py             # PreToolUse hook: block git commit/push if gitleaks finds secrets
├── mcp/
│   ├── mcp-servers.json              # 8 MCP server configs
│   └── env-template.json             # API key placeholders
├── graphrag/
│   ├── cli_create.py                 # CLI wrapper for graph_create (used by git hook)
│   ├── post-commit                   # Global git hook (auto-updates knowledge graph)
│   └── env-template                  # Default .env config for repo-graphrag-mcp
├── autoloop-dashboard/
│   ├── server.js                     # Node.js monitoring server (port 7890)
│   ├── dashboard.html                # Single-file web UI (Mission Control)
│   ├── package.json                  # Dependencies (Playwright)
│   ├── config.example.json           # Example config (edit with your paths)
│   ├── start.sh                      # Start server
│   ├── stop.sh                       # Stop server
│   └── .gitignore
└── xbar/
    └── plugins/
        ├── 001-shortcuts.1d.sh       # Keyboard shortcuts menu
        ├── 002-clipboard-snippets.1d.sh  # Clipboard snippets
        ├── 003-autoloop.5s.sh        # Autoloop menu bar monitor
        └── scripts/                  # 21 helper scripts (launchers, clips, layout)
```

---

## Uninstall

Restores everything from the backup created during install:

```bash
./uninstall.sh
```

Handles both scenarios:

- **Had existing configs** — Restores them from backup
- **Fresh install** — Cleanly removes everything that was added

---

## License

MIT
