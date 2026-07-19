---
name: repo-init
description: 'Scaffold per-repo Claude excellence in the current repo: scan the codebase, actually run (verify) the build/test/typecheck/lint commands, and generate .claude/CLAUDE.md, path-scoped .claude/rules/*.md, the machine-readable .claude/VERIFY.md verification manifest — deploy surfaces plus THE proof signal each deploy claim requires — and its runnable projection .claude/verify.sh (proof signals as executable checks with exit codes). Use when the user says "initialize repo", "init this repo", "set up project for Claude", "new repo", "scaffold claude config", or when starting work in a repo missing .claude/CLAUDE.md. Idempotent — fills gaps in existing scaffolds, never clobbers. Implements the global Project Init Protocol and prevents "deploy verified" overclaims that cite the wrong pipeline''s signal (documented incident: ECS green cited as proof for a Vercel-deployed dashboard change). Pair with ~/.claude/scripts/repo-drift-check.sh to find repos under ~/dev missing the scaffold.'
---

Make this repo's tribal knowledge self-installing: one pass that scans, **verifies with fresh evidence**, and writes the scaffold (`.claude/CLAUDE.md`, `.claude/rules/*.md`, `.claude/VERIFY.md`, and its runnable projection `.claude/verify.sh`) so every future session — human-driven or `/autopilot` — starts with proven commands and the correct deploy-proof signals instead of re-learning them expensively. `VERIFY.md` is the human-readable manifest; `verify.sh` makes its proof signals executable, so a claim of "tested" or "live" can be *run*, not just read and voluntarily obeyed.

## When to invoke

- User says "initialize repo", "set up this project for Claude", "scaffold claude config", "/repo-init"
- Starting work in a repo that has no `.claude/CLAUDE.md` (the Project Init Protocol trigger)
- `~/.claude/scripts/repo-drift-check.sh` flagged this repo as missing pieces
- After a deploy pipeline changes (new Vercel project, new ECS service, edge functions added) — re-run to update `VERIFY.md`

Skip for: non-git scratch directories, autopilot worktrees (`*-autopilot-*` — they inherit the parent repo's scaffold), repos you're touching for a single one-line fix and will never revisit.

## Why VERIFY.md is the key artifact

A 60-session analysis showed the best-instrumented repo succeeds because of accumulated repo knowledge: how to prove THIS repo's deploys are live, which commands actually work, where the admin test account lives. Documented incident: a "deploy verified" overclaim happened because a dashboard commit deploys via **Vercel** while the cited proof signal was **ECS** — dashboard-only commits skip every ECS job, so ECS green proved nothing. `VERIFY.md` is the machine-readable manifest that orchestrators (`/autopilot`, `/bug`, `qa-agent`, `live-test-campaign`) read BEFORE claiming anything is tested or live.

## Step 1 — Scan the repo

From the repo root (confirm with `git rev-parse --show-toplevel`), gather — read files, don't guess:

| What                | Where to look                                                                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Stack & framework   | `package.json` (deps, scripts, workspaces), `tsconfig.json`, `next.config.*`, `vite.config.*`, `turbo.json`, `deno.json`, `Cargo.toml`                                                |
| Commands            | `package.json` scripts (`build`, `test`, `typecheck`, `lint`), `scripts/` dir (e.g. a `check.sh`), `Makefile`, CI workflow steps                                                      |
| Formatter / hooks   | `.husky/`, `.githooks/`, `core.hooksPath` in git config, `.prettierrc*`, `deno fmt` config, `lint-staged` config, gitleaks hooks                                                      |
| Deploy surfaces     | `vercel.json` / `.vercel/`, ECS/task-def references (`.github/workflows/*.yml`, `taskdef*.json`, `Dockerfile*`), `supabase/` dir + `supabase/functions/`, `fly.toml`, `wrangler.toml` |
| CI                  | `.github/workflows/*.yml` — which jobs run on which paths (path filters are exactly where the ECS-vs-Vercel trap lives)                                                               |
| Admin/test accounts | `.env*` files, existing `.claude/test-identities.md` — **read key NAMES only** (`grep -oE '^[A-Z0-9_]+' .env`). NEVER echo a secret value into any generated file or the conversation |
| Data layer          | `supabase/migrations/`, `prisma/`, `drizzle/`, existing `docs/SCHEMA-PROD.md` snapshot                                                                                                |
| Existing scaffold   | `.claude/CLAUDE.md`, `.claude/rules/`, `.claude/VERIFY.md`, `.claude/test-identities.md`, `docs/RUNBOOK.md`, `docs/recipes/`                                                          |

For large/unfamiliar repos, dispatch an `Explore` agent for the scan instead of reading 20 files in the main thread.

## Step 2 — Verify before writing (Iron Law)

**Every command written into the manifest must have been actually run in this session, with its exit code captured — or be explicitly marked `UNVERIFIED`.** No guessed commands. Per `~/.claude/rules/gates.md`: no claims without fresh evidence.

- Run typecheck/lint/build via the `typecheck-and-build` skill conventions (redirect to file, read `$?` — no pipes; zsh `PIPESTATUS` trap).
- Run the test suite once and record the suite size (`N tests`) from real output. If the suite needs live credentials or exceeds a sane timeout (~5 min), mark it `UNVERIFIED (reason)` rather than blocking init.
- Deploy **proof signals** usually can't be exercised at init time (no fresh deploy to observe). Document the signal from pipeline evidence (CI workflow files, `vercel.json`, task definitions) and mark the row `UNVERIFIED` until a real deploy confirms it. Never invent a signal.
- Anything `UNVERIFIED` goes into the final summary table for the user to confirm.

## Step 3 — Generate (idempotent — fill gaps, never clobber)

**If a file already exists: Read it, identify missing sections, and propose a diff of additions (or append clearly-scoped new sections). Never overwrite existing content.** If a file is absent, Write it whole.

### 3a. `.claude/CLAUDE.md`

Model it on the gold standard (`~/dev/delta-agents/.claude/CLAUDE.md`): project overview + quick reference (live URL, repo, infra ids), monorepo/directory layout with one-line purposes, architecture rules, key patterns, **verified** commands, environment (var NAMES only), tech stack, and a `## Learned Mistakes / Gotchas` section (seed it empty or with anything discovered during the scan — the Self-Learning Protocol appends here over time).

### 3b. `.claude/rules/*.md` — only for layers that actually exist

Per the Project Init Protocol: `frontend.md` (component patterns, styling conventions), `api.md` (validation, error handling, auth patterns), `database.md` (migration conventions, RLS, query patterns). Each with a `paths:` YAML header scoping it:

```yaml
---
paths: apps/dashboard/**/*.tsx
---
```

Content comes from patterns observed in the scan (real conventions in real files), not from generic best practices. A rules file you couldn't fill with repo-specific content is a rules file that shouldn't exist yet.

### 3c. `.claude/VERIFY.md` — THE key artifact

Canonical template (fill every `<placeholder>` from scan + verification evidence; delete example rows):

```markdown
# VERIFY.md — <repo> verification manifest

<!-- Machine-readable source of truth. Orchestrators (/autopilot, /bug, qa-agent) read this BEFORE claiming anything is tested or live. Keep updated when pipelines change. -->

## Commands (each verified on <date>)

- typecheck: `<cmd>`
- build: `<cmd>`
- test: `<cmd>` (suite size: N tests)
- lint: `<cmd>`

## Formatter / hooks

- <e.g. prettier via husky pre-commit — ALWAYS format-then-stage>
- commit hooks: <gitleaks etc., known timeouts>

## Deploy surfaces & THE proof signal for each

<!-- One row per independently-deployed surface. The proof signal is what a green deploy claim REQUIRES — not CI status. -->

| Surface            | Pipeline                           | Proof a change is LIVE                                              |
| ------------------ | ---------------------------------- | ------------------------------------------------------------------- |
| <dashboard>        | <Vercel project X on push to main> | <vercel inspect prod + grep live bundle for a change-unique string> |
| <gateway/services> | <ECS cluster Y, services list>     | <per-service image tag == pushed SHA + /health 200>                 |
| <edge functions>   | <supabase deploy via PR/CI>        | <function version bump N→N+1 + get_logs clean 5 min>                |

## Deploy traps

<!-- e.g. "dashboard-only commits SKIP all ECS jobs — ECS green is NOT proof for dashboard changes" -->

## Live-test safety

- admin/test account: <where configured — never inline the secret>
- designated test tenant: <name/id>
- state-neutralization: <how to restore prod state after live tests>

## Data layer

- schema snapshot: <path> (regen: /schema-snapshot)
- migrations dir: <path> — additive-only per ~/.claude/rules/database-safety.md
```

Rules for filling it:

- **One row per independently-deployed surface.** If two things can deploy separately, they get separate rows with separate proof signals.
- **Proof signal ≠ CI status.** A green pipeline is a precondition, not proof. Proof observes the LIVE artifact: bundle grep for a change-unique string, image tag == pushed SHA, function version bump + clean logs.
- **Deploy traps** is where path-filter interactions live — write down every "surface A's commits skip surface B's pipeline" fact you find in CI workflow files.
- Unverifiable-at-init rows carry `UNVERIFIED` inline; whoever performs the first real deploy upgrades them with evidence and a date.
- Suite size `N tests` comes from actual test output, never estimated.

### 3d. `.claude/verify.sh` — the runnable projection of VERIFY.md

**Whenever this skill creates or updates `.claude/VERIFY.md`, generate a sibling `.claude/verify.sh`.** VERIFY.md is prose an agent must read and voluntarily obey — costing tokens every session and complying only probabilistically. `verify.sh` turns each proof signal into an executable check with an exit code. VERIFY.md stays the human-readable source of truth; `verify.sh` is its executable projection, and the two stay in sync — regenerate `verify.sh` on any VERIFY.md change, under the same idempotent fill-gaps-never-clobber policy as every other artifact here.

Contract (hold it exactly):

- `#!/usr/bin/env bash`, `set -uo pipefail`, `chmod +x` it. `cd` to the repo root off `${BASH_SOURCE[0]}` so it runs from any cwd.
- **Modes:**
  - `./verify.sh` (default) runs the **LOCAL gate** — the typecheck / lint / build / test commands this skill actually verified for the repo, each as a named check.
  - `./verify.sh deploy <surface>` runs **THE proof-signal check** for that deploy surface from VERIFY.md (e.g. active ECS image tag == pushed/HEAD SHA, a health/version endpoint returns expected, a served-bundle grep). One function per surface named in the VERIFY.md deploy table; accept `all`.
  - `./verify.sh --list` prints the available checks + surfaces.
- **Output discipline:** exactly one `PASS <check>` / `FAIL <check>` / `SKIP <check> (<reason>)` line per check; a final summary line `VERIFY: <n_pass>/<n_total> passed, <n_skip> skipped`; exit 0 only when nothing FAILed.
- **SKIP — never FAIL, never silent-pass — for any check whose creds/network aren't available where it runs** (AWS creds, Vercel CLI, a management-plane MCP). The SKIP reason carries the exact command a human/agent should run. Distinguish a connection-level failure (network down → SKIP) from a reachable-but-wrong response (→ FAIL): e.g. curl exit 6/7/28 → SKIP, HTTP non-200 → FAIL.
- **Slow local checks stay optional-fast:** include the real test suite, but honor `VERIFY_QUICK=1` to emit `SKIP test (...)` instead of running it.
- **Derivation rule (non-negotiable):** every check is derived from VERIFY.md content OR a command this skill actually ran and verified — never invented. A signal that can't run in a shell (Supabase MCP `list_migrations`, a change-unique bundle grep that needs the diff + a gitignored project link) is a SKIP that names the real command, not a fake automated PASS.

Idempotency: if `verify.sh` already exists, reconcile it against the current VERIFY.md (add missing surface functions, correct drifted commands/URLs) rather than clobbering local edits.

Reference implementation: `~/dev/delta-agents/.claude/verify.sh` (the flagship — Turborepo local gate + six path-gated ECS image-tag surfaces + gateway `/health` + Vercel dashboard reachability + a Supabase-MCP migrations SKIP).

## Step 4 — Register (commit policy)

Default: **the scaffold gets committed.** The gold-standard repo (delta-agents) tracks `.claude/` in git (`git ls-files .claude/` is non-empty; `git check-ignore .claude` says not ignored) — that's what makes the knowledge survive clones, worktrees, and teammates.

- Check `git check-ignore -q .claude` first. If the repo's existing policy ignores `.claude/`, respect it and tell the user the scaffold is local-only.
- Otherwise stage the generated files **by name** (never `git add .`, per `~/.claude/rules/git-safety.md`) and offer to commit via the `commit-with-heredoc` skill. Do not push — pushing needs explicit user permission.
- Never commit `.env*` or anything holding a secret value; the scaffold references var NAMES only.

## Step 5 — Report (output shape)

End with a summary table + the UNVERIFIED list — never paste generated file bodies back into the conversation:

```
| Artifact                    | Action  | Notes                                  |
|-----------------------------|---------|----------------------------------------|
| .claude/CLAUDE.md           | created | commands verified: typecheck, build    |
| .claude/rules/frontend.md   | created | paths: apps/dashboard/**               |
| .claude/rules/database.md   | skipped | no DB layer in repo                    |
| .claude/VERIFY.md           | updated | added edge-functions surface row       |
| .claude/verify.sh           | created | 4 local checks + N deploy surfaces; +x |

UNVERIFIED (needs you): test command (suite requires live Redis); Vercel proof signal (no deploy observed yet)
```

## Anti-patterns

- ❌ **Writing a command you didn't run.** A guessed `npm run typecheck` that doesn't exist poisons every future session that trusts the manifest. Run it or mark `UNVERIFIED`.
- ❌ **One proof signal for all surfaces.** The documented incident is exactly this — ECS green cited for a Vercel-deployed dashboard change. Per-surface rows, always.
- ❌ **Overwriting an existing CLAUDE.md/VERIFY.md.** Existing content is accumulated repo knowledge — the thing this skill exists to preserve. Fill gaps only.
- ❌ **Echoing secret values** into generated files or the conversation while scanning `.env*`. Key names only; the manifest says _where_ the secret is configured, never what it is.
- ❌ **Generic rules files** ("write clean components", "handle errors properly"). If the scan didn't reveal a repo-specific convention, don't write the file.
- ❌ **Creating rules for layers that don't exist** — a `database.md` in a static site repo is noise that misfires forever.
- ❌ **`git add .` to stage the scaffold** — stage the generated files by name.
- ❌ **Inventing a `verify.sh` check.** A `deploy` function that echoes `PASS` without querying the live artifact, or a local check for a command that doesn't exist, is the runnable version of a guessed manifest command — it poisons every future run that trusts the exit code. Every check maps to a VERIFY.md signal or a verified command; an unrunnable signal is `SKIP` with the real command, never a fake pass.
- ❌ **Letting `verify.sh` drift from VERIFY.md.** They are one source of truth and its projection. Change VERIFY.md → regenerate `verify.sh` in the same pass; never update one and leave the other stale.

## Edge cases

- **Monorepo with per-app pipelines** — each app that deploys independently is its own surface row; commands section notes root-level vs `--filter <pkg>` variants.
- **No deploy surface at all** (library, CLI tool) — the Deploy surfaces table says `none — published via <npm publish / not deployed>`; the proof signal for a release is the registry version bump.
- **Repo already excellent** (delta-agents-class scaffold, only VERIFY.md missing) — generate only VERIFY.md and its `verify.sh` projection, harvesting existing knowledge (CLAUDE.md gotchas, `docs/RUNBOOK.md`, `.claude/test-identities.md`, `scripts/check.sh`) instead of re-deriving it.
- **`.claude/` full of PLAN-\*.md but no CLAUDE.md** (the operatorbase-website state) — the dir existing is not the scaffold existing; proceed normally.
- **Pre-commit hooks time out or need a TTY** — record the known timeout in "Formatter / hooks" so future commits budget for it.

## Pair with

- `~/.claude/scripts/repo-drift-check.sh` — run any time to list repos under `~/dev` missing scaffold pieces; run `/repo-init` inside each flagged repo
- `typecheck-and-build` — the verification mechanics for Step 2
- `schema-snapshot` — generates the schema snapshot the Data layer section points to (Supabase repos)
- `commit-with-heredoc` — committing the scaffold in Step 4
- `/qa-loop` — this skill typically writes 3+ files; run it before claiming done if the user asked for more than the scaffold itself
