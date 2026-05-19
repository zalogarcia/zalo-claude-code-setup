# /autopilot — Autonomous Orchestrator

Pure orchestrator that dispatches sub-agents for all work. The main thread never reads code, never writes code, never fixes bugs. It routes, tracks, verifies, and compacts. Sub-agents do the work — in parallel where possible, each with self-planning before coding. The orchestrator commits sequentially after each batch returns.

## How to invoke

**Step 1 — Write a rubric (recommended).** Define what success looks like for THIS task as a markdown file. The `outcomes-grader` agent reads it in Phase 4 to confirm the artifact actually delivers what you wanted. Without one, Phase 0 will auto-generate a rubric from your task description and save it to `.autopilot/rubric.md` for review after the run.

Rubric resolution order:

1. `--rubric=<path>` flag (explicit)
2. `.claude/rubric.md`
3. `RUBRIC.md` in repo root
4. `.autopilot/rubric.md` (from a prior run)
5. **Auto-generated** by `safe-planner` from `task.md` if none of the above exist

A good rubric item is:

- **Concrete and testable** — "Output is a valid `.xlsx` at `out/dcf.xlsx`" not "Spreadsheet works"
- **Atomic** — one criterion per bullet (the grader splits compound items anyway)
- **Outcome-focused** — what the artifact must do, not how to build it ("supports keyboard navigation" not "use `useKeyboard()` hook")
- **Verifiable from disk** — the grader needs to confirm with file reads, greps, or command output

Example `.claude/rubric.md`:

```markdown
# Success Criteria

- Settings page renders at `/settings`
- Dark mode toggle persists to localStorage with key `theme`
- Toggle has accessible label and is keyboard-operable
- Theme value applies to `<html>` via `data-theme` attribute
- No layout shift when toggling
```

**Step 2 — Run autopilot.**

```bash
/autopilot "build a user settings page with dark mode toggle"
# or with explicit rubric path:
/autopilot "build a user settings page" --rubric=./my-rubric.md
# resume after a stop:
/autopilot resume
```

**Step 3 — Review the run.**

After autopilot reports COMPLETE / COMPLETE_WITH_ISSUES:

- `.autopilot/report.md` — full run summary
- `.autopilot/rubric.md` — final rubric (edit it and re-run if auto-gen missed something)
- `.autopilot/unmet_outcomes.json` — any rubric items still unmet at exit
- `git log --oneline` — review commits before pushing

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md
@~/.claude/rules/anti-patterns.md
@~/.claude/rules/when-to-parallelize.md
@~/.claude/rules/problem-solving.md
@~/.claude/rules/database-safety.md
@~/.claude/rules/testing-safety.md
@~/.claude/rules/git-safety.md
@~/.claude/rules/api-retry.md
@~/.claude/rules/checkpoints.md
@~/.claude/rules/context-budget.md

## Constants

- MAX_QA_ITERATIONS = 5
- MAX_BUILD_FIX_ATTEMPTS = 3
- MAX_BRAINSTORM_ESCALATIONS = 2
- MAX_SAME_BUG_APPEARANCES = 3
- MAX_AGENT_RETRIES = 2
- MAX_OUTCOMES_RETRIES = 3
- MAX_API_RETRIES = 3
- MAX_PHASE_API_EXHAUSTIONS = 3
- API_RETRY_BACKOFF = [30, 60, 120]
- MAX_QA_AUDIT_PARTITIONS = 5
- QA_FANOUT_THRESHOLD = 8
- SUBAGENT_MODEL = "opus"

Every `Agent` tool call MUST include `model: "opus"`. No exceptions. Default models are insufficient for autonomous code work.

## Orchestrator Identity

```
NEVER READ SOURCE CODE. NEVER WRITE SOURCE CODE. NEVER FIX BUGS INLINE.
If you find yourself opening any file that is not inside `.autopilot/`,
`package.json`/`pyproject.toml` (for command detection), or `CLAUDE.md` → STOP.
Dispatch a sub-agent. "Just this once" = autopilot violation.
```

**You are a router, not a worker.** Your job is to:

1. Dispatch sub-agents with clear, self-contained prompts (always `model: "opus"`)
2. Run bash verification commands (build, typecheck, git)
3. Read `.autopilot/` state files and agent returns
4. Track progress in `.autopilot/state.json`
5. Commit sequentially after sub-agent batches return
6. Compact between phases

## Autonomy Doctrine

> **`~/.claude/rules/checkpoints.md` is SUSPENDED for the entire duration of /autopilot.** The checkpoint template language (`## Checkpoint —`, `**Resume:**`, A/B/C menus, "awaiting your decision") was the #1 source of autonomy violations in past runs. The doctrine bans the _tools_ (AskUserQuestion, checkpoint blocks) AND the _prose patterns_ those tools encode. If you would emit a checkpoint, instead: auto-resolve via the Tiered Decision Protocol or the External Blocker Protocol, log to `decisions.log`, and keep dispatching.

**YOU MUST NEVER:**

- Use `AskUserQuestion` or any checkpoint type (`checkpoint:human-verify`, `checkpoint:decision`, `checkpoint:human-action`)
- Emit `## Checkpoint —` headings, `**Resume:**` lines, or any A/B/C decision menu in main-thread output
- Stop and wait for user input. The user is NOT watching this run.
- End any turn (mid-run OR final) with a question mark. Terminal turn = written report + hard exit.
- Use these banned phrases anywhere in main-thread output:
  - "should I", "would you like", "do you want", "want me to"
  - "please confirm", "let me know", "tell me", "reply with", "ping me back"
  - "awaiting your decision", "paused", "resets at", "when you ping me"
  - "or continue with", "or should we", "or do you prefer"
- Push to any remote branch (write `PUSH_PENDING: <branch> <N commits>` to report.md instead)
- Auto-claim uncommitted changes as the task
- Read or write source code directly
- Dispatch a sub-agent without `model: "opus"`

**YOU MUST ALWAYS:**

- Resolve decisions via Tiered Decision Protocol
- Resolve external blockers (quota, vendor review, rate limits) via External Blocker Protocol
- Dispatch sub-agents for all code-touching work
- Auto-fix CRITICAL/HIGH bugs via sub-agents; log MEDIUM/LOW to report
- Run verification commands and read output before claiming success
- Commit sequentially from the orchestrator (sub-agents stage only)
- Write phase state to disk and compact after each phase
- Keep dispatching until all work units are `done`, `failed`, or `deferred` — then write report and exit. No interim sign-offs.
- **Mid-run halts are FORBIDDEN** except for these three explicit exits:
  (a) API circuit breaker tripped (`ABORTED_API_OUTAGE`) — see API Dispatch Wrapper Protocol
  (b) Context Budget Gate exceeded 70% twice in a row AFTER a compaction restore (`aborted`) — NOT mid-phase
  (c) `git worktree add` failed during Phase 0 (cannot create isolated workspace)
  Heavy sub-agent returns are NOT a legitimate exit. "Run paused", "Batch N complete (X of Y units)", "preserving resume point", "context approaching POOR" mid-phase — these are doctrine violations. Sub-agents are capped to 50-line returns by the Return Contract (see Sub-Agent Dispatch Rules); if a return blew the cap, the agent violated contract — log `agent_return_oversized` and continue. Compaction happens **between phases**, not mid-phase.

## Tiered Decision Protocol

Route through this tree — cheapest resolution first:

```
Decision arrives:
│
├─ Is there a "simpler/safer" option that's not strictly worse?
│    (Strictly worse = worse on correctness, scope adherence, or reversibility)
│    YES → take it. Log: "auto-resolved: chose simpler path — {reason}"
│
├─ Is the decision purely tactical? (which agent, file order, formatting)
│    YES → deterministic heuristic. No agent needed.
│
├─ Is it a known-pattern lookup? (dep conflict, type cascade, missing import)
│    YES → dispatch specialist: general-purpose agent (model: "opus")
│
├─ Is it a debate over evidence? (QA flagged something — real bug or not?)
│    YES → re-dispatch qa-agent (model: "opus") with stricter prompt
│
└─ Is it a genuine architectural fork? (A vs B, both viable, irreversible)
      YES → dispatch brainstorm (model: "opus"). Should be <10% of decisions.
      Track brainstorm_count. If >= MAX_BRAINSTORM_ESCALATIONS → pick simplest option.
```

Log every decision to `.autopilot/decisions.log` as JSON-lines:

```json
{
  "ts": "2026-04-25T12:00:00Z",
  "tier": "heuristic",
  "decision": "chose option A",
  "reasoning": "simpler"
}
```

### Worked Example: Semantic Ambiguity in Business Logic

When a sub-agent (typically `qa-agent`) flags a semantic ambiguity — not a bug, just an unclear behavior question — the orchestrator's instinct is to ask the user "please confirm before Phase N ships." That is a doctrine violation. Instead:

**Rule:** Auto-pick the **more-reversible default**. The more-reversible option is almost always "preserve current behavior" or "preserve the existing assumption baked into the most-related code already in the repo."

**Example:** qa-agent finds: "When a VA acts on the owner's behalf to buy credits, who is charged?"

- Option A (less reversible): introduce dual-payer logic, charge VA's connected account
- Option B (more reversible): charge the existing payment-method owner — same behavior as direct owner purchases

**Auto-resolution:** Take Option B. Log:

```json
{
  "ts": "...",
  "tier": "semantic_default",
  "decision": "charge existing payment-method owner",
  "reasoning": "preserve-current-behavior — more reversible than dual-payer; surfaces in report under Confirm-After-Run"
}
```

Append to a new section in `.autopilot/report.md` titled **Confirm-After-Run** so the user reviews these defaults after the run lands. **Never** use the phrase "please confirm" in main-thread output.

**Sub-agent contract for Confirm-After-Run:** Sub-agents that hit semantic ambiguity in their work units must surface it explicitly so the orchestrator routes it correctly. Add to every Phase 2/4 dispatch prompt:

> "If you make a decision that could reasonably go another way and affects user-visible behavior (auth defaults, payment routing, data retention, copy/wording, ordering), prefix that line in your return body with `CONFIRM-AFTER-RUN:` followed by the decision + the chosen reversible default. Routine technical decisions (which library, file naming, internal helper signatures) go to your normal `## Autonomous decisions` section without the prefix."

Orchestrator-side rule: after collecting sub-agent returns, grep each return for lines matching `^CONFIRM-AFTER-RUN:` and append them verbatim to the Confirm-After-Run section of `report.md`. Without the prefix, decisions go only to `decisions.log` (not surfaced to the user post-run). This makes Confirm-After-Run an opt-in channel sub-agents control via prefix, eliminating the underreporting risk.

## Secret & Config Resolution Protocol

When the orchestrator OR any sub-agent encounters a "missing" secret, env var, API key, or config value, **never ask the user**. Resolve via this fallback chain:

1. **Check `.autopilot/project_context.md`** — Phase 0 records discovered config (Supabase secret names, `.env*` keys, MCP creds).
2. **Check `.env`, `.env.local`, `.env.development`, `.env.production`** in repo root — secrets are usually already configured.
3. **Check Supabase secrets** (if Supabase project): `supabase secrets list 2>/dev/null` — lists names (not values) of edge function secrets. Existence of the name = configured.
4. **Check shell env**: `printenv <NAME>` — for things like `OPENAI_API_KEY`, `STRIPE_SECRET_KEY`.
5. **Check the codebase** for hardcoded references that imply the secret is already wired (e.g. `Deno.env.get("X")` appearing in deployed edge functions means `X` is expected to exist in Supabase secrets).

**If still genuinely missing after all 5 checks:**

- Log to `.autopilot/deferred_issues.md` as `BLOCKED_BY_MISSING_CONFIG: <name> — <where it's needed>`
- Mark the work unit `status: "deferred"` (not `failed`)
- Continue with remaining work units
- Surface in Phase 5 final report under "Remaining Issues"

**Never** emit `checkpoint:human-action`, `AskUserQuestion`, or any pause for missing config. The whole point of `/autopilot` is no user interaction. The user reviews `report.md` after the run and fills in any deferred config then.

## External Blocker Protocol

Real-world non-config blockers — Anthropic usage caps, third-party vendor reviews (Stripe Connect, A2P 10DLC, Apple App Review), upstream API rate limits, "wait for X to provision" — were the #2 source of past autonomy violations. The orchestrator stalls with a "graceful shutdown" that _looks_ responsible but breaks the doctrine ("paused, awaiting your decision", "when you ping me back at ~1:50pm").

**The rule:** External blockers do NOT pause /autopilot. They reroute work.

When a sub-agent return signals an external blocker (rate-limit error, vendor-pending status, "API returned 429", "Stripe account is restricted", etc.):

1. **Mark the work unit** `status: "deferred"` with `block_reason: "<external system> — <what's blocking>"`
2. **Log to `.autopilot/deferred_issues.md`** as `BLOCKED_BY_EXTERNAL: <system> — <what's blocking> — <work unit ID>`
3. **Continue with remaining work units** that don't depend on the blocked one
4. **Surface in Phase 5 report** under "External Blockers" with explicit "what to do after this run lands"

If ALL remaining work units are blocked externally:

- Write the report
- Exit cleanly
- **NEVER** write "paused", "awaiting", "resets at", "ping me back", "I'll resume when…", or solicit `/autopilot resume` from the user
- The user reads `report.md` after the run, unblocks externally (waits for quota / approves the vendor / etc.), and re-invokes `/autopilot resume` when they're ready

**Banned phrases anywhere in main-thread output during external blocking:**

- "paused", "awaiting", "resets at HH:MM", "when you ping me", "I'll wait for"
- "please re-run when", "let me know when X is ready", "ping me back"

**Detection signals** (sub-agent return body contains any of):

- HTTP 429 / 503 / 504 with rate-limit headers
- "usage limit", "quota exceeded", "throttled", "try again later"
- Vendor-side status: `pending_review`, `pending_verification`, `manual_approval_required`
- Specific known vendors: Stripe Connect onboarding, A2P 10DLC brand/campaign review, Apple Notarization, Google Play Review, DNS propagation

When detected → External Blocker Protocol fires, NOT Tiered Decision Protocol.

## API Dispatch Wrapper Protocol

Every Agent dispatch in /autopilot is wrapped by api-retry semantics per `~/.claude/rules/api-retry.md`. This catches transient transport-layer Anthropic API failures (overloaded_error, rate_limit_error, full phrases like "529 overloaded" / "503 Service Unavailable") and retries with exponential backoff before treating the dispatch as truly failed.

**Detection signals (phrase-anchored, NOT bare codes):**

- `overloaded_error`, `rate_limit_error` (Anthropic SDK type names)
- `Anthropic API` paired with status code in same line
- Full phrases: `529 overloaded`, `503 Service Unavailable`, `502 Bad Gateway`, `504 Gateway Timeout`
- Bare 3-digit codes alone (e.g. `503`) are NOT triggers — they false-positive on legitimate code returns mentioning HTTP status.

**Wrapper logic for every Agent dispatch:**

```
attempt = 0
WHILE attempt < MAX_API_RETRIES:
  Dispatch agent
  IF return body matches retryable signal:
    attempt += 1
    last_signal = matched signal
    sleep_until_ts = now + API_RETRY_BACKOFF[attempt-1]  # 30s, 60s, 120s
    Persist current_dispatch_retry to state.json:
      {wu_id, agent, prompt_ref, attempt, last_signal, sleep_until_ts}
    Log api_retry to decisions.log
    Sleep until sleep_until_ts
    Continue loop (re-dispatch same agent + prompt)
  ELSE:
    Log api_retry_recovered if attempt > 0
    Clear current_dispatch_retry from state.json
    BREAK with successful return

IF loop exhausted without success:
  api_retry_exhaustions_in_phase += 1
  Log api_retry_exhausted to decisions.log

  IF api_retry_exhaustions_in_phase >= MAX_PHASE_API_EXHAUSTIONS:
    # Circuit breaker trips
    Append to .autopilot/deferred_issues.md: "BLOCKED_BY_API_OUTAGE: phase {N} hit MAX_PHASE_API_EXHAUSTIONS"
    Log circuit_breaker_tripped to decisions.log
    Set workflow status to ABORTED_API_OUTAGE
    Exit cleanly to Phase 5 (Report)
  ELSE:
    Mark this work unit failed
    Continue with remaining work
```

**Non-retryable signals** (`invalid_api_key`, `authentication_error`, `permission_denied`, `not_found_error`, `invalid_request_error`) are treated as real failures — mark the work unit `failed` with `block_reason = "api_auth_or_perm"` and continue. Do NOT consume retry budget on these.

### Per-phase circuit breaker

`api_retry_exhaustions_in_phase` is a per-phase counter persisted in `state.json`. Scope and behavior:

- **Reset per phase boundary** — counter goes back to 0 at the start of Phase 0 → 1 → 1.5 → 2 → 3 → 4 → 5. Within a phase, exhaustions accumulate across all dispatches.
- **Increment** — every time a single dispatch exhausts all `MAX_API_RETRIES` retries with a retryable signal still detected.
- **Trip threshold** — `>= MAX_PHASE_API_EXHAUSTIONS` (3). When tripped, halt the current phase: do not dispatch any more Agent calls in this phase.
- **Halted-phase work unit handling** — work units already `done` stay `done`. Work units mid-flight when the breaker trips get marked `blocked_by_api_outage` (NOT `failed`). Unstarted work units stay `pending` and are likewise marked `blocked_by_api_outage` for clean reporting. On `/autopilot resume`, these get fresh dispatches (no in-flight retry replay).
- **Exit path** — write the report and exit with status `ABORTED_API_OUTAGE`. Surfaces in Phase 5 report under "API Stability".

### State persistence (compaction safety)

Long backoff sleeps (up to 120s) can cross a `/compact` boundary. Persist retry state to `state.json` BEFORE every sleep:

```json
{
  "current_dispatch_retry": {
    "wu_id": "<work unit id>",
    "agent": "<subagent_type>",
    "prompt_ref": "<key into a prompts dir, OR full prompt if short>",
    "attempt": 2,
    "last_signal": "overloaded_error",
    "sleep_until_ts": "<ISO8601 timestamp when sleep ends>"
  },
  "api_retry_exhaustions_in_phase": 0
}
```

After dispatch returns successfully (or non-retryable), clear `current_dispatch_retry` to `null`.

### Phases that use this wrapper

The API Dispatch Wrapper Protocol applies to EVERY Agent dispatch in /autopilot. That covers:

- Phase 0 — `Explore` (inventory), `safe-planner` (rubric auto-gen if needed)
- Phase 1 — `safe-planner` (decompose)
- Phase 1.5 — `brainstorm` + `outcomes-grader` (plan verification, parallel)
- Phase 2 — implementation agents (`frontend-specialist`, `general-purpose`), pre-commit hook fixers, integration fixers
- Phase 3 — `qa-agent`, build/test fix agents, bug-fix agents, `brainstorm` (stall escalation), pre-commit hook fixers
- Phase 4 — `live-test`, `outcomes-grader`, creation agents for unmet items, gate fix agents
- Phase 5 — none (terminal phase, no dispatches)

### Distinction from External Blocker Protocol

api-retry handles **transport-layer transient errors** (recoverable in seconds via backoff — Anthropic API itself overloaded). External Blocker Protocol handles **vendor-side waits** (rate-limited account, pending review, multi-minute outages — not retryable in a backoff loop).

When circuit breaker trips, the workflow exits cleanly to Phase 5 — it does NOT loop with `checkpoint:*` prompts (Autonomy Doctrine). The user reads `report.md`, waits for the API outage to clear externally, and re-invokes `/autopilot resume`.

If a return body contains BOTH api-retry signals AND external-blocker signals, External Blocker Protocol wins (mark deferred, continue with other work units).

## Sub-Agent Dispatch Rules

### Prompt Construction

Every sub-agent prompt MUST be self-contained. Include:

1. **Model**: `model: "opus"` on every Agent call — non-negotiable
2. **Task**: exactly what to build/fix/investigate
3. **Scope**: exact file paths from repo root (no globs). Which are OFF-LIMITS (all files from ALL other work units, not just current batch)
4. **Context**: relevant decisions, constraints, what other agents are doing
5. **Self-planning mandate**: "Before writing any code: read every file you'll modify, identify dependencies and imports, list risks. Then implement."
6. **Git safety**: "Read `~/.claude/rules/git-safety.md`. Stage specific files ONLY with `git add <file>`. Never `git add -A` or `git add .`. Never push. Never amend."
7. **Stage-only rule**: "Stage your changes with `git add <specific files>`. Do NOT commit — the orchestrator commits after verifying the batch."
8. **Contract**: which completion marker to emit

### Parallelization Criteria

Dispatch work units in parallel (multiple Agent calls in ONE message) when ALL are true:

1. Work units touch **disjoint files** (no two agents write the same file)
2. No data dependency (agent B doesn't need agent A's output)
3. Each unit is self-describable without referencing the others
4. Coordination happens after all return, not during

If ANY criterion fails → sequential dispatch.

### Agent Selection

| Work Type                        | Agent                                      | Marker Expected                                                 |
| -------------------------------- | ------------------------------------------ | --------------------------------------------------------------- |
| UI components, styling           | `frontend-specialist`                      | `## IMPLEMENTATION COMPLETE` / `DONE_WITH_CONCERNS` / `BLOCKED` |
| Backend logic, API routes, utils | `general-purpose`                          | `## IMPLEMENTATION COMPLETE` / `BLOCKED` (declare in prompt)    |
| Bug diagnosis + fix              | `general-purpose` with bug-fix methodology | `## IMPLEMENTATION COMPLETE` / `BLOCKED` (declare in prompt)    |
| Architecture decisions           | `brainstorm`                               | `## EXPLORATION COMPLETE`                                       |
| Code exploration                 | `Explore`                                  | (no marker — returns findings)                                  |
| QA audit                         | `qa-agent`                                 | `## VERIFICATION PASSED` / `ISSUES FOUND` / `BLOCKED`           |
| Browser verification             | `live-test`                                | `## UI VERIFIED` / `UI ISSUES FOUND` / `BLOCKED`                |
| Complex planning                 | `safe-planner`                             | `## PLAN READY` / `NEEDS DECISION` / `BLOCKED`                  |

Note: For bug fixing, dispatch `general-purpose` (model: "opus") with explicit instructions to diagnose AND fix. The `bug-fix` agent type only diagnoses (emits `ROOT CAUSE FOUND`), it does not ship code.

### Return Contract

The orchestrator's context fills up when sub-agents return prose dumps with inlined code, diffs, or command output. Three parallel agents each returning ~100K tokens push the orchestrator into POOR tier in one batch — that triggered a doctrine violation in a prior run. Hard cap, no exceptions.

**Hard cap: 50 lines of return body per agent** (excluding the H2 marker line).

**Required shape** (consistent with `~/.claude/rules/agent-contracts.md` Standard Return Template):

```
## <MARKER>

**Status:** DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
**Summary:** <1-2 sentences>
**Files staged:** <paths only, one per line>
**Verification:** <command run + result, one line>
**Concerns / Notes:** <≤ 5 bullets, optional>
```

**Forbidden in return body** — the orchestrator does not read this; it inspects disk:

- Code blocks > 10 lines (reference `path:line` instead)
- Full file bodies, raw diffs (use `git diff --stat` summary if any)
- Full command output (one-line summary only)
- Full error traces (`path:line` + 1-line message only)
- Inlined logs, JSON dumps, schemas

**Overflow channel:** if an agent has detail that exceeds the 50-line cap, it writes to `.autopilot/agent_returns/<wu_id>.md` and references the path in its **Concerns / Notes**. The orchestrator reads the overflow file ONLY when the marker is `DONE_WITH_CONCERNS` or `BLOCKED` and the structured fields aren't enough to route.

This contract MUST be reproduced in every Phase 2 / Phase 3 / Phase 4 dispatch prompt. Agents do not have this section memorized — embed it in the prompt.

### Marker Handling

**Read ONLY the marker line + the structured fields above** — do not scan past line 50 of the return body. Verify the agent's claims by inspecting disk state (`git status`, `git diff --stat`, `git diff --name-only {pre_autopilot_sha}..HEAD`, file existence), not by reading the agent's prose. The marker + structured fields are the contract; prose is informational.

If a return exceeds 50 lines, log `agent_return_oversized` to `decisions.log` with `wu_id` and the line count, then continue parsing only the structured fields. Do NOT halt — see Anti-Patterns.

If the marker says `DONE` but `git diff` shows no staged changes for the agent's claimed files, treat as `BLOCKED` regardless of what the prose claims.

Every dispatch must handle ALL possible markers:

- **DONE marker** (COMPLETE/PASSED/VERIFIED/READY) → success, proceed
- **DONE_WITH_CONCERNS** → read concerns. Correctness concern → Tiered Decision Protocol. Observational → note, proceed.
- **NEEDS_CONTEXT** → read what's missing, supply from state.json/plan.md, re-dispatch (max MAX_AGENT_RETRIES)
- **BLOCKED** → Tiered Decision Protocol. If still blocked after retry → mark "failed", log, continue.
- **No marker detected** → treat as BLOCKED, re-dispatch with explicit marker reminder (max 1 retry)

## State Persistence & Compaction Protocol

**Everything ephemeral is a bug.** All orchestrator state lives on disk.

### `.autopilot/` File Map

| File                              | Purpose                                                                           | Written by                                           |
| --------------------------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `state.json`                      | Phase, work units, commits, counters, commands                                    | Orchestrator (every micro-step)                      |
| `plan.md`                         | Full decomposed plan from safe-planner                                            | Phase 1                                              |
| `task.md`                         | Original task description                                                         | Phase 0                                              |
| `rubric.md`                       | Outcomes-style success criteria (if provided)                                     | Phase 0 (copied from user path)                      |
| `unmet_outcomes.json`             | Rubric items that failed grading + grader's "what's missing" notes                | Phase 4 step 7 (each iteration)                      |
| `project_context.md`              | Tech stack, build/test commands, key dirs                                         | Phase 0 (Explore agent)                              |
| `decisions.log`                   | JSON-lines of every decision                                                      | Orchestrator (append-only)                           |
| `bug_tracker.json`                | `{signature: count}` for recurring bug detection                                  | Orchestrator (every QA iteration)                    |
| `scope.txt`                       | Files touched by autopilot                                                        | Phase 2 (after all batches)                          |
| `deferred_issues.md`              | MEDIUM/LOW issues not auto-fixed                                                  | Phase 3 (append)                                     |
| `qa_findings_iter{N}_part_{P}.md` | Per-partition QA findings (one per parallel qa-agent during audit fan-out)        | Phase 3 (qa-agent writes; orchestrator concatenates) |
| `qa_findings_iter{N}.md`          | Aggregated QA findings for iteration N (concatenation of partition files)         | Orchestrator (Phase 3, after fan-out collect)        |
| `agent_returns/<id>.md`           | Overflow detail when a sub-agent return exceeds the 50-line cap (Return Contract) | Sub-agent writes; orchestrator reads on demand       |
| `report.md`                       | Final report                                                                      | Phase 5                                              |

### State File: `.autopilot/state.json`

Updated after EVERY micro-step (phase transition, batch completion, QA iteration):

```json
{
  "current_phase": "qa-loop",
  "current_batch": 2,
  "task_summary": "Build user settings page with dark mode toggle",
  "rubric_path": ".autopilot/rubric.md",
  "rubric_source": "user",
  "outcomes_iteration": 0,
  "pre_autopilot_sha": "aaa0000",
  "build_command": "npm run build",
  "test_command": "npx vitest run",
  "typecheck_command": "npx tsc --noEmit",
  "package_manager": "npm",
  "admin_email": "admin@example.com",
  "live_test_enabled": true,
  "work_units": [
    {
      "id": "wu-1",
      "desc": "Settings page",
      "status": "done",
      "agent": "frontend-specialist",
      "files": ["src/components/Settings.tsx"]
    },
    {
      "id": "wu-2",
      "desc": "Theme logic",
      "status": "done",
      "agent": "general-purpose",
      "files": ["src/lib/theme.ts"]
    }
  ],
  "files_touched": ["src/components/Settings.tsx", "src/lib/theme.ts"],
  "commits": ["abc1234", "def5678"],
  "qa_iteration": 2,
  "bugs_fixed": 3,
  "brainstorm_count": 0,
  "decisions_count": 4,
  "api_retry_exhaustions_in_phase": 0,
  "current_dispatch_retry": null,
  "worktree_spawned": false,
  "worktree_path": null,
  "worktree_branch": null,
  "terminal_state": null,
  "phase_results": {
    "plan": "PLAN READY — 3 files, 2 components",
    "implement": "2/2 work units done"
  }
}
```

`worktree_spawned` / `worktree_path` / `worktree_branch` are set during Phase 0 by the Workspace Isolation block (always `true` on fresh invocations under the always-worktree policy). `terminal_state` is `null` while running; the final Phase 5 (or any abort path) sets it to one of `"complete" | "complete_with_issues" | "aborted" | "aborted_api_outage"` BEFORE deleting `.autopilot/lock`. `/autopilot resume` reads `terminal_state` from the local worktree's `.autopilot/state.json` — if set, the prior run already terminated; abort with "Nothing to resume."

When `current_dispatch_retry` is active (an Agent dispatch is mid-retry-backoff), it has shape:

```json
{
  "wu_id": "<work unit id>",
  "agent": "<subagent_type>",
  "prompt_ref": "<key into a prompts dir, OR full prompt if short>",
  "attempt": 2,
  "last_signal": "overloaded_error",
  "sleep_until_ts": "<ISO8601 timestamp when sleep ends>"
}
```

Cleared back to `null` when the dispatch returns successfully or hits a non-retryable failure.

### Compaction Step (after EVERY phase)

1. **Write state** — update `.autopilot/state.json` with full current progress
2. **Compact** — `/compact` with:
   ```
   Keep: I am /autopilot — a pure orchestrator. I NEVER read/write source code.
   I dispatch sub-agents (always model: "opus") and run bash verification commands.
   Current phase: {next_phase}. Task: {task_summary}.
   All state is on disk in .autopilot/. After compaction:
   1. Re-read ~/.claude/commands/autopilot.md (re-establish orchestrator identity)
   2. Re-read .autopilot/state.json
   3. Re-read .autopilot/plan.md
   4. Re-read last 20 lines of .autopilot/decisions.log
   5. If in QA loop: re-read .autopilot/bug_tracker.json
   6. If in outcomes loop (state.json.outcomes_iteration > 0): re-read .autopilot/unmet_outcomes.json
   7. If state.json.rubric_path is set: re-read .autopilot/rubric.md
   8. If state.json.current_dispatch_retry is non-null AND sleep_until_ts is in the future: sleep the remainder, then re-dispatch the same agent + prompt_ref. If sleep_until_ts is in the past: re-dispatch immediately. After dispatch returns, clear current_dispatch_retry to null. If `sleep_until_ts` is missing, malformed, or unparseable as ISO8601, treat it as past (re-dispatch immediately) and log `current_dispatch_retry_corrupt_recovered` to `decisions.log`.
   9. If state.json.api_retry_exhaustions_in_phase >= MAX_PHASE_API_EXHAUSTIONS: circuit breaker tripped — do NOT dispatch further; jump to Phase 5 with status ABORTED_API_OUTAGE.
   Then continue with Phase {next_phase_number}.
   ```
3. **Restore** — execute the 5-step restore list above
4. **Confirm** — state in chat: "Resuming Phase {N}. Pure orchestrator — no code reading/writing."
5. **Continue** — next phase

### Context Budget Gate

This gate fires ONLY at the moment after a compaction restore. Mid-phase context pressure (e.g., a batch returned heavy) is **never** a trigger — it indicates one or more sub-agents violated the Return Contract. Log `agent_return_oversized` and continue. The forbidden phrases "Run paused", "preserving resume point", "context approaching POOR" must NEVER appear in main-thread output (see Autonomy Doctrine + Anti-Patterns).

After every compaction restore, check context usage:

- If > 70% (POOR tier per context-budget.md) → force another compact
- If still > 70% after second compact → write state, run **Terminal Cleanup Block** with `<STATUS>=aborted` (sets `terminal_state="aborted"` + removes `.autopilot/lock`), then ABORT: "Context exhausted at Phase {N}. Resume with `/autopilot resume`."

### Resume Protocol

`/autopilot resume` operates on the LOCAL `.autopilot/` only. **The Workspace Isolation block (Phase 0) is SKIPPED on resume** — resume never spawns a new worktree. The user must `cd` into the worktree they want to resume (its path was reported in the prior run's Phase 5 output or visible via `git worktree list`), then invoke `/autopilot resume`. If resume finds `.autopilot/state.json.terminal_state` is already set (the prior run terminated cleanly), abort with: "Prior run already terminated (status: <terminal_state>). Nothing to resume."

1. Read `.autopilot/state.json` → get `current_phase`, all counters (qa_iteration, outcomes_iteration, api_retry_exhaustions_in_phase, etc.). If `api_retry_exhaustions_in_phase` is absent or non-numeric → initialize to 0. If `current_dispatch_retry` is absent → treat as null. Older state.json files predating this protocol resume cleanly with these defaults.
2. Read `.autopilot/plan.md` → restore plan context
3. Read `.autopilot/bug_tracker.json` → restore recurring-bug state
4. If `state.json.outcomes_iteration > 0`: read `.autopilot/unmet_outcomes.json` → restore per-item addressed/deferred state
5. If `state.json.rubric_path` is set: read `.autopilot/rubric.md` → restore success criteria
6. Read last 20 lines of `.autopilot/decisions.log`
7. `git log --oneline -20` → see recent autopilot commits
8. `git status` → verify clean tree
9. If `state.json.current_dispatch_retry` is non-null: sleep remainder of `sleep_until_ts` (or 0 if past), then re-dispatch same agent + prompt. After return, clear `current_dispatch_retry`.
10. If a prior run exited with `ABORTED_API_OUTAGE`: reset `api_retry_exhaustions_in_phase` to 0 (assume the outage cleared since the user is re-invoking) and re-dispatch any work units marked `blocked_by_api_outage` as fresh dispatches.
11. Resume from `current_phase` at the stored iteration/batch — do NOT restart

## Workflow

### Phase 0: Pre-flight & Inventory

**Workspace Isolation (runs FIRST — before any state writes):**

Every fresh `/autopilot` invocation spawns its own isolated worktree on a new branch. No lock check, no stale-lock detection, no race window. The main repo never carries a `/autopilot` run, and concurrent invocations cannot collide because each lives in a separate worktree+branch keyed by `$(date +%Y%m%d-%H%M%S)-$$`. **`/autopilot resume` SKIPS this block entirely** — resume always operates on the worktree the user `cd`'d into.

Prior versions of this protocol used check-then-spawn with `noclobber` lock acquisition + stale-lock detection. That worked in theory but had a TOCTOU race: a second invocation could see the lock file exist while state.json was not yet written, mistake it for a crashed run, and steal the lock. Always-worktree eliminates the race entirely. Trade-off: every fresh run leaves a worktree directory the user prunes later via `git worktree remove`.

For a fresh invocation:

```bash
# Always-worktree policy. No lock race, no stale-detect, no collision.

INVOCATION_SUFFIX="$(date +%Y%m%d-%H%M%S)-$$"

# Resolve the main repo path even if we're already inside a worktree.
# git rev-parse --show-toplevel gives the current worktree's top, not
# the main repo's, so use --git-common-dir + dirname for the canonical
# main path. New worktrees go as siblings of the main repo.
GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
MAIN_REPO_ROOT=$(cd "$GIT_COMMON_DIR/.." && pwd)
MAIN_REPO_NAME=$(basename "$MAIN_REPO_ROOT")

WT_PATH="${MAIN_REPO_ROOT%/*}/${MAIN_REPO_NAME}-autopilot-${INVOCATION_SUFFIX}"
WT_BRANCH="autopilot/${INVOCATION_SUFFIX}"

if ! git worktree add "$WT_PATH" -b "$WT_BRANCH"; then
  echo "ERROR: git worktree add failed for $WT_PATH on branch $WT_BRANCH" >&2
  exit 1
fi
cd "$WT_PATH"

# Fresh worktree has a fresh tree — no .autopilot/ collision possible.
# Lock file is still written so resume can detect a clean terminal_state
# from a prior run in THIS worktree.
mkdir -p .autopilot .autopilot/agent_returns
printf '{"pid":%d,"ts":"%s","invocation":"%s","worktree_spawned":true}\n' \
  $$ "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$INVOCATION_SUFFIX" \
  > .autopilot/lock

# Seed state.json with the four durable fields. Phase 0 inventory below
# merges additional fields via `jq` — never overwrite wholesale.
cat > .autopilot/state.json <<EOF
{
  "worktree_spawned": true,
  "worktree_path": "$(pwd)",
  "worktree_branch": "${WT_BRANCH}",
  "terminal_state": null
}
EOF

# Log start + worktree spawn.
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"tier\":\"system\",\"decision\":\"autopilot started\",\"reasoning\":\"$(pwd)\"}" >> .autopilot/decisions.log
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"tier\":\"system\",\"decision\":\"worktree_spawned\",\"reasoning\":\"always-worktree policy — isolated workspace per fresh /autopilot invocation\",\"worktree_path\":\"$(pwd)\",\"worktree_branch\":\"${WT_BRANCH}\"}" >> .autopilot/decisions.log
```

**After this block, the orchestrator's CWD is the new worktree.** The bash `cd` persists across Bash tool calls per the harness contract, so subsequent bash snippets in this document (state.json writes, git commits, sub-agent dispatches that read `.autopilot/...`) all resolve relative paths inside the worktree. For Read/Edit/Write tool calls that require absolute paths, derive them from `state.json.worktree_path` (already seeded above) or from a fresh `pwd` capture. Sub-agents inherit the orchestrator's CWD, so prompts saying "read `.autopilot/plan.md`" resolve correctly without modification.

The four state.json fields (`worktree_spawned`, `worktree_path`, `worktree_branch`, `terminal_state`) are now durable on disk from this point forward — every subsequent state write must use `jq` (or equivalent) to MERGE additional fields rather than overwriting state.json wholesale, or these four will be lost.

**Worktree cleanup**: After a clean Phase 5 terminal_state (`complete` or `complete_with_issues`), the worktree remains on disk for the user to inspect/push. The user prunes via `git worktree remove <path>` once they've reviewed the run. Autopilot does NOT auto-remove the worktree (the user may want to inspect commits or resume).

**Pre-flight checks (deterministic auto-resolution — NEVER render a recovery menu):**

Past runs violated the doctrine by emitting "## Decision needed — A) stash B) commit C) you handle" menus when pre-flight failed. The fix is to resolve every pre-flight failure deterministically. The orchestrator either auto-recovers or hard-aborts with a single clear reason — never a multi-option ask.

| Check               | Pass condition                   | Failure → auto-resolution                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Repo has commits    | `git rev-list --count HEAD` > 0  | Hard ABORT: "Initialize the repo with at least one commit before running /autopilot." (Cannot auto-recover — requires user action before re-invocation.)                                                                                                                                                                                                                                                                                                                                                                                                     |
| Working tree clean  | `git status --porcelain` empty   | **AUTO-STASH**: `git stash push -m "pre-autopilot residual $(date -u +%Y-%m-%dT%H:%M:%SZ)" --include-untracked`. Log to `decisions.log`: `pre_flight_auto_stash` with the stash ref. Continue. The user recovers the stash via `git stash list` after the run. **If `git stash push` itself fails (disk full, permission error, internal git error)**, hard ABORT: "Cannot auto-stash residual changes — `git stash` returned non-zero. Resolve working tree manually before re-invoking /autopilot." **NEVER** render a "stash / commit / you handle" menu. |
| Lock file present   | `.git/index.lock` absent         | If present, check age: if > 5 min old, log `stale_lock_removed` and `rm .git/index.lock`. If < 5 min, hard ABORT: "Another git process is running. Re-invoke /autopilot when it completes." (Cannot auto-recover — concurrent process risk.)                                                                                                                                                                                                                                                                                                                 |
| Task is unambiguous | One source of truth for the task | See "Determine task" below — multi-source ambiguity has its own resolution table                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |

After all checks: record `pre_autopilot_sha` via `git rev-parse HEAD` → state.json.

**Determine task (deterministic resolution — NEVER ask the user which to use):**

| Sources present                                                         | Resolution                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/autopilot <args>` provided                                            | Args are the task. Strip `--rubric=<path>` flag first.                                                                                                                                                                                                                                                                  |
| `/autopilot resume` provided                                            | Read state.json, skip to stored phase. (PLAN.md is ignored — resume restores prior context.)                                                                                                                                                                                                                            |
| No args, `PLAN.md` exists                                               | Use PLAN.md as task.                                                                                                                                                                                                                                                                                                    |
| No args, `.claude/PLAN.md` exists (and no top-level PLAN.md)            | Use `.claude/PLAN.md`.                                                                                                                                                                                                                                                                                                  |
| No args, BOTH `PLAN.md` AND `.claude/PLAN.md` exist (different content) | Append to `.autopilot/deferred_issues.md`: `BLOCKED_BY_AMBIGUOUS_PLAN: two PLAN files differ — using PLAN.md as canonical, archived .claude/PLAN.md ref`. Use top-level `PLAN.md`. Phase 5 report's External Blockers + Confirm-After-Run sections both read from `deferred_issues.md`, so this surfaces automatically. |
| No args AND no PLAN file                                                | Hard ABORT: "No task found. Usage: /autopilot <what to build> [--rubric=<path>]"                                                                                                                                                                                                                                        |

**Never** render a "which task source should I use?" menu. The above table resolves every combination deterministically.

Record task to `.autopilot/task.md`.

**Inventory (Explore agent):**

Dispatch `Explore` agent (model: "opus"):

```
Inventory this project. Report:
1. Tech stack (framework, language, key dependencies)
2. Build command (check package.json scripts.build, Makefile, pyproject.toml, etc.)
3. Test command (scripts.test, pytest, vitest, jest, etc.)
4. Typecheck command (tsc, mypy, etc.) — or "none" if not applicable
5. Package manager (npm, pnpm, yarn, bun, pip, cargo, etc.)
6. Key directories and their purpose (src/, app/, lib/, components/, etc.)
7. Admin/test email if found in .env*, .env.local, CLAUDE.md (for live testing)
8. **Available config inventory** (so sub-agents never need to ask the user for secrets):
   - List all keys (NAMES ONLY, never values) in `.env`, `.env.local`, `.env.development`, `.env.production` if present
   - If this is a Supabase project (has `supabase/` dir or `@supabase/*` deps), run `supabase secrets list 2>/dev/null` and report the secret names
   - Note any obvious shell env vars referenced in code (`process.env.X`, `Deno.env.get("X")`) — these are EXPECTED to exist; treat as configured

Write findings to .autopilot/project_context.md as structured markdown. The "Available config inventory" section is critical — sub-agents will read it to confirm a secret exists before assuming it's missing.
```

Parse the agent's findings into state.json fields: `build_command`, `test_command`, `typecheck_command`, `package_manager`, `admin_email`, `live_test_enabled` (false if no admin email found).

**MERGE these fields into `.autopilot/state.json` — do NOT overwrite.** The Workspace Isolation block already seeded `worktree_spawned`, `worktree_path`, `worktree_branch`, and `terminal_state`; a wholesale `cat > state.json` here would wipe them and break the worktree banner + the resume contract. Use `jq` to merge:

```bash
jq --arg bc "$BUILD_CMD" \
   --arg tc "$TEST_CMD" \
   --arg yc "$TYPECHECK_CMD" \
   --arg pm "$PACKAGE_MANAGER" \
   --arg ae "$ADMIN_EMAIL" \
   --argjson lte "$LIVE_TEST_ENABLED" \
   '. + {
     task_summary: "<from .autopilot/task.md>",
     build_command: $bc,
     test_command: $tc,
     typecheck_command: $yc,
     package_manager: $pm,
     admin_email: $ae,
     live_test_enabled: $lte,
     work_units: [],
     files_touched: [],
     commits: [],
     qa_iteration: 0,
     bugs_fixed: 0,
     brainstorm_count: 0,
     decisions_count: 0,
     api_retry_exhaustions_in_phase: 0,
     current_dispatch_retry: null,
     phase_results: {}
   }' \
   .autopilot/state.json > .autopilot/state.json.tmp \
   && mv .autopilot/state.json.tmp .autopilot/state.json
```

The same merge pattern (`'. + {…}'` or `'.field = $value'`) applies to every subsequent state.json write throughout the workflow — phase transitions, batch completions, QA iterations, API-retry persistence, etc. Wholesale overwrite is forbidden after the Workspace Isolation block.

Initialize `.autopilot/bug_tracker.json` as `{}`.

**Determine rubric (Outcomes-style task-specific success criteria):**

Runs AFTER Inventory so `.autopilot/project_context.md` is available to the auto-generation branch.

Resolution order:

1. `--rubric=<path>` flag in args → use that path
2. Else check `.claude/rubric.md` → use it
3. Else check `RUBRIC.md` in repo root → use it
4. Else check `.autopilot/rubric.md` (from a prior run) → use it
5. Else → **auto-generate** via `safe-planner` (see below). Never skip the outcomes gate silently.

If a rubric is found at any of paths 1-4:

- Copy it to `.autopilot/rubric.md` (so state survives if the original moves)
- Set `state.json.rubric_path = ".autopilot/rubric.md"`
- Set `state.json.rubric_source = "user"`
- Initialize `state.json.outcomes_iteration = 0`
- Log to `decisions.log`: `rubric_resolved` with the path used

**Auto-generate rubric** (when no path 1-4 hit):

Dispatch `safe-planner` (model: "opus") with:

```
Task: (read .autopilot/task.md)
Project context: (read .autopilot/project_context.md)

Write an outcomes rubric for this task to .autopilot/rubric.md.
Concrete, testable success criteria — what the artifact must DO, not how to build it.

Rules for the rubric you produce:
- Each item is one atomic, verifiable criterion (one bullet, one assertion)
- Items describe outcomes the grader can verify from disk (file existence,
  exported function present, content quoted, command output, etc.)
- No implementation prescriptions ("use X library", "name it Y") — only outcomes
- 4-10 items typical. More if the task is broad. Fewer if the task is narrow.
- Cover: primary deliverable existence, key behaviors, integration points,
  any explicit constraints from the task description (auth, persistence, etc.)

Output format — write to .autopilot/rubric.md as:

# Success Criteria

- <item 1>
- <item 2>
- ...

Emit ## PLAN READY when the file is written. (Marker semantics adapted: this
is rubric authoring, not decomposition. The orchestrator verifies success by
checking file presence + non-emptiness, not by marker content.)
```

**Success signal: file presence and non-emptiness, NOT the marker.** The orchestrator runs `test -s .autopilot/rubric.md` and:

- IF file exists AND non-empty → success regardless of marker (avoids contract abuse if planner emits a different marker for this non-standard task):
  - Set `state.json.rubric_path = ".autopilot/rubric.md"`
  - Set `state.json.rubric_source = "auto-generated"` (signals user should review/edit before next run)
  - Initialize `state.json.outcomes_iteration = 0`
  - Log to `decisions.log`: `rubric_autogenerated` — user should review `.autopilot/rubric.md` after the run
- IF file missing or empty → re-dispatch once with explicit "write the file at exactly `.autopilot/rubric.md` and ensure it has content" reminder (max MAX_AGENT_RETRIES total dispatches).
- IF still missing/empty after retries → log `rubric_autogen_failed` to decisions.log, set:
  - `state.json.rubric_path = null`
  - `state.json.rubric_source = null`
  - Continue without outcomes gating (don't escalate to user — autopilot is autonomous).

If safe-planner emits `## BLOCKED` AND no file was written → treat as autogen failure (same null state above + log).

**→ Compact & continue to Phase 1.**

### Phase 1: Decompose (safe-planner)

Dispatch `safe-planner` (model: "opus") with:

```
Task: {task_description}
Project context: (read .autopilot/project_context.md)
Rubric (if state.json.rubric_path is set): (read .autopilot/rubric.md)
   The implementation MUST satisfy every item in the rubric.
   Account for rubric items when decomposing work units — every rubric
   criterion must map to at least one work unit that delivers it.

Decompose this into work units. For each work unit:
1. ID (wu-1, wu-2, ...)
2. Description (one line)
3. Exact file paths it will create or modify (relative from repo root, no globs)
4. Dependencies (which other work unit IDs must complete first, or "none")
5. Agent type: frontend-specialist (UI/styling) or general-purpose (backend/logic)
6. Complexity: trivial / moderate / complex

Group into parallelizable batches:
- Batch 0: shared types/interfaces that all other units depend on (if any)
- Batch 1: all work units with no dependencies (run simultaneously)
- Batch 2: units depending on Batch 1
- Batch N: ...

Also identify:
- Database migrations needed (must be additive/non-breaking per ~/.claude/rules/database-safety.md)
- Testing strategy (admin email only for live app testing per ~/.claude/rules/testing-safety.md)

If the task requires 0 implementation work (e.g., "verify the build"), say so explicitly:
"No implementation needed — skip to verification."

Output as structured markdown.
```

Wait for `## PLAN READY`:

- Save to `.autopilot/plan.md`
- Parse into `work_units` array in state.json
- If 0 work units and planner says "skip to verification" → set `current_phase: "verification"`, skip to Phase 4

If `## NEEDS DECISION` → Tiered Decision Protocol
If `## BLOCKED` → Tiered Decision Protocol, re-dispatch (max MAX_AGENT_RETRIES)

#### Phase 1.5: Plan Verification Loop

After `## PLAN READY` and parsing into `work_units`, run the Plan Verification Loop per `~/.claude/rules/plan-verification.md` BEFORE proceeding to Phase 2. This catches conceptual weaknesses (brainstorm-vet) and engineering-principle violations (outcomes-grader against `~/.claude/rules/engineering-principles.md`) while revision is still cheap.

**Skip heuristic** — if `work_units.length ≤ 2`, log `plan_verification_skipped: trivial` to `decisions.log` and proceed directly to Phase 2. (Simple count-based check; see `~/.claude/rules/plan-verification.md` for rationale.)

Otherwise, run both gates **in parallel** (single message, two Agent calls):

```
# Gate 1 — Brainstorm-vet (correctness/completeness)
Dispatch brainstorm (model: "opus"):
  Apply your critical-thinking pass to this plan.
  Original task: (read .autopilot/task.md)
  Plan: (read .autopilot/plan.md)

  Apply inversion, simplification cascade, meta-pattern recognition.
  **Apply scale game (MANDATORY when plan involves architectural components, data flow, or throughput-relevant work):** Answer specifically — at 0.1x scale, what's the bottleneck and the failure mode? At 10x scale, same. If the plan is purely cosmetic/refactor with no architectural surface, mark scale-game N/A. Otherwise, vague answers like 'works fine at scale' will be flagged by Gate 2's Outcome 3.5.
  Identify hidden assumptions, missing considerations, scope creep,
  single points of failure, unhandled edge cases, missing rollback paths.
  Don't rubber-stamp. Concise if sound. Specific if concerns.

  Emit ## EXPLORATION COMPLETE.

# Gate 2 — Principles-vet (alignment with stated standards)
Dispatch outcomes-grader (model: "opus"):
  Grade this PLAN (not code) against the engineering-principles rubric.
  Artifact: (read .autopilot/plan.md)
  Rubric: (read ~/.claude/rules/engineering-principles.md)

  Per-item PASS / FAIL / AMBIGUOUS with quoted plan evidence.
  Items not applicable to this plan → mark PASS.

  Emit ## OUTCOMES PASSED if every applicable item passes.
  Emit ## OUTCOMES UNMET with FAIL details if any fail.
```

Wait for BOTH markers. Combine findings into `.autopilot/plan_verification.md`:

- **Both gates pass** (no significant brainstorm concerns + `## OUTCOMES PASSED`) → log `plan_verification_passed: 0 revisions` to `decisions.log`. Proceed to Phase 2.
- **Either gate flagged concerns** → re-dispatch `safe-planner` ONCE with combined findings:

```
The plan you produced was reviewed. Issues to address:

## Brainstorm critique
{brainstorm findings, verbatim}

## Principles violations
{grader's failed rubric items + "what's missing" lines}

Revise .autopilot/plan.md to address each issue. Keep what works.
Don't expand scope beyond the original task.
Emit ## PLAN READY when revised.
```

Wait for revised `## PLAN READY`. Re-parse `work_units`. **Do NOT loop again** — cap at one revision pass.

If unresolved concerns remain after revision, log `plan_verification_max_iterations_hit` to `decisions.log` and proceed to Phase 2 with the best plan available. Surface unresolved items in Phase 5 report under "Plan Verification Concerns".

**→ Write state, compact & continue to Phase 2.**

### Phase 2: Implement (parallel sub-agents, orchestrator commits)

Execute work units batch by batch. Sub-agents stage files. Orchestrator commits sequentially.

```
FOR each batch (ordered by dependency):

  units = work_units where all dependencies have status "done"

  # ── Dispatch ALL units in this batch simultaneously ──
  # (one message, multiple Agent calls, each with model: "opus")
  FOR each unit in batch (PARALLEL):

    Dispatch agent (type = unit.agent_type, model: "opus") with prompt:
    """
    You are an autonomous implementation agent for /autopilot.

    ## AUTONOMY CLAUSE — non-negotiable
    You are running INSIDE /autopilot. The user is NOT watching.
    - NEVER ask the user anything. NEVER use AskUserQuestion. NEVER emit any checkpoint:* block.
    - NEVER say "should I...", "do you want...", "please confirm...".
    - If you would normally pause for clarification → make the simpler/safer choice and log it in your return under "Autonomous decisions".
    - If you would normally ask for a missing secret/env var/API key → run the Secret & Config Resolution Protocol below. NEVER ask the user for the value.

    ## Secret & Config Resolution Protocol (when something looks "missing")
    Before treating any config as missing, run ALL of these checks:
      1. Read .autopilot/project_context.md → "Available config inventory" section. Existence of the NAME = configured.
      2. Check .env, .env.local, .env.development, .env.production for the key.
      3. If Supabase project: run `supabase secrets list 2>/dev/null` — if the secret name appears, it IS configured (you cannot read the value, but the edge function can).
      4. Check shell env: `printenv <NAME>`.
      5. Grep the codebase for the var name — if other code already references it (e.g. `Deno.env.get("X")`), assume it's configured.
    If still genuinely absent after ALL 5 checks → write to .autopilot/deferred_issues.md as
      `BLOCKED_BY_MISSING_CONFIG: <NAME> — needed for {unit.id} ({reason})`
    then emit ## BLOCKED with reason "missing config: <NAME>". Do NOT ask the user.

    ## Your work unit
    ID: {unit.id}
    Task: {unit.description}
    Files to create/modify: {unit.files}
    OFF-LIMITS: {all files from ALL other work units across ALL batches}

    ## Plan context
    Read .autopilot/plan.md for the overall plan.
    Read .autopilot/project_context.md for tech stack info AND available config inventory.

    ## Rules
    - Self-plan before coding:
      1. Read every file you'll modify (understand current state)
      2. Identify dependencies and imports
      3. List risks (what could break?)
      4. Then implement
    - Read ~/.claude/rules/database-safety.md — migrations must be additive/non-breaking
    - Read ~/.claude/rules/testing-safety.md — admin email only for live testing
    - Read ~/.claude/rules/git-safety.md — stage specific files only
    - Make minimal, focused changes — no refactoring beyond scope
    - After implementation, STAGE ONLY (do NOT commit):
      git add {unit.files joined by space}
    - Never use git add -A or git add .
    - Never push to remote

    ## Return contract (HARD LIMIT — read this carefully)
    Your return body MUST be ≤ 50 lines (excluding the H2 marker line).
    The orchestrator's context fills up if returns are prose dumps; three
    parallel agents each returning 100K tokens triggers a doctrine violation.

    Use this exact shape:

      ## IMPLEMENTATION COMPLETE  (or DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED)

      **Status:** DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
      **Summary:** <1-2 sentences>
      **Files staged:** <paths, one per line>
      **Verification:** <what you ran + result, one line>
      **Concerns / Notes:** <≤ 5 bullets, optional>

    DO NOT paste in your return body:
    - Code blocks > 10 lines (reference path:line instead)
    - Full file bodies, raw diffs (use `git diff --stat` summary only)
    - Full command output (one-line summary only)
    - Full error traces (path:line + 1-line message only)
    - Inlined logs, JSON dumps, schemas

    If you have detail that exceeds 50 lines, write it to
    `.autopilot/agent_returns/{unit.id}.md` and reference the path in
    your **Concerns / Notes**. The orchestrator only reads the first
    50 lines of your return — anything beyond is invisible.

    CONFIRM-AFTER-RUN prefixed lines (per Autonomy Doctrine above) still
    apply and count toward the 50-line cap.

    ## Completion
    Emit ## IMPLEMENTATION COMPLETE when done (files staged).
    If you need more context, emit ## NEEDS_CONTEXT with what's missing (from disk, NOT from the user).
    If you hit a blocker, emit ## BLOCKED with details.
    """

  # ── Collect returns ──
  FOR each returned agent:
    IF ## IMPLEMENTATION COMPLETE → mark unit "done" in state.json
    IF ## IMPLEMENTATION DONE_WITH_CONCERNS → mark "done", log concerns to decisions.log
    IF ## NEEDS_CONTEXT → supply context from state.json/plan.md, re-dispatch (max MAX_AGENT_RETRIES)
    IF ## BLOCKED → Tiered Decision Protocol → re-dispatch. If still blocked → mark "failed"
    IF no marker → treat as BLOCKED, re-dispatch once with marker reminder

  # ── Orchestrator commits this batch sequentially ──
  git status --short  # verify staged files
  git commit -m "[autopilot] Batch {N}: {comma-separated unit descriptions}"

  # Handle pre-commit hook failure:
  IF commit fails:
    Dispatch general-purpose agent (model: "opus"):
      "Pre-commit hook rejected the commit. Hook output: {output}.
       Fix the issues, re-stage the files. Do NOT commit."
    Retry commit. If fails again after 2 attempts → log, unstage, continue.

  # ── Verify batch integration ──
  IF typecheck_command is not null:
    Run: {typecheck_command} 2>&1
    IF type errors:
      attempts = 0
      WHILE type errors AND attempts < MAX_BUILD_FIX_ATTEMPTS:
        Dispatch general-purpose agent (model: "opus"):
          "Type errors after integrating batch {N}: {errors}.
           Fix the integration issues. Stage fixes only, do not commit.
           Return contract: ≤50 lines, structured (Status/Summary/Files staged/Verification/Concerns).
           No code blocks >10 lines, no full error traces — path:line + 1-line summary only.
           Overflow → .autopilot/agent_returns/integration-fix-{N}.md.
           Emit ## IMPLEMENTATION COMPLETE when done."
        Run: {typecheck_command}
        attempts += 1
      IF fixed → orchestrator commits: "[autopilot] Batch {N} integration fix"

  # Update state.json with batch results
  NEXT batch
```

After all batches complete:

```bash
git diff --name-only {pre_autopilot_sha}..HEAD > .autopilot/scope.txt
```

If `scope.txt` is empty (all agents failed) → ABORT to Phase 5 with status `ABORTED`.

**→ Write state, compact & continue to Phase 3.**

### Phase 3: QA Loop (parallel audit + fix)

Convergence loop. Orchestrator runs bash commands and dispatches sub-agents. All state persisted to disk every iteration.

```
# Restore or initialize
iteration = state.json.qa_iteration or 0
bug_tracker = read('.autopilot/bug_tracker.json') or {}
prev_issues = null
brainstorm_count = state.json.brainstorm_count or 0

LOOP:
  iteration += 1
  IF iteration > MAX_QA_ITERATIONS: BREAK

  # ── Step 1: Build verification ──
  # Kill stale dev servers in current directory only
  lsof -ti :3000 -sTCP:LISTEN | xargs kill 2>/dev/null || true
  lsof -ti :5173 -sTCP:LISTEN | xargs kill 2>/dev/null || true

  IF build_command is not null:
    build_attempts = 0
    WHILE build fails AND build_attempts < MAX_BUILD_FIX_ATTEMPTS:
      build_attempts += 1

      IF typecheck_command: Run {typecheck_command} 2>&1
      Run: {build_command} 2>&1

      IF exit 0: BREAK (build OK)

      Dispatch general-purpose agent (model: "opus"):
        "Build/typecheck errors (attempt {build_attempts}/{MAX_BUILD_FIX_ATTEMPTS}):
         {error output}
         Diagnose the root cause. Fix the code. Stage fixes only, do not commit.
         Return contract: ≤50 lines, structured (Status/Summary/Files staged/Verification/Concerns).
         No code blocks >10 lines, no full error traces — path:line + 1-line summary only.
         Overflow → .autopilot/agent_returns/build-fix-iter{iteration}.md.
         Emit ## IMPLEMENTATION COMPLETE when fixed."

      Wait for return. If BLOCKED → Tiered Decision Protocol.

    IF build still failing:
      Log to decisions.log: "Build failing after {MAX_BUILD_FIX_ATTEMPTS} attempts"
      Continue to QA (QA may identify root cause)
    ELSE:
      Orchestrator commits: "[autopilot] QA iter {iteration} build fix"

  # ── Step 2: Run tests ──
  IF test_command is not null:
    Run: {test_command} 2>&1
    IF failures:
      Dispatch general-purpose agent (model: "opus"):
        "Test failures: {output}. Fix the CODE, not the tests.
         Stage fixes. Do not commit.
         Return contract: ≤50 lines, structured (Status/Summary/Files staged/Verification/Concerns).
         No code blocks >10 lines. Overflow → .autopilot/agent_returns/test-fix-iter{iteration}.md.
         Emit ## IMPLEMENTATION COMPLETE."
      Wait. If fixed → orchestrator commits: "[autopilot] QA iter {iteration} test fix"

  # ── Step 3: QA audit (parallel fan-out) ──
  Read .autopilot/scope.txt → scope_files

  # ── Partition scope_files into K disjoint subsets ──
  # Goal: dispatch K qa-agents in parallel, each owning a disjoint slice of
  # the diff. Read-only → safe per ~/.claude/rules/when-to-parallelize.md.
  # Audit step is the slowest single step in QA; fan-out gives ~K× speedup.
  IF len(scope_files) < QA_FANOUT_THRESHOLD OR len(state.json.work_units) <= 1:
    # Too small to benefit — single dispatch (preserves prior behavior).
    partitions = [("all", scope_files)]
  ELSE:
    # Partition by work-unit-owned-files (matches Phase 2 ownership).
    partitions_map = {}  # wu_id → list of files
    unowned = []
    FOR each file in scope_files:
      owners = [wu.id for wu in state.json.work_units if file in wu.files]
      IF len(owners) == 0:
        unowned.append(file)
      ELSE:
        # Deterministic assignment: first wu alphabetically by id
        partitions_map[sorted(owners)[0]].append(file)

    # Merge partitions while count > MAX_QA_AUDIT_PARTITIONS — combine the
    # two smallest by file count until under the cap.
    WHILE len(partitions_map) > MAX_QA_AUDIT_PARTITIONS:
      a, b = two partitions with smallest file counts
      partitions_map[a+"+"+b] = partitions_map[a] + partitions_map[b]
      delete partitions_map[a], partitions_map[b]

    # Distribute unowned files into the smallest existing partition.
    IF unowned:
      smallest = partition key with fewest files
      partitions_map[smallest].extend(unowned)

    partitions = list of (partition_id, files) from partitions_map
    # Skip empty partitions (defensive — shouldn't happen post-merge)
    partitions = [(pid, files) for (pid, files) in partitions if files]

  # ── Dispatch all partitions in PARALLEL ──
  # Single message, one Agent call per partition, all model: "opus"
  FOR each (partition_id, files) in partitions (PARALLEL):
    Dispatch qa-agent (model: "opus"):
      "Audit these files: {files}.
       You are auditing a SUBSET of the changed files; other qa-agents are
       auditing other subsets in parallel. You MAY read files outside your
       subset for context (imports, type definitions, callers) — but only
       FLAG bugs in files within your subset. Bugs in files outside your
       subset will be caught by the partition that owns them.

       Only flag bugs that affect runtime behavior. Skip style/naming/formatting.
       Severity rubric:
         CRITICAL = data loss, security vulnerability, crash
         HIGH = wrong behavior visible to users
         MEDIUM = wrong behavior in edge cases only
         LOW = code smell, minor inconsistency
       Categorize every finding.

       Return contract: write the FULL findings list to
       .autopilot/qa_findings_iter{iteration}_part_{partition_id}.md (one section
       per bug, with severity, file, line, description, suggested fix). In your
       return body (≤50 lines), emit ONLY: marker, Status, Summary (counts per
       severity), path to YOUR findings file, and any blockers. Do NOT inline
       the bug list — orchestrator reads it from disk."

  # ── Collect parallel returns ──
  all_passed = true
  any_blocked = false
  partition_files = []  # paths to findings files from partitions that emitted ISSUES FOUND

  FOR each returned qa-agent:
    IF ## VERIFICATION PASSED → continue
    IF ## ISSUES FOUND → all_passed = false; partition_files.append(its findings path)
    IF ## BLOCKED → Tiered Decision Protocol, re-dispatch that partition only
    IF ## NEEDS_CONTEXT → supply, re-dispatch that partition only (max MAX_AGENT_RETRIES)
    IF no marker → treat as BLOCKED, re-dispatch that partition with marker reminder

  IF all_passed: BREAK (all clean!)

  # ── Aggregate partition findings into single iteration findings file ──
  # Downstream fix loop expects .autopilot/qa_findings_iter{iteration}.md
  # Each partition's bugs are in disjoint files → simple concatenation, no dedup
  cat {partition_files joined by space} > .autopilot/qa_findings_iter{iteration}.md

  # On any ## ISSUES FOUND, read the aggregated findings file from disk:
  issues = parse(.autopilot/qa_findings_iter{iteration}.md)
  # If the aggregated file is missing or empty (partition return claimed ISSUES
  # FOUND but didn't write its file), re-dispatch the offending partition ONCE
  # with explicit reminder of the file path + structured format. If still
  # missing after retry, log "qa_findings_parse_failure" and BREAK with current state.

  # ── Step 4: Stall detection ──
  current_issues = normalize each issue to (file, first_8_words_of_description)
  IF prev_issues is not null AND overlap(current_issues, prev_issues) >= 80%:
    IF brainstorm_count >= MAX_BRAINSTORM_ESCALATIONS: BREAK with issues noted
    brainstorm_count += 1
    Dispatch brainstorm (model: "opus"):
      "QA found near-identical issues after fixes: {list}. What's structurally wrong?"
    Wait for ## EXPLORATION COMPLETE. Extract recommendation paragraph.
    IF recommendation contains "needs human" / "escalate" / "unclear" → BREAK.
    Apply recommendation via general-purpose agent dispatch.
  prev_issues = current_issues

  # ── Step 5: Fix bugs via sub-agents (severity-filtered) ──
  critical_high = [b for b in issues if severity in (CRITICAL, HIGH)]
  medium_low = [b for b in issues if severity in (MEDIUM, LOW)]

  Append medium_low to .autopilot/deferred_issues.md (do NOT fix)

  IF no critical_high bugs: GOTO LOOP (QA may find new issues next pass)

  # Update bug_tracker
  FOR each bug in critical_high:
    signature = bug.file + ":" + normalize(bug.description)
    bug_tracker[signature] = (bug_tracker.get(signature, 0)) + 1
  Write bug_tracker to .autopilot/bug_tracker.json

  # Group bugs by file
  bug_groups = group critical_high by file

  # Dispatch fix agents — parallel if disjoint files
  IF all bug_groups touch disjoint files:
    FOR each group (PARALLEL, single message, model: "opus"):
      recurring = any bug where bug_tracker[sig] >= MAX_SAME_BUG_APPEARANCES
      IF recurring:
        Dispatch general-purpose (model: "opus"):
          "Recurring bug ({count}x): {desc} in {file}.
           This has been 'fixed' {count} times and keeps coming back.
           Trace the actual root cause — don't patch symptoms.
           Self-plan: read the file, trace data flow, find the real issue.
           Stage fixes. Do not commit.
           Return contract: ≤50 lines, structured (Status/Summary/Files staged/Verification/Concerns).
           No code blocks >10 lines. Overflow → .autopilot/agent_returns/qa-fix-iter{iteration}-{file_slug}.md.
           Emit ## IMPLEMENTATION COMPLETE."
      ELSE:
        Dispatch general-purpose (model: "opus"):
          "Fix these bugs in {file}: {bug_list}.
           Self-plan: read the file, understand full context, then fix.
           Minimal changes only. Stage fixes. Do not commit.
           Return contract: ≤50 lines, structured (Status/Summary/Files staged/Verification/Concerns).
           No code blocks >10 lines. Overflow → .autopilot/agent_returns/qa-fix-iter{iteration}-{file_slug}.md.
           Emit ## IMPLEMENTATION COMPLETE."
  ELSE:
    FOR each group (SEQUENTIAL):
      Same dispatch pattern, wait between each

  # ── Step 6: Orchestrator commits fixes ──
  git status --short
  IF staged changes:
    git commit -m "[autopilot] QA iteration {iteration} — fixed {count} bugs"
    IF commit fails (hook rejection):
      Dispatch general-purpose (model: "opus"):
        "Pre-commit hook blocked: {output}. Fix and re-stage."
      Retry. If fails 2x → log, `git reset HEAD`, continue loop.

  # ── Step 7: Persist iteration state ──
  Update state.json: qa_iteration, bugs_fixed, brainstorm_count
  Write bug_tracker to .autopilot/bug_tracker.json

  GOTO LOOP
```

**→ Write state, compact & continue to Phase 4.**

### Phase 4: Final Verification Gate

Orchestrator runs all verification commands directly:

1. **Typecheck** (if available): `{typecheck_command}` → must exit 0
2. **Build** (if available): `{build_command}` → must exit 0
3. **Tests** (if available): `{test_command}` → must pass
4. **Stub detection** (scoped to autopilot's changes):
   ```bash
   git diff {pre_autopilot_sha}..HEAD --name-only | xargs grep -lE "TODO|FIXME|placeholder|not implemented" 2>/dev/null
   ```
5. **Migration safety scan** (if any migration files changed):
   ```bash
   git diff {pre_autopilot_sha}..HEAD -- '*migration*' 'supabase/migrations/*' | grep -iE 'DROP TABLE|DROP COLUMN|RENAME (COLUMN|TABLE)|TRUNCATE|SET NOT NULL'
   ```
   If matches → CRITICAL finding, log to report.
6. **Frontend** (if applicable AND `live_test_enabled`):
   Dispatch `live-test` (model: "opus") → wait for:
   - `## UI VERIFIED` → pass
   - `## UI ISSUES FOUND` → if QA budget remains, dispatch fix agent, loop back to Phase 3
   - `## BLOCKED` → log as DEGRADED, continue

7. **Outcomes grading gate** (only if `state.json.rubric_path` is set, and gates 1-6 passed):

   The Outcomes-style gate. Phase 3's `qa-agent` catches generic software bugs;
   this gate confirms task-specific success criteria are met. Uses a dedicated
   `outcomes-grader` agent (NOT `qa-agent`) — different cognitive task, fresh context,
   higher-quality grading. Findings here are **missing features**, not bugs — they
   are routed to creation agents, not file-bound fix agents, and stored separately
   from `bug_tracker.json` so stall-detection in Phase 3 stays clean.

   ```
   iteration = state.json.outcomes_iteration or 0

   LOOP:
     iteration += 1
     IF iteration > MAX_OUTCOMES_RETRIES: BREAK

     # ── Step 7a: Grade ──
     Dispatch outcomes-grader (model: "opus") with:
       """
       Grade the delivered artifact against the rubric.
       Rubric: (read .autopilot/rubric.md)
       Scope: (read .autopilot/scope.txt)
       Project context: (read .autopilot/project_context.md)

       For each rubric item, evaluate PASS / FAIL / AMBIGUOUS with concrete evidence.

       Return contract: write the FULL per-item grading (each item under
       #### N. <item> with **Verdict:** and **What's missing:** lines, per
       outcomes-grader.md output schema) to
       .autopilot/outcomes_findings_iter{iteration}.md. In your return body
       (≤50 lines), emit ONLY: marker, Status, Summary (counts: N pass / N fail /
       N ambiguous), and the path to the findings file. Do NOT inline the full
       grading in the return body — the orchestrator reads the file from disk.

       Emit ## OUTCOMES PASSED if every item passes.
       Emit ## OUTCOMES UNMET if any item fails or is ambiguous.
       Emit ## BLOCKED if you cannot evaluate.
       """

     IF ## OUTCOMES PASSED → BREAK (rubric satisfied)
     IF ## BLOCKED → Tiered Decision Protocol; if still blocked, log DEGRADED, BREAK
     IF no marker → treat as BLOCKED, re-dispatch once with marker reminder

     IF ## OUTCOMES UNMET:
       # ── Step 7b: Persist unmet items ──
       Parse .autopilot/outcomes_findings_iter{iteration}.md (NOT the agent's
       return body) per outcomes-grader.md output schema →
         extract every FAIL or AMBIGUOUS item with its "What's missing" line.
       Write .autopilot/unmet_outcomes.json:
         [
           {"item": "<verbatim>", "missing": "<grader's description>", "verdict": "FAIL|AMBIGUOUS"},
           ...
         ]

       # Parse-failure fallback: marker is UNMET but no items extracted
       IF parsed items list is empty (findings file missing OR unparseable):
         Re-dispatch outcomes-grader once with explicit reminder:
           "Your previous output emitted ## OUTCOMES UNMET but no FAIL/AMBIGUOUS
            items were parseable in .autopilot/outcomes_findings_iter{iteration}.md.
            Re-grade and write the full findings to that file, following the output
            schema in outcomes-grader.md exactly: each item under #### N. <item> with a
            **Verdict:** line and (for FAIL) a **What's missing:** line."
         IF still 0 items after retry:
           Log to .autopilot/deferred_issues.md as "outcomes_parse_failure: grader
             returned UNMET but per-item structure unparseable after 1 retry"
           BREAK outer loop (do not iterate further; report at Phase 5)

       Append to .autopilot/decisions.log as type "outcomes_unmet" with iteration count.

       # ── Step 7c: Dispatch creation/completion agents ──
       Group items by whether they touch disjoint files (parallelize) vs same files (sequential).
       FOR each unmet item (PARALLEL when disjoint, single message, model: "opus"):
         Dispatch general-purpose with prompt:
           """
           You are an autonomous completion agent for /autopilot.

           ## AUTONOMY CLAUSE — non-negotiable
           Same as Phase 2 implementation agents — never ask the user.
           See Secret & Config Resolution Protocol if config seems missing.

           ## Rubric item (must satisfy)
           {item.item verbatim}

           ## What's missing per grader
           {item.missing}

           ## Scope
           Existing files: (read .autopilot/scope.txt)
           Plan: (read .autopilot/plan.md)
           Project context: (read .autopilot/project_context.md)

           ## Important
           This is a MISSING-FEATURE finding, not a bug fix. The file you need
           to satisfy this criterion may NOT exist yet — create it. Or it may
           need additions to existing files — modify them. Use whatever shape
           best satisfies the rubric item.

           Self-plan before coding:
             1. Decide: which existing files (if any) need changes?
             2. Decide: which new files need to be created?
             3. Read the existing files in scope before modifying them.
             4. Implement minimally — only what's needed to satisfy this item.
             5. Stage your changes with `git add <specific files>`. Do NOT commit.

           Read ~/.claude/rules/database-safety.md, testing-safety.md, git-safety.md.

           ## Return contract (HARD LIMIT)
           ≤50 lines, structured (Status/Summary/Files staged/Verification/Concerns).
           No code blocks >10 lines, no full file bodies, no raw diffs.
           Overflow → .autopilot/agent_returns/outcomes-iter{iteration}-{item_slug}.md.

           ## Completion
           Emit ## IMPLEMENTATION COMPLETE when staged.
           Emit ## NEEDS_CONTEXT if information is missing (from disk, not the user).
           Emit ## BLOCKED with details if you cannot proceed.
           """

       # ── Step 7d: Collect returns + commit ──
       FOR each returned agent:
         IF ## IMPLEMENTATION COMPLETE → mark unmet item as "addressed"
         IF ## IMPLEMENTATION DONE_WITH_CONCERNS → mark item "addressed", log concerns to decisions.log
         IF ## NEEDS_CONTEXT → supply, re-dispatch (max MAX_AGENT_RETRIES)
         IF ## BLOCKED → log to .autopilot/deferred_issues.md, mark item "deferred"
         IF no marker → treat as BLOCKED, re-dispatch once

       git status --short  # verify staged files
       IF staged changes:
         git commit -m "[autopilot] Outcomes iter {iteration}: {N} rubric items addressed"
         IF commit fails (hook rejection):
           Dispatch general-purpose (model: "opus") to fix hook output, re-stage.
           Retry commit. If fails 2x → log, `git reset HEAD`, continue loop.

       # ── Step 7e: Re-run prerequisite gates (typecheck/build/tests) ──
       # Creation agents may have introduced typecheck/build breakage.
       # Re-run gates 1-3 inline (NOT the full Phase 3 QA loop — that's a separate concern).
       # Each gate is bounded by MAX_BUILD_FIX_ATTEMPTS to prevent runaway dispatch.

       FOR each gate in [typecheck_command, build_command, test_command]:
         IF gate is null: SKIP

         attempts = 0
         WHILE gate fails AND attempts < MAX_BUILD_FIX_ATTEMPTS:
           attempts += 1
           Run: {gate} 2>&1
           IF exit 0: BREAK (gate passes)
           Dispatch general-purpose (model: "opus"):
             "Outcomes-iter {iteration} introduced gate failures (attempt {attempts}/{MAX_BUILD_FIX_ATTEMPTS}):
              {error output}
              Fix the CODE (not the test, not the gate command). Stage fixes only.
              Return contract: ≤50 lines, structured. No code blocks >10 lines.
              Overflow → .autopilot/agent_returns/outcomes-gate-fix-iter{iteration}.md.
              Emit ## IMPLEMENTATION COMPLETE when fixed."
           Wait for return. If BLOCKED → Tiered Decision Protocol.

         IF gate still failing after MAX_BUILD_FIX_ATTEMPTS:
           Log to .autopilot/decisions.log as "outcomes_gate_failure" with gate name + iteration
           # Mark this outcomes iteration DEGRADED but don't dead-end — outer loop
           # may still produce a passable artifact if other gates fix themselves.
           # If all 3 gates fail across MAX_OUTCOMES_RETRIES iterations, the final
           # report flags this as COMPLETE_WITH_ISSUES.
           CONTINUE to next gate
         ELSE IF attempts > 0:
           Orchestrator commits: "[autopilot] Outcomes iter {iteration} gate fix"

       # ── Step 7f: Persist iteration state ──
       Update state.json.outcomes_iteration
       GOTO LOOP

   # After loop:
   IF last grader return was ## OUTCOMES PASSED:
     status = "rubric satisfied"
   ELSE (retries exhausted with items still unmet):
     Mark workflow status COMPLETE_WITH_ISSUES
     Append remaining unmet items from unmet_outcomes.json to .autopilot/deferred_issues.md
   ```

If ANY gate (1-6) fails AND QA iteration budget remains → loop back to Phase 3.
If budget exhausted → note failures, proceed to Phase 5.

**→ Write state, compact & continue to Phase 5.**

### Phase 5: Report & Notify

Generate `.autopilot/report.md`:

```markdown
# Autopilot Report

**Task:** <summary>
**Status:** COMPLETE | COMPLETE_WITH_ISSUES | ABORTED | ABORTED_API_OUTAGE

<!-- Worktree banner — include ONLY if state.json.worktree_spawned == true -->

> **Ran in worktree:** `<worktree_path>` on branch `<worktree_branch>`
> (auto-spawned because another autopilot was active in the main repo).
>
> **Review:** `cd <worktree_path> && git log --oneline <pre_autopilot_sha>..HEAD`
> **Merge back (from main repo):** `git merge <worktree_branch>` (or open a PR)
> **Clean up:** `git worktree remove <worktree_path>` after merging

## Work Units

| ID   | Description | Status | Agent               |
| ---- | ----------- | ------ | ------------------- |
| wu-1 | ...         | done   | frontend-specialist |
| wu-2 | ...         | done   | general-purpose     |

## Changes

- <file>: <one-line summary>

## QA Summary

- Iterations: <count>
- Bugs found: <count>
- Bugs fixed (CRITICAL/HIGH): <count>
- Deferred (MEDIUM/LOW): <count>

## Parallel Execution

- Batches: <count>
- Max concurrent agents per batch: <count>
- Work units completed: <done>/<total>

## Autonomous Decisions

<top decisions from decisions.log>

## Verification Evidence

- Typecheck: <exit code + error count>
- Build: <exit code>
- Tests: <pass/fail count>
- Stubs: <clean/count>
- Migration safety: <clean/findings>
- Frontend: <verified/issues/skipped>
- Outcomes: <satisfied / N of M items unmet / not provided>

## Outcomes Grading

(Omit this section if no rubric was provided.)

- Rubric source: `<path>` (`user` | `auto-generated` — if auto, **review and edit `.autopilot/rubric.md` before next run**)
- Grader: `outcomes-grader`
- Iterations: <count> / <MAX_OUTCOMES_RETRIES>
- Items addressed (creation agents dispatched): <count>
- Items deferred (still unmet at exit): <count> — see Deferred Issues
- Per-item final results:
  - <item verbatim> — PASS (<evidence>)
  - <item verbatim> — FAIL (<what's missing>)
  - ...

## Deferred Issues

<MEDIUM/LOW not auto-fixed from deferred_issues.md>

## API Stability

(Omit if no api_retry events.)

- Total retries: <N>
- Recoveries after retry: <N>
- Exhaustions: <N>
- Circuit breaker: tripped / not tripped
- Status if tripped: ABORTED_API_OUTAGE — see deferred_issues.md

## External Blockers

(Omit if none.)

- BLOCKED_BY_EXTERNAL: <system> — <what's blocking> — <work unit ID>
- Resolution: <what the user must do externally before re-invoking /autopilot resume>

## Confirm-After-Run

(Omit if none. Semantic-ambiguity defaults the orchestrator auto-resolved per Tiered Decision Protocol — user reviews these and overrides if needed.)

- <decision> — auto-picked **<chosen option>** because <reason>. To override: <what to edit + re-run command>

## Remaining Issues

<CRITICAL/HIGH unresolved, with context>

## Push Status

(One line — machine-parseable. The orchestrator NEVER pushes itself.)

Compute via:

- Branch with upstream set (`git rev-parse --abbrev-ref --symbolic-full-name @{u}` returns 0): `PUSH_PENDING: <branch> <N> commits ahead of <upstream>` where N = `git rev-list --count @{u}..HEAD`
- Branch with NO upstream set (newly created local branch never pushed): `PUSH_PENDING: <branch> NEW_BRANCH <N> commits — no upstream tracking` where N = `git rev-list --count HEAD ^$(git rev-parse origin/HEAD 2>/dev/null || echo HEAD~0)` (count vs default branch; falls back to total HEAD count if origin/HEAD also missing)
- If user authorized push in advance via the user prompt: `PUSH_PENDING: SUPPRESSED — user pre-authorized in this session`
```

**Terminal Cleanup Block (named, referenced — runs BEFORE the terminal summary on every Phase 5 exit AND every ABORT path that occurs after the Workspace Isolation block wrote `.autopilot/lock`):**

```bash
# Set terminal_state in state.json — values: complete | complete_with_issues | aborted | aborted_api_outage
STATUS_LOWER=$(echo "<STATUS>" | tr '[:upper:]' '[:lower:]')
jq --arg s "$STATUS_LOWER" '.terminal_state = $s' .autopilot/state.json > .autopilot/state.json.tmp \
  && mv .autopilot/state.json.tmp .autopilot/state.json

# Release lock LAST — state must be durable on disk before lock is removed,
# so the next /autopilot invocation reads a coherent terminal_state.
rm -f .autopilot/lock
```

**Abort-path coverage rule (binding):** Every `ABORT:` instruction in this document that fires AFTER the Workspace Isolation block wrote `.autopilot/lock` MUST execute the Terminal Cleanup Block (with appropriate `<STATUS>`) before emitting the user-facing abort message. Under the always-worktree policy there is no shared lock to race against, so the backstop concern of prior versions (stale-lock detection on a concurrent invocation) no longer applies — each invocation owns its own worktree's `.autopilot/lock` exclusively. Cleanup-on-abort still matters because `/autopilot resume` inside the same worktree reads `terminal_state` to decide whether resume is meaningful.

Concrete sites in this document that MUST invoke Terminal Cleanup before aborting (status in parens):

- "Context exhausted at Phase {N}" (`aborted`) — after Context Budget Gate
- Pre-flight table rows: "Initialize the repo…", "Cannot auto-stash residual changes…", "Another git process is running.", "No task found." (all `aborted`)
- Phase 2/3 "ABORT to Phase 5" sites (`aborted`) — Phase 5's own cleanup covers these IF the path actually transitions to Phase 5; if the abort exits directly, invoke cleanup inline
- Circuit breaker exit (`aborted_api_outage`) — already routes to Phase 5, which runs cleanup

Pre-flight ABORTs that occur BEFORE lock acquisition (none currently — the Workspace Isolation block is the first action of Phase 0) would skip cleanup since there's no lock to release.

**Terminal summary** (last thing the orchestrator emits before hard exit — NO questions, NO "want me to" sign-offs):

- Status (COMPLETE / COMPLETE_WITH_ISSUES / ABORTED)
- **If `worktree_spawned == true`:** the single line `WORKTREE: <worktree_path> (branch <worktree_branch>) — merge back when ready`
- Files changed (count + list)
- Bugs fixed (count)
- Verification status (pass/fail per gate)
- Deferred issues count
- External blockers count
- Confirm-After-Run defaults count
- Any remaining CRITICAL/HIGH issues
- Final line, verbatim: `Run complete. Review .autopilot/report.md, .autopilot/decisions.log, and git log --oneline. Push manually when ready.`

**Banned in the terminal summary:**

- "Want me to push", "should I", "or continue with", "let me know"
- Any question mark
- Any "Resume:" line
- Any A/B/C menu
- "Awaiting" / "paused" / "ping me back"

The orchestrator's last act is to write the report and the terminal summary, then return control. The user's next move is theirs to choose without prompting.

**Telegram notification** (if available, else write to `.autopilot/notification.txt`):

```
Autopilot finished: {STATUS}
Task: {summary}
{done}/{total} work units | {bugs_fixed} bugs fixed
```

## Anti-Patterns (will not do)

- Mark a work unit `failed` for transient API errors (overloaded_error, rate_limit_error, "529 overloaded", "503 Service Unavailable") without exhausting MAX_API_RETRIES first
- Dispatch additional Agent calls after the per-phase circuit breaker tripped (`api_retry_exhaustions_in_phase >= MAX_PHASE_API_EXHAUSTIONS`) — exit cleanly to Phase 5 with `ABORTED_API_OUTAGE`
- Skip persisting `current_dispatch_retry` to state.json before entering a backoff sleep — compaction can cross the sleep boundary; without persistence, the retry is lost
- Ask the user anything during execution
- Read or write source code in the orchestrator thread
- Fix bugs inline — always dispatch sub-agent
- Plan inline — always dispatch safe-planner or let sub-agent self-plan
- Dispatch a sub-agent without `model: "opus"`
- Let sub-agents commit — orchestrator commits sequentially
- Use `git add -A` or `git add .` (sub-agents or orchestrator)
- Skip QA because "changes are small"
- Push to remote
- Refactor beyond scope
- Delete tests to make them pass
- Claim "done" without verification evidence in this turn
- Loop infinitely — hard caps on every loop
- Fix MEDIUM/LOW issues (log, don't fix)
- Expand QA scope beyond autopilot-touched files
- Use brainstorm for tactical decisions
- Dispatch parallel agents that write to the same files
- Skip compaction between phases
- Auto-claim uncommitted changes as task
- Trust ephemeral in-memory state — persist everything to .autopilot/
- **Halt mid-phase with "Run paused" / "preserves resume point" / "context approaching POOR" because sub-agent returns were heavy.** Sub-agent returns are capped at 50 lines per the Return Contract. If a return blew the cap, the agent violated contract — log `agent_return_oversized` to `decisions.log` and continue dispatching. The only legitimate mid-run exits are listed in Autonomy Doctrine.
- Inline a sub-agent's full return body into orchestrator context. Read marker + structured fields only; verify work from disk (`git diff --stat`, `git diff --name-only`, file existence checks).
- Trust an agent's prose claim that "I implemented X" without running `git diff --name-only {pre_autopilot_sha}..HEAD` to confirm staged changes match the agent's claimed files.
- Parse a sub-agent's prose body for structured data (bug lists, grader findings, etc.). When the contract specifies a findings file (e.g., `.autopilot/qa_findings_iter{N}.md`, `.autopilot/outcomes_findings_iter{N}.md`), parse the file from disk, never the return body.
- Hand-roll lock acquisition or stale-lock detection on `.autopilot/lock`. The always-worktree policy in Phase 0 guarantees no collision — each invocation owns its own worktree's `.autopilot/lock` exclusively.
