# Orchestrator — Implementation Plan

Status: **Draft v1** — locked-in decisions from brainstorm rounds, ready to execute.
Last updated: 2026-05-05.

This plan survives compaction, session transfers, and context limits. Anyone (human or Claude) can pick it up cold and continue. Update the **Changelog** at the bottom every time scope or decisions change.

---

## North Star

A unified surface — currently `~/.claude/autoloop-dashboard/`, to be renamed `~/.claude/orchestrator/` — that lets the user **manage work, not supervise agents**. Drop a Linear ticket, approve the plan in ~30 seconds, walk away, get a PR notification when it's ready for human merge review.

It absorbs:

- Today's autoloop monitoring (already built — auto-discovers `.autoloop/`, surfaces logs, lifecycle controls).
- A Symphony-equivalent dispatcher (Linear → plan → human gate → autonomous execution → verification → PR).
- An autopilot run viewer (auto-discovered `.autopilot/` dirs, same chrome).
- A harness abstraction so this works with Claude Code today and Codex/others later.

**Tagline:** Manage work, not agents.

---

## Architecture decisions (locked)

These are the load-bearing calls from three rounds of brainstorm. Reversing them is expensive — flag in the Changelog if you need to.

### 1. Tiered harness, not interchangeable peers (Option D)

```
HarnessAdapter
├── Tier 1 (rich):    Claude Code only.
│                     Plan via safe-planner subagent.
│                     Execute via /autopilot (parallel work units, qa-agent, live-test).
│                     Verify with subagents inside the harness.
│
└── Tier 2 (minimal): Codex / Aider / future.
                      Plan via plain prompt, no subagents.
                      Execute via single harness invocation.
                      Verify via external shell only (tsc, vitest, eslint).
                      No qa-agent. No live-test. PR labeled "shallow verification".
```

**The orchestrator does NOT dispatch subagents.** Subagents are an _adapter-internal_ concept. The Claude Code adapter dispatches them by virtue of running `claude -p` with the right system prompt. The orchestrator just says "run Symphony intent" and the adapter decides whether that's 1 process or 3.

Rejected: Option A (thin harness, fat orchestrator — loses subagent value, reimplements 3000+ LOC). Option B (per-harness recipe, common interface — interface keeps growing, rots independently). Option C (harness as code-writer only — same as A in a hat).

### 2. Symphony backend ships before Symphony UI

Stage 2 ships a fully working Linear → plan → autopilot → PR loop using shell scripts + auto-discovered cards in the existing dashboard. No Symphony-specific UI. Stage 3 adds the polished UI as a UX upgrade, not a blocker.

### 3. Human gate at planning, not at PR

Plan review takes ~30s; PR review still happens at the end (CI + human merge). The human is gated twice:

1. "Is this the right work?" (plan stage)
2. "Is the code good?" (PR stage)

This is how senior engineers actually work — design review then code review. A bad plan caught at T=0 wastes ~$0.50; a bad plan caught at PR wastes $5-10 in execution tokens.

### 4. Linear is v1, GitHub Issues is v2

User explicitly wants Linear. Use Linear's GraphQL API + their states as our state machine. No custom JSON API needed — Linear IS the API.

### 5. autopilot is the per-issue executor

Not autoloop. autoloop stays as a separate primitive for ratchet/metric optimization (perf tuning, ML loop). autopilot's 5 phases (preflight → decompose → parallel implement → QA loop → final verification gate → report) map directly onto Symphony's per-ticket flow. We pre-seed `.autopilot/plan.md` with the approved plan and invoke `/autopilot resume`.

### 6. Defer Stage 4 (Codex adapter) until concrete trigger

Build the `HarnessAdapter` interface as a seam from Stage 0. Don't build the second adapter on speculation. Concrete trigger = price hike, model regression, outage, or teammate who only has Codex. If you build Stage 4 anyway, commit to dogfooding Codex on a real ticket within a week or it's dead code.

### 7. Naming: keep "Orchestrator" with documented overload

`/autopilot` is internally called "the orchestrator" pattern. The dashboard is also "Orchestrator". Disambiguate by context — most conversations will say "the dashboard" or "autopilot" anyway. Not load-bearing.

---

## Per-ticket flow (the canonical loop)

```
Linear ticket gets label `claude:plan-me`
  ↓
[Orchestrator daemon] Webhook (or 60s poll) → acquire ticket lock → set "Symphony Planning"
  ↓
[Orchestrator] Spawn Tier 1 adapter (Claude Code) with safe-planner prompt
  ↓
[Adapter] Reads ticket body, produces plan.md in .symphony/issues/<linear-id>/
  ↓
[Orchestrator] Posts plan as Linear comment + transitions to "Awaiting Plan Approval"
  ↓
══════ HUMAN GATE (30s review in Linear OR dashboard) ══════
  ↓
Human action:
  ├─ Status → "Approved"               → continue
  ├─ Comment → revisions               → re-plan loop (max 3)
  └─ Status → "Rejected"               → close ticket, no work done
  ↓
[Orchestrator] Copy approved plan.md → approved-plan.md
  ↓
[Orchestrator] Spawn Tier 1 adapter with prompt: "/autopilot resume" + state-dir override
  ↓
[Adapter] /autopilot runs Phase 2-5 autonomously:
   Phase 2: Implement (parallel sub-agents, batch commits)
   Phase 3: QA loop (qa-agent + severity rubric, MAX_QA_ITERATIONS=5)
   Phase 4: Final verification (typecheck, build, tests, stub-detect, migration scan, live-test)
   Phase 5: Report → .autopilot/report.md
  ↓
[Orchestrator] Read report.md — if COMPLETE or COMPLETE_WITH_ISSUES:
  ↓
[Orchestrator] Run additional verification (Tier 1):
   - Backend smoke on ephemeral Supabase branch (if migrations changed)
   - Visual diff via pixelmatch (if frontend changed; baseline in .symphony/baselines/)
  ↓
[Orchestrator] Open PR: gh pr create with proof-of-work template (plan, QA summary, screenshots, diff link)
  ↓
[Orchestrator] Comment PR link on Linear, transition → "In Review", apply label `symphony:verified-rich`
  ↓
[Human] Reviews PR + waits for CI → merges
```

For Tier 2 (Codex/Aider) the planning + execution steps are simpler (single prompt, no subagents) and the verification step skips qa-agent + live-test, applying label `symphony:verified-shallow` instead.

---

## HarnessAdapter interface (the seam)

```typescript
// orchestrator/src/harness/types.ts

export type RunIntent = {
  type: "symphony" | "autopilot" | "autoloop";
  workdir: string; // absolute path
  stateDir: string; // .symphony/issues/<id>, .autopilot, .autoloop
  prompt: string; // seed prompt or approved plan
  systemPromptFile?: string; // skill/instructions file
  budgetUsd?: number;
  timeoutSec?: number;
  model?: string;
  scope?: string[]; // files/dirs in scope (Tier 2 hint)
};

export type RunHandle = {
  pid: number;
  pgid?: number;
  agentLog: string; // path to streaming output
  start: Date;
  cancel(): Promise<void>;
};

export type RunResult = {
  exitCode: number;
  reason: "clean" | "crash" | "stall" | "timeout" | "budget" | "cancelled";
  filesChanged: string[]; // from git diff
  costUsd?: number;
  markers: string[]; // H2 markers found in output
};

export interface HarnessAdapter {
  readonly id: "claude-code" | "codex" | "aider" | string;
  readonly tier: 1 | 2;

  readonly capabilities: {
    subagents: boolean;
    streamJsonEvents: boolean;
    appendSystemPrompt: boolean;
    budgetCap: boolean;
  };

  spawn(intent: RunIntent): Promise<RunHandle>;
  status(handle: RunHandle): Promise<"running" | "exited" | "crashed">;
  collect(handle: RunHandle): Promise<RunResult>;

  // Tier 1 only — Tier 2 throws NotSupported
  dispatchSubagent?(
    name: string,
    prompt: string,
    opts?: object,
  ): Promise<RunResult>;
}
```

**State ownership boundary:**

- Adapter owns: `<stateDir>/<harness-id>/{agent.log, agent.pid, harness.lock}`
- Orchestrator owns: everything else (`plan.md`, `phase.txt`, `manifest.json`, `results.tsv`, `approved-plan.md`)

This is what makes harness swap possible without losing run history.

---

## The Run data model

```typescript
// orchestrator/src/runs/model.js
type RunType = "autoloop" | "autopilot" | "symphony";

type Run = {
  id: string; // hash of stateDir
  type: RunType;
  harness: "claude-code" | "codex" | "unknown";
  workdir: string;
  stateDir: string;
  status: "idle" | "running" | "awaiting-approval" | "completed" | "failed";
  phase: string | null; // current phase from phase.txt
  manifestVersion: number;
  startedAt?: string;
  pid?: number;
  // Symphony-specific (null for other types)
  linearTicketId?: string;
  linearStatus?: string;
};
```

Each run writes a `manifest.json` to its `stateDir` so the dashboard can render heterogeneous run types without monolithic if/else chains. Discovery extends to all three markers: `.autoloop/`, `.autopilot/`, `.symphony/issues/*/`.

---

## Stages — sequential, each shippable

### Stage 0+1 — Rename + Run model + adapter scaffolding

**Effort:** 1.5 nominal days, 2 days realistic.

**Files:**

- Rename `~/.claude/autoloop-dashboard/` → `~/.claude/orchestrator/`. Keep `autoloop-dashboard` as a symlink for one release so existing references still resolve.
- New: `src/runs/{discover,model,manifest}.js`
- New: `src/harness/{types.ts (or .d.ts), claude-code.js, codex.js (stub), index.js}`
- Rewrite: `server.js` — discovery extends to all three markers
- Touch: `dashboard.html` — `runType` badge per row, no other UX change
- Apply: DESIGN.md (Anthropic warm-ivory parchment) tokens to dashboard.html — see Design System section below

**Code skeleton:**

```javascript
// runs/model.js
function loadRun(stateDir) {
  /* reads manifest.json, falls back to legacy detection */
}
function listRuns(scanRoots) {
  /* unified discovery */
}

// runs/discover.js
function discoverByMarker(scanRoots, marker) {
  /* scan for .autoloop, .autopilot, .symphony */
}

// runs/manifest.js
function writeManifest(stateDir, run) {
  /* adapters call this on spawn */
}
function readManifest(stateDir) {
  /* returns Run | null */
}

// harness/index.js
const adapters = {
  "claude-code": require("./claude-code"),
  codex: require("./codex"),
};
function pickAdapter(id) {
  return adapters[id] ?? throw new Error(`Unknown adapter: ${id}`);
}
```

**Acceptance:**

- `cd ~/.claude/orchestrator && bash start.sh` launches the dashboard.
- All existing autoloop dirs render identically to before — zero regression.
- Adding an empty `.autopilot/` dir somewhere makes a row appear with `runType=autopilot`.
- `node -e "require('./src/harness').pickAdapter('codex').spawn({})"` throws `NotImplemented` (proves the registry).
- DESIGN.md tokens applied — page background is `#faf9f5`, all buttons `border-radius: 0`, no box-shadows anywhere.

**Dependencies:** None.

**Skip cost:** Bolting Symphony onto the autoloop-only data model produces `if (type === 'symphony')` branches everywhere. Within 6 weeks the codebase rejects all further evolution.

---

### Stage 2 — Symphony backend, headless, Claude Code only

**Effort:** 4 nominal days, 5-6 realistic.

**Files:**

- New: `src/symphony/linear.js` — Linear GraphQL client (poll, comment, transition)
- New: `src/symphony/orchestrator.js` — the per-ticket flow
- New: `src/symphony/budget.js` — daily cap + per-ticket cap + global kill switch
- New: `src/symphony/verifier.js` — runs `tsc/vitest/eslint`, calls Tier 1 adapter for `qa-agent`/`live-test`, runs Supabase branch backend smoke if migrations changed, runs pixelmatch visual diff if frontend changed
- New: `~/.claude/commands/symphony-plan.md` — skill the planner reads (Linear-aware, mirrors autopilot Phase 1)
- New: `~/.claude/commands/symphony-execute.md` — wraps `/autopilot resume` with pre-seeded plan + Linear ID
- Touch: `server.js` — `POST /api/symphony/poll` (manual trigger), `POST /api/symphony/kill` (global kill)
- Touch: `config.example.json` — Linear API key, team ID, polling interval, daily/per-ticket budget USD

**Code skeleton:**

```javascript
// symphony/orchestrator.js
async function processTicket(ticketId) {
  if (await budget.isExhausted()) return abort('budget');
  await acquireLock(ticketId);
  await linear.transition(ticketId, 'Symphony Planning');

  const stateDir = `.symphony/issues/${ticketId}`;
  const adapter = pickAdapter('claude-code');
  const planRun = await adapter.spawn({
    type: 'symphony', workdir, stateDir,
    prompt: planPromptFor(ticket),
    systemPromptFile: '~/.claude/commands/symphony-plan.md',
    budgetUsd: 2,
  });
  const planResult = await waitFor(planRun);
  const plan = await readFile(`${stateDir}/plan.md`);

  await linear.commentPlan(ticketId, plan);
  await linear.transition(ticketId, 'Awaiting Plan Approval');
  // STOP — human gate
}

async function onApproval(ticketId) {
  const stateDir = `.symphony/issues/${ticketId}`;
  await fs.cp(`${stateDir}/plan.md`, `${stateDir}/approved-plan.md`);

  const execRun = await adapter.spawn({
    type: 'symphony', stateDir,
    prompt: `/autopilot resume`,
    budgetUsd: 8,
    // adapter sets AUTOPILOT_STATE_DIR=<stateDir>/autopilot-state
  });
  await waitFor(execRun);

  const verification = await verifier.run(stateDir);
  if (!verification.passed) return markFailed(ticketId, verification);

  const prUrl = await openPR(ticketId, verification);
  await linear.comment(ticketId, `PR: ${prUrl}`);
  await linear.transition(ticketId, 'In Review');
  await linear.label(ticketId, 'symphony:verified-rich');
}

// symphony/linear.js
async function poll(label)               // → Ticket[]
async function transition(id, status)    // → void
async function commentPlan(id, plan)     // → { commentUrl }
async function watchStatus(id, target)   // → EventEmitter (SSE-style)

// symphony/budget.js
async function isExhausted()             // reads .symphony/budget.json (daily)
async function isTicketExhausted(id)     // per-ticket cap
async function record(usd, ticketId)
async function killAll()                 // SIGTERM every running symphony adapter
```

**Acceptance:**

- Label a Linear ticket `claude:plan-me`. Within 60s plan appears as a Linear comment + status flips to "Awaiting Plan Approval".
- Manually flip status to "Approved" → execution starts, branch created (`symphony/<ticket-id>`), commits land, PR opens with `Closes <ticket>` and `symphony:verified-rich` label.
- Daily budget cap of $20 actually halts new ticket pickup at $20.01 spent.
- Per-ticket cap of $10 kills the run + comments "exceeded budget — needs decomposition" + transitions to "Blocked".
- Global kill via `POST /api/symphony/kill` SIGTERMs all running symphony adapters within 5s.

**Dependencies:** Stage 0+1 done.

**Skip cost:** You don't have Symphony. Don't skip.

**This is when Symphony actually ships.** End of Stage 2 = ~day 6. You flip Linear statuses by hand for now, but the autonomous loop works.

---

### Stage 3 — Symphony UI on the dashboard

**Effort:** 3 nominal days, 4 realistic.

**Files:**

- Touch: `dashboard.html` — three new components in design-system style:
  - **Plan-approval inline expansion** (not a modal — modal adds clicks for a 30s action). Shows plan markdown rendered in editorial style, with Approve / Reject / Edit & Approve buttons.
  - **Linear ticket card** — issue title, link, current Linear status as metadata label (Anthropic Mono uppercase).
  - **Verification stack progress strip** — typecheck → unit → qa-audit → backend smoke → live-test → PR opened, each as a hard-edged segment that fills with dark on completion.
- Touch: `server.js`:
  - `POST /api/symphony/approve/:ticketId` — flips Linear status to Approved, calls `onApproval`
  - `POST /api/symphony/reject/:ticketId` — posts comment, sets status to "Plan Rejected"
  - `GET /api/symphony/ticket/:id` — proxies Linear, returns `{ ticket, plan, status, verification }`
  - `GET /api/symphony/runs` — `Run[]` filtered by `type=symphony`
  - `GET /api/symphony/budget` — `{ dailyUsd, spentToday, remaining }`
- New: `src/symphony/render.js` — server-side data shaping for the UI

**Acceptance:**

- Symphony tickets show as their own row type, distinct from autoloop/autopilot, badge color-coded.
- Clicking an awaiting-approval row inline-expands the plan with `Approve` / `Reject` / `Edit & Approve` buttons.
- Approve flips Linear status and starts execution within 3s.
- Verification strip shows live progress; completed segments fill with `#141413`.
- Edit & Approve writes directly to `approved-plan.md` (does NOT rely on parsing Linear comment edits).

**Dependencies:** Stage 2 done.

**Skip cost:** You manually flip Linear statuses forever. Workable but annoying. Can ship as v1.1 if scope is tight.

**End of Stage 3 = it feels like Orchestrator.** ~day 10.

---

### Stage 4 — Codex adapter + multi-harness selector + polish (DEFERRED unless committed)

**Effort:** 5 nominal days, 7 realistic.

**Only build this if you have a concrete trigger to use Codex within a week of finishing.** Otherwise the adapter rots faster than you can fix it.

**Files:**

- Implement: `src/harness/codex.js` (was a stub from Stage 0+1)
- New: `src/symphony/tier2-flow.js` — plan-via-prompt, execute-via-prompt, verify-via-shell-only
- Touch: `dashboard.html` — harness picker on "add project" form; "shallow verification" banner on Tier 2 PRs
- Touch: `~/.claude/commands/symphony-plan.md` — make adapter-neutral (no `<subagent_type>` directives)

**Code skeleton:**

```javascript
// harness/codex.js
const adapter = {
  id: "codex",
  tier: 2,
  capabilities: {
    subagents: false,
    streamJsonEvents: false,
    appendSystemPrompt: true,
    budgetCap: false,
  },
  async spawn(intent) {
    const args = ["run", "--auto", "--workdir", intent.workdir];
    if (intent.systemPromptFile)
      args.push("--instructions", intent.systemPromptFile);
    args.push("--prompt", intent.prompt);
    const child = spawn("codex", args, { detached: true });
    return {
      pid: child.pid,
      agentLog,
      start: new Date(),
      cancel: () => process.kill(-child.pid),
    };
  },
  // status/collect mirror claude-code adapter shape
};

// symphony/tier2-flow.js
async function processTicketTier2(ticketId, adapter) {
  // Same shape as Tier 1 BUT:
  //  - external verification only (tsc + vitest + eslint)
  //  - no live-test
  //  - no qa-agent
  //  - PR labeled `symphony:verified-shallow`
  //  - PR body banner: "Verification: tier-2 (typecheck + unit only). Manual review recommended."
}
```

**Acceptance:**

- Add-project form lets you pick `claude-code | codex` per project.
- Codex-configured project produces a working PR with degraded-mode banner.
- Daily budget panel shows spend by harness.
- Tier 2 PRs apply `symphony:verified-shallow`; branch protection requires explicit human review for that label.

**Dependencies:** Stages 2 and 3.

**Skip cost:** You don't actually have harness-agnosticism. You have "Symphony for Claude Code with a stub interface." If you're being honest about not using Codex yet, that may be the right place to stop.

---

## Top 5 load-bearing risks (all v1)

1. **Linear status race condition.** Two events fire at once (you approve while polling is mid-flight). Symptom: ticket flickers between statuses, executor spawns twice → two branches, two PRs.
   **Mitigation:** per-ticket lock file at `.symphony/issues/<id>/.lock` checked before any state transition + Linear `updatedAt` ETag matching on every transition.

2. **Plan approval that's actually a plan rewrite.** Human reads plan, mostly likes it, edits 3 lines in a Linear comment. Executor runs the _original_ plan because it reads `plan.md`, not the comment.
   **Mitigation:** dashboard saves edits directly to `approved-plan.md`; Linear is notified after. The dashboard path is cleaner than parsing `PLAN_AMENDMENT:` prefixes from Linear comments.

3. **Cost runaway from a single bad ticket.** Pathological ticket dispatches 5 parallel agents at $4 each + QA loop at $6 = $26 from a single ticket. Daily $20 cap is already gone.
   **Mitigation:** per-ticket hard cap (default $10) separate from daily cap. On hit: kill, comment "exceeded budget — needs human decomposition" to Linear, transition to "Blocked".

4. **Stale autopilot state across runs.** `.autopilot/` from a prior run lives at the same path; new symphony run picks up stale `wu-3.md` etc.
   **Mitigation:** symphony state at `.symphony/issues/<id>/autopilot-state/`, isolated per ticket. Teach `/autopilot` to accept `--state-dir` (small change to autopilot.md resume logic).

5. **Multi-harness verification quality drift** (if Stage 4 is built). Reviewers learn Tier 1 PRs are usually correct and extend the same trust to Tier 2. Tier 2 sneaks through.
   **Mitigation:** distinct PR labels (`symphony:verified-rich` vs `symphony:verified-shallow`). Branch protection requires explicit human review for `verified-shallow`. Don't rely on humans noticing the PR body banner.

---

## Design system

**Source of truth:** `./DESIGN.md` (in this directory — the Anthropic warm-ivory parchment system).

**Hard rules** that override default web aesthetics:

- Page background: `#faf9f5` (Ivory Light). **Never** `#ffffff` or any pure gray.
- Primary text: `#141413` (Slate Dark). **Never** `#000000`.
- Border default: `1px solid #141413`.
- **Zero box-shadows.** Surface depth via background contrast only — `#faf9f5` vs `#141413` vs `#e3dacc`.
- Border radius is meaningful:
  - Cards: `8px`
  - Panels: `16px`
  - Featured cards (dark editorial): `24px`
  - **Buttons: `0px`** (deliberate formal signal — no pill, no rounded buttons).
  - Primary CTA "Try Claude" pattern: `0px 0px 8px 8px` (asymmetric — flat top, rounded bottom).
- Type families:
  - Anthropic Sans (substitute Inter or DM Sans) — all UI chrome, body, headlines
  - Anthropic Serif (substitute Playfair Display or Lora) — **only** at display sizes (91px, weight 400) **only** on dark editorial cards (`#141413` surface)
  - Anthropic Mono (substitute JetBrains Mono) — metadata field labels only ('DATE', 'CATEGORY')
- Type scale: `12 / 15 / 18 / 20 / 24 / 61 / 91` px. Letter-spacing tightens at display: `-1.22px` at 61px.
- Headline emphasis is **underline only**, never color, never bold weight increase. Apply to selected keywords in display-scale headlines.
- Chromatic accents (Clay `#d97757`, Olive, Sky, Fig, Cactus) — one accent per section maximum, deployed sparingly. Default state has zero chromatic color.
- Metadata labels are pure text — **no chip, no pill, no capsule background.**
- Surface alternation: ivory base → dark editorial card (24px radius, contained inversion not full-bleed) → light card grid → repeat. Hard-edged transitions, no gradient fade.

**Spacing:** base unit 4px. Scale: 4 / 8 / 12 / 16 / 32 / 76 / 84. Card padding 31px. Section gap 61px.

**Layout:** max-width 1200px centered. No sidebar.

When implementing UI in any stage, read `DESIGN.md` first. The Quick Start section has CSS custom properties + Tailwind v4 tokens ready to paste.

---

## What's deferred / out of scope (v1)

Explicit "no" list — don't quietly creep these in:

- ❌ Webhook receiver for Linear (start with 60s polling; webhooks are v2).
- ❌ Web dashboard rebuild from scratch — extend the existing 4700 LOC HTML.
- ❌ Walkthrough videos as proof-of-work (PR diff + screenshots + plan = enough).
- ❌ Custom JSON API beyond what the dashboard needs — Linear is the API.
- ❌ Multi-project federation (one Symphony watching N repos via shared dashboard) — local first.
- ❌ GitHub Issues adapter — Linear-only v1.
- ❌ Cron scheduling, recurring tickets — manual trigger or label-on-create only.
- ❌ Dashboard auth — assume single-user local, secure via firewall/VPN if exposed.
- ❌ Modal-based plan approval — use inline row expansion (modal adds clicks for a 30s action).
- ❌ Codex adapter (Stage 4) — DEFERRED unless concrete trigger.

If any of these become required, document the trigger in the Changelog and reopen scope.

---

## Operational invariants

These never change between stages:

1. **Never push to remote** automatically. Symphony opens PRs; humans merge.
2. **Never commit to `main`/`master`.** All work on `symphony/<ticket-id>` branches.
3. **Never ask the user during execution.** All decisions front-loaded at plan-gate. (Plan rejection is the user's "stop" button.)
4. **Per-ticket lock + per-ticket budget cap + daily budget cap.** All three required.
5. **Global kill switch** (`~/.symphony/STOP` flag file or `POST /api/symphony/kill`) checked at every adapter heartbeat.
6. **gitleaks-guard.py enforced as PreToolUse hook** — not opt-in.
7. **Tier 1 PRs labeled `symphony:verified-rich`. Tier 2 PRs labeled `symphony:verified-shallow`.** Branch protection treats them differently.
8. **Verification Gate Function applies** (`~/.claude/rules/gates.md` Part 2). Every "done" claim runs the verification command in this turn.

---

## File structure (target — end of Stage 4)

```
~/.claude/orchestrator/
├── PLAN.md                          ← this file
├── DESIGN.md                        ← Anthropic style system
├── package.json
├── start.sh
├── stop.sh
├── server.js                        ← extended for Symphony routes
├── dashboard.html                   ← extended UI components
├── config.example.json              ← Linear creds, budgets
├── src/
│   ├── runs/
│   │   ├── discover.js
│   │   ├── model.js
│   │   └── manifest.js
│   ├── harness/
│   │   ├── types.ts (or .d.ts)
│   │   ├── index.js                 ← registry / pickAdapter
│   │   ├── claude-code.js           ← Tier 1
│   │   └── codex.js                 ← Tier 2 (Stage 4)
│   └── symphony/
│       ├── orchestrator.js          ← per-ticket flow
│       ├── linear.js                ← GraphQL client
│       ├── budget.js                ← daily + per-ticket caps + kill switch
│       ├── verifier.js              ← tsc/vitest/eslint + qa-agent + live-test + Supabase + pixelmatch
│       ├── tier2-flow.js            ← Stage 4
│       └── render.js                ← server-side data shaping for UI
└── (legacy autoloop-dashboard symlink for one release)

~/.claude/commands/
├── symphony-plan.md                 ← skill for planner (Linear-aware)
└── symphony-execute.md              ← wraps /autopilot resume

~/.symphony/
└── STOP                             ← global kill flag (touched by symphony-stop)

# Per-project state (created in user repos, NOT in ~/.claude/)
.symphony/
├── issues/
│   └── <linear-ticket-id>/
│       ├── manifest.json            ← Run metadata for dashboard discovery
│       ├── plan.md                  ← initial plan from planner
│       ├── approved-plan.md         ← human-edited approved plan
│       ├── .lock                    ← per-ticket lock file
│       ├── verification.json        ← gate results per layer
│       ├── pr-url.txt               ← opened PR URL
│       ├── claude-code/             ← adapter-owned
│       │   ├── agent.log
│       │   ├── agent.pid
│       │   └── harness.lock
│       └── autopilot-state/         ← .autopilot/-equivalent, isolated per ticket
│           ├── state.json
│           ├── plan.md              ← copy of approved-plan.md
│           ├── decisions.log
│           └── ...
└── budget.json                      ← daily + per-ticket spend tracking
```

---

## Honest scope check

| Stage              | Nominal   | Realistic  | Calendar (evenings) |
| ------------------ | --------- | ---------- | ------------------- |
| 0+1                | 1.5d      | 2d         | ~4 days             |
| 2                  | 4d        | 5-6d       | ~2 weeks            |
| 3                  | 3d        | 4d         | ~1 week             |
| 4                  | 5d        | 7d         | ~2 weeks            |
| **Total (with 4)** | **13.5d** | **18-20d** | **4-6 weeks**       |
| **Total (no 4)**   | **8.5d**  | **12d**    | **2-3 weeks**       |

Symphony usable at end of Stage 2 (~day 6). Feels like Orchestrator at end of Stage 3 (~day 10). Multi-harness real at end of Stage 4 (~day 17).

Hidden cost not budgeted: if this becomes a daily driver, observability (run history beyond disk, cost dashboards, alerting on stuck tickets) is another ~week. Not in this plan.

---

## Resume protocol (read this first if picking up cold)

1. Read this PLAN.md fully.
2. Read `./DESIGN.md` if doing UI work.
3. `git log --oneline -20` in `~/.claude/orchestrator/` (or `autoloop-dashboard/` if Stage 0+1 not done).
4. Check Changelog below for any scope changes since last session.
5. Identify current stage: which acceptance criteria are met? Which aren't?
6. Pick the next failing acceptance criterion. That's the work.
7. Update Changelog when done.

If brainstorming a deviation from this plan: dispatch `brainstorm` agent with PLAN.md as context, not a fresh design conversation.

---

## Changelog

Append-only log of scope changes, decisions overturned, or new constraints discovered. Format: `YYYY-MM-DD — change — rationale`.

- 2026-05-05 — Initial plan committed. Architecture decisions locked from 3 brainstorm rounds. DESIGN.md (Anthropic warm-ivory) added as design source of truth. Stages 0+1 → 2 → 3 → 4 (deferred) defined.
- 2026-05-05 — **Stage 0+1 SHIPPED via `/autopilot`.** 7 WUs across 4 batches (1 parallel batch of 4). All 5 acceptance criteria PASS. Final SHA `3c63efc`. 3 deferred non-blocking findings (1 MEDIUM, 2 LOW) at `.autopilot/deferred_issues.md`. Full report at `.autopilot/report.md`. Stage 2 ready: dir is now `~/.claude/orchestrator/`, `pickAdapter` resolves both Tier 1 (claude-code) and Tier 2 (codex stub), `discoverRuns` finds `.autoloop` + `.autopilot` + `.symphony/issues/*` markers, DESIGN.md tokens applied to dashboard.
