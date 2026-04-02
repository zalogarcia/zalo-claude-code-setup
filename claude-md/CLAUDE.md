# Global Claude Code Instructions

## Self-Learning Protocol

When the user corrects you, says "no", "wrong", "don't do that", "stop", or otherwise indicates you made a mistake:

1. **Identify the root cause** — what assumption or pattern led to the error?
2. **Update the relevant file immediately**:
   - If the mistake is project-specific → update the project's `.claude/CLAUDE.md` or `.claude/rules/*.md`
   - If the mistake applies globally → update `~/.claude/CLAUDE.md` (this file)
   - If it's about a specific file type → update or create a rule in the project's `.claude/rules/` with the appropriate `paths:` scope
3. **Add it under the `## Learned Mistakes` section** at the bottom of the relevant file
4. Never add vague rules like "be more careful". Be specific: what went wrong, what to do instead.

## Project Init Protocol

When starting work on a new project, or when the user asks to initialize/set up the project for Claude, set up the project's Claude config:

1. **Read the codebase** — scan `package.json`, `tsconfig.json`, directory structure, existing README
2. **Create `.claude/CLAUDE.md`** if it doesn't exist, with:
   - Project overview (tech stack, purpose)
   - Build/dev/test commands
   - Architecture summary (key directories and their purpose)
   - Any non-obvious patterns found in the code
3. **Create `.claude/rules/`** directory with path-scoped rules based on what you find:
   - `frontend.md` — if there's a frontend (React/Next.js/Vue conventions, component patterns)
   - `api.md` — if there's an API layer (validation, error handling, auth patterns)
   - `database.md` — if there's a DB layer (migration conventions, RLS, query patterns)
   - Only create rules files for layers that actually exist in the project
4. **Each rules file** must have a YAML header scoping it:
   ```yaml
   ---
   paths: src/components/**/*.tsx
   ---
   ```
5. **Update these files** as you learn about the project during the session — don't wait for mistakes, add patterns proactively when you discover them

## Workflow Commands

- `/build-fix` — Iteratively fix build errors
- `/refactor-clean` — Detect and remove dead code
- `/tdd` — Test-driven development
- `/e2e` — Generate Playwright end-to-end tests
- `/learn` — Extract reusable patterns from session into memory
- `/session-save` — Save session context for cross-session continuity

## Verification (IMPORTANT)

Always verify your work. This is the single highest-leverage practice:

- After writing code: run the build/lint/typecheck command
- After fixing a bug: run the relevant test or reproduce the fix
- After frontend changes: take a screenshot or check the browser if Playwright is available
- After API changes: curl the endpoint or run the test suite
- If there's no automated way to verify, tell the user what to check manually
- Never say "this should work" — prove it works

## Default Tech Stack Preferences

When the user doesn't specify, default to:

- **Frontend**: React + TypeScript + Tailwind CSS
- **Backend**: Supabase (Edge Functions, Auth, RLS, Storage)
- **Payments**: Stripe
- **Deployment**: Vercel or Supabase hosting
- **Package manager**: npm
- **Testing**: Vitest for unit, Playwright for e2e

## Frontend Workflow (Auto-Chain)

When the user asks to build, design, or create any frontend UI (page, component, landing page, dashboard, etc.), automatically run this pipeline — do NOT wait to be asked:

1. **Design** — Invoke `/ui-ux-pro-max` to get concrete palette, font pairing, and style recommendations for the context
2. **Create** — Apply `/frontend-design` principles (bold direction, anti-slop aesthetics) while writing the code, using the design database output from step 1
3. **Build** — Use the `frontend-specialist` agent for production-quality implementation (a11y, responsiveness, edge states)
4. **Verify** — Launch `live-test` agent to screenshot and confirm it looks right in the browser

Skip steps that don't apply (e.g., skip step 4 if no dev server is running, skip step 3 for simple single-file components you can build inline).

## When to Use Subagents

Subagents protect the main context window and enable parallelism. Use them deliberately:

| Agent                 | When to Use                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `live-test`           | After any frontend/UI change — verify it works in the browser before reporting done              |
| `qa-agent`            | After implementing a feature or before deployment — audit for real bugs                          |
| `safe-planner`        | Before complex refactors, migrations, or multi-file changes — map risks first                    |
| `frontend-specialist` | For building UI components, styling, responsive design, accessibility                            |
| `image-craft-expert`  | For ALL image generation — produces better prompts than inline                                   |
| `Explore`             | For broad codebase questions that need multiple searches — keeps exploration out of main context |

**Rules:**

- **Prefer planning and QA in subagents, not the main thread.** Use `safe-planner` for complex plans (3+ steps, multi-file) and `qa-agent` for audits. Quick inline planning for trivial tasks (via `/plan`) is fine. The main thread is for decisions and implementation.
- Delegate exploration/research to subagents — keep the main context clean and focused
- Launch independent subagents in parallel (single message, multiple Agent calls)
- Use background agents (`run_in_background: true`) when you don't need results immediately
- After frontend changes, proactively use `live-test` to verify — don't wait to be asked
- When a subagent returns findings, synthesize the key points yourself — don't paste the full output back into context
- If a task would require reading 5+ files to understand, use `Explore` or a subagent instead of reading them all in the main thread

## Plans & Context Survival (IMPORTANT)

When creating a non-trivial plan (3+ steps):

- **Write the full plan to a file** — `docs/PLAN.md` or `.claude/PLAN.md` in the project directory. Include every step, acceptance criteria, and current status.
- **Update the plan file** as you complete steps — mark done items, add notes, track blockers.
- This ensures the plan survives compaction, session transfers, and context limits.

When compacting (`/compact`):

- Always include the plan context: `/compact Keep the implementation plan and current progress`
- If a plan file exists, re-read it after compaction to restore full context.
- Never compact mid-step — finish the current step first, update the plan file, then compact.

## Context Window

Prefer CLI tools (gh, supabase CLI) over MCP for simple one-off operations. MCPs consume context.

## Persistent Memory

Two memory MCPs are active: **Qdrant** (semantic search for patterns, solutions, decisions) and **Knowledge Graph** (structured facts, entity relationships, configs).

**Goal**: Important non-obvious learnings survive across conversations. Deduplicate before storing. Skip routine edits, info already in docs, and temporary state.

## Code Quality

- No `console.log` in production code
- No silent failures — handle errors explicitly
- Validate at system boundaries (user input, API responses, webhooks)
- Prefer simple solutions over clever ones
- Don't add features, abstractions, or "improvements" beyond what was asked

## Learned Mistakes

<!-- Add entries here when corrected. Format: "- **Context**: What to do instead (date)" -->
