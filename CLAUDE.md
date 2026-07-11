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

When starting work on a new project, or when the user asks to initialize/set up the project for Claude, **invoke the `repo-init` skill — do not hand-roll the scaffold.** It scans the codebase, verifies (actually runs) the build/test/typecheck commands, and generates `.claude/CLAUDE.md`, path-scoped `.claude/rules/*.md`, and `.claude/VERIFY.md` — the machine-readable verification manifest (deploy surfaces + THE proof signal each deploy claim requires). Idempotent: fills gaps, never clobbers.

- `.claude/VERIFY.md` is the per-repo source of truth for verification. Orchestrators (`/autopilot`, `/bug`, `qa-agent`, `live-test`) read it before claiming anything is tested or live. If it's missing in a repo you're working in, run `/repo-init` (or flag it).
- `~/.claude/scripts/repo-drift-check.sh` lists repos under `~/dev` missing the scaffold.
- **Update these files** as you learn about the project during the session — don't wait for mistakes, add patterns proactively when you discover them. Pipeline changes (new deploy surface, changed CI) must update VERIFY.md in the same commit.

## Workflow Commands

- `/autopilot` — Autonomous multi-phase orchestrator: plan → implement → QA → commit
- `/bug` — Trace, diagnose, fix, validate
- `/qa-loop` — Iterative audit-and-fix loop
- `/goal` — Goal-driven convergence loop: pin goal + acceptance criteria to .claude/GOAL.md, implement → live-verify → repeat until all criteria pass (lighter /autopilot sibling)
- `/plan` — Plan with brainstorm + principles verification
- `/brainstorm` — Deep thinking, challenge assumptions

## Git & Deployment (IMPORTANT)

- **Never push to any remote branch without explicit user permission.** Commit freely, but STOP and ask before `git push`.
- When the user says "push" — confirm the target branch before executing.
- Default working branch is `dev` unless the user specifies otherwise.
- Never force-push to `main` or `dev` without explicit approval.
- If deploying edge functions or running migrations, ask the user first — these affect shared infrastructure.

## Shared Rules (Authoritative)

The meta-rule injected at every session boundary (`~/.claude/META_RULE.md`) names the primitives in this setup. Detailed reference docs live in `~/.claude/rules/` and are `@`-included by commands and agents that depend on them. You should also read them directly when an applicable situation arises.

| Rule                                       | Use When                                                                                                 |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `~/.claude/rules/agent-contracts.md`       | Dispatching or interpreting subagents — H2 markers + DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED |
| `~/.claude/rules/gates.md`                 | 4 workflow gate types + the 5-step Verification Gate Function for "is it really done?"                   |
| `~/.claude/rules/checkpoints.md`           | Inserting human-verify / decision / human-action checkpoints in a long workflow                          |
| `~/.claude/rules/verification-patterns.md` | "Existence ≠ Implementation" — stub-detect greps + wiring checks                                         |
| `~/.claude/rules/anti-patterns.md`         | Universal failure modes (placeholders, silent partial completion, drift)                                 |
| `~/.claude/rules/questioning.md`           | Surfacing the real problem behind the presented one (dream extraction)                                   |
| `~/.claude/rules/context-budget.md`        | PEAK / GOOD / DEGRADING / POOR tier behaviors + degradation warning signs                                |
| `~/.claude/rules/persuasion-principles.md` | Authoring or revising rules in `~/.claude/rules/` or this file                                           |
| `~/.claude/rules/when-to-parallelize.md`   | Deciding whether to dispatch agents in parallel vs. sequential                                           |
| `~/.claude/rules/problem-solving.md`       | When stuck — symptom-to-technique dispatch table + 3+ Fixes Rule                                         |
| `~/.claude/rules/git-safety.md`            | Any git operation — staging, pre-op checks, destructive-op approval                                      |
| `~/.claude/rules/database-safety.md`       | Any database migration — additive-only, non-breaking, expand-contract for breaking changes               |
| `~/.claude/rules/testing-safety.md`        | Live app testing — admin email only, no fake users against live systems                                  |

## Debugging Protocol

When investigating bugs or errors:

1. **Check live evidence FIRST** — Supabase edge function logs, browser console, server logs. Use `mcp__supabase__get_logs` or CLI before forming hypotheses.
2. **Never conclude "no error found"** without checking actual runtime logs from the last 5 minutes.
3. **Trace the full flow** — from user action → frontend → API/edge function → database. Don't guess which layer failed.
4. If the user says "I just reproduced this" — the bug is real. Skip re-verification and go straight to logs.
5. Apply the 4-phase systematic debugging in `~/.claude/agents/bug-fix.md` (Understand symptom → Trace backward → Identify root cause → STOP at 3 failed fixes).
6. When stuck, consult `~/.claude/rules/problem-solving.md` — symptom-to-technique dispatch table (inversion, simplification, root-cause tracing).

## Verification & QA (IMPORTANT)

Always verify your work. This is the single highest-leverage practice. Apply the **Verification Gate Function** in `~/.claude/rules/gates.md` Part 2 — every claim of "done" requires a fresh command, captured output, and reported evidence in the same turn.

- After writing code: run the build/lint/typecheck command
- After fixing a bug: run the relevant test or reproduce the fix
- After frontend changes: take a screenshot or check the browser if Playwright is available
- After API changes: curl the endpoint or run the test suite
- If there's no automated way to verify, tell the user what to check manually
- Never say "this should work" — prove it works (per the Iron Law in `~/.claude/rules/gates.md`)
- **Before marking any feature or fix complete**, invoke the `typecheck-and-build` skill — it standardizes the tsc+build chain with smart failure-region extraction. Do not roll your own `npm run build 2>&1 | tail -N` invocation; the skill picks the right tail and reports exit codes consistently.
- For commits, invoke the `commit-with-heredoc` skill — it encodes the correct `$(cat <<'EOF' … EOF)` quoting and the Co-Authored-By trailer.
- For dev-server restarts (after env changes, before live-test, or when the server is stuck), invoke the `dev-server-restart` skill — it kills by port, restarts with nohup, polls for readiness, and smoke-tests a route. Do not hand-write the `pkill && sleep && curl` chain.
- For post-ship live verification of a feature against the deployed app ("live test everything", "make sure it's perfect", pre-launch checks), invoke the `live-test-campaign` skill — it runs the full campaign methodology: brainstorm design-review first (finds bugs from code before testing), Explore inventory, live-vs-lab split, the 9-phase cheapest-first ladder, positive-evidence discipline, and the state-neutralization protocol. Do not improvise an ad-hoc smoke test for these requests.
- **3+ file edits → mandatory QA, tiered by blast radius.** Any turn that touches 3 or more files MUST run a QA audit before claiming done. A single build/typecheck is NOT sufficient for either tier — audits catch integration bugs, wiring issues, and logic errors that static checks miss. Pick the tier by risk:
  - **Full `/qa-loop`** (the default): new features or endpoints, logic changes, anything touching auth/payment/data-deletion/migration paths, new dependencies, or >150 changed lines. The iterative loop: `qa-agent` audits → fix bugs → re-audit → repeat until clean or cap hit.
  - **Light tier — one `qa-agent` dispatch, no loop** (allowed ONLY when ALL hold): ≤150 changed lines total, behavior-preserving or narrowly additive (config values, copy, docs/rules edits, mechanical renames), no auth/payment/data-deletion/migration paths, no new dependencies. Findings still get fixed; a second dispatch confirms the fixes.
  - State which tier you chose and why. When in doubt → full loop. (Basis: the 2026-07 audit showed full loops catching real prod-bound bugs on feature work AND spending ~1.4M tokens confirming 0 findings on 100-line fixes — the tier split keeps the catches without the tax.)
  - If already inside `/autopilot` or `/bug` (which have their own QA phases), that satisfies this rule.
- **Kill stale background processes** before starting new dev servers or builds (`pkill -f 'next dev' || true`)
- For "did I really build it?" doubt, apply `~/.claude/rules/verification-patterns.md` — Existence ≠ Implementation; use the stub-detect greps.

## Default Tech Stack Preferences

Primary stack: **TypeScript/JavaScript (Next.js)**, **Supabase** (Edge Functions, Auth, RLS, Storage, DB), **Vercel** deployment. Always use TypeScript for new files unless explicitly told otherwise.

When the user doesn't specify, default to:

- **Frontend**: React + TypeScript + Tailwind CSS
- **Backend**: Supabase (Edge Functions, Auth, RLS, Storage)
- **Payments**: Stripe
- **Deployment**: Vercel or Supabase hosting
- **Package manager**: npm
- **Testing**: Vitest for unit, Playwright for e2e

## Design Principles

- When proposing architecture or UX changes, **present the direct/simple approach first**. Avoid adding unnecessary queues, intermediary steps, or over-engineered patterns unless explicitly requested.
- For CSS/UI fixes: **audit all style sources** (parent components, layouts, global CSS, Tailwind config) before making changes. Account for specificity, inheritance, and layout conflicts in a single pass — don't iterate blindly.
- Prefer flat, obvious implementations over abstracted clever ones.

## Frontend Workflow (Opt-In)

When the user asks to build, design, or create frontend UI (page, component, landing page, dashboard, etc.), **consider** this pipeline. It's opt-in, not mandatory — invoke when the work is genuinely UI-design-heavy (a new page, a component library piece, a visual redesign). Skip for trivial copy/style tweaks or one-line CSS fixes.

1. **Design** — Apply the `frontend-design` skill's principles (bold direction, anti-slop aesthetics, concrete palette and font pairing) while writing the code.
2. **Build** — For non-trivial implementation, use the `frontend-specialist` agent. It has scoped MCP servers for Aceternity UI and shadcn/ui. Apply Apple HIG-quality design principles (bold direction, anti-slop aesthetics, generous whitespace, clear hierarchy, no decoration without function).
3. **Verify** — Launch the `live-test` agent to screenshot and confirm it looks right in the browser.

This chain has been historically underused — don't force it for small changes. For full-page or component-library work, the full chain is high-value.

## Video B-Roll Production

- For branded motion-graphics "slides b-roll" (VSL-style slides, YouTube segment graphics, teleprompter-script b-roll), invoke the `machine-editorial-broll` skill — it maps script beats to the Machine Editorial comp archetypes in the Remotion studio at `~/dev/operator-broll`. Do not hand-roll Remotion comps outside the studio's token/move system.
- Disambiguation: `machine-editorial-broll` = branded typographic slide graphics (Remotion). `seedance` = AI-generated _footage_ (people, scenes, camera moves). A "b-roll" request for graphics/slides goes to the former; filmed-looking clips go to the latter.

## When to Use Subagents

Subagents protect the main context window and enable parallelism. Use them deliberately:

| Agent                 | When to Use                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `live-test`           | After any frontend/UI change — verify it works in the browser before reporting done              |
| `qa-agent`            | After implementing a feature or before deployment — audit for real bugs                          |
| `safe-planner`        | Before complex refactors, migrations, or multi-file changes — map risks first                    |
| `frontend-specialist` | For building UI components, styling, responsive design, accessibility                            |
| `brainstorm`          | For deep problem analysis, challenging assumptions, and stress-testing plans before committing   |
| `Explore`             | For broad codebase questions that need multiple searches — keeps exploration out of main context |

**Rules:**

- **Subagent model policy — split by leverage.** Thinking agents whose single, low-volume dispatch cascades downstream pin `model: fable` in frontmatter: `brainstorm`, `safe-planner`, `bug-fix` (plan/diagnosis quality is worth 2× on one dispatch). Everything else runs Opus 4.8 (`claude-opus-4-8`): `qa-agent`, `outcomes-grader`, `live-test`, `frontend-specialist`, `image-craft-expert` pin it in frontmatter; built-in agents with no definition file (`Explore`, `general-purpose`, `Plan`, `claude`, `claude-code-guide`) inherit the session model, so pass `model: "opus"` explicitly on every Agent dispatch and on Workflow `agent()` calls. Rationale: fan-out and high-token work (QA loops, exploration, implementation) gets half-price tokens ($5/$25 vs $10/$50 per MTok) with no measurable quality loss, protects Fable's session limit from multi-agent exhaustion (2026-07-07 incident), and Opus verifying Fable's work adds a second-opinion dynamic. If a fable-pinned dispatch fails on a Fable usage limit, re-dispatch that one agent on `opus` — never `sonnet`. (Updated 2026-07-09.)
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

## Context Window & MCP vs CLI

Most MCP tools are **deferred** (schemas not loaded until invoked via `ToolSearch`), so the old "MCPs consume context" concern no longer applies broadly. Choose per case:

- **`gh` CLI** — preferred over the GitHub MCP. The CLI is lightweight and pulls no secrets into the prompt.
- **Supabase MCP** — **PREFERRED** over raw `curl` against `api.supabase.com` or inline access tokens. Use `mcp__supabase__execute_sql`, `mcp__supabase__deploy_edge_function`, `mcp__supabase__get_logs`, `mcp__supabase__apply_migration`, etc. The MCP server holds the `SUPABASE_ACCESS_TOKEN` — never echo it inline. **Writing `Authorization: Bearer sbp_...` in a Bash command is a security bug; use the MCP instead.**
- **Supabase CLI** — fine for local-dev workflows (`supabase start`, `supabase functions serve`) where no token is involved. Avoid for management-plane operations.
- **Other MCPs** (Playwright, Context7, Vercel) — use as designed; they're all deferred.

## Code Quality

- No `console.log` in production code
- No silent failures — handle errors explicitly
- Validate at system boundaries (user input, API responses, webhooks)
- Prefer simple solutions over clever ones
- Don't add features, abstractions, or "improvements" beyond what was asked

## Learned Mistakes

<!-- Add entries here when corrected. Format: "- **Context**: What to do instead (date)" -->

- **Sleep-polling**: foreground `sleep`/poll loops are blocked by the harness — use `run_in_background: true` for long commands, or the Monitor tool with an until-condition, to wait (2026-07-02)
- **Background agents**: after dispatching background agents, don't strand their completion notifications — stay resumable (end the turn cleanly with pending work noted) or schedule a wakeup to collect results (2026-07-02)
