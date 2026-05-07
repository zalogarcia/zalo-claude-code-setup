# Engineering Outcome Principles (Rubric)

Used by `outcomes-grader` to evaluate plans (and optionally implementations) against the standards stated in `~/.claude/CLAUDE.md`. Each item describes an **outcome** the plan must exhibit — a measurable property — not a rule to follow. This makes the rubric harder to game and more aligned with how `outcomes-grader` natively evaluates artifacts.

**How this is used:** any orchestrator that produces a plan via `safe-planner` runs the plan through `outcomes-grader` with this file as the rubric. The grader returns per-item PASS/FAIL with quoted plan evidence. Failed items are fed back into a single revision pass.

## Reading the rubric

**Sections 1-6** (positive outcomes) — each item has 3-4 fields:

- **Outcome** — the property the plan must exhibit (positive statement of success)
- **Why** — the failure mode this outcome prevents (provides intent for edge cases)
- **Measure** — how the grader determines PASS/FAIL from the plan text
- **Applicable when** _(optional)_ — scoping clause. If the condition is not met, the grader marks the item PASS with reason `"not applicable: <clause>"`. Do **not** mark non-applicability as AMBIGUOUS — that triggers spurious revision passes.

**Section 7** (Anti-Patterns Absent) — items are inherently absences (forbidden patterns), so they use a shorter shape: `Measure` and optional `Applicable when` only. No `Outcome` or `Why` field. Treat them as binary checks: pattern present in plan → FAIL.

## How to update

Add or refine outcomes as patterns emerge from real runs. Each outcome must be:

- **Specific enough** that two reasonable readers would agree on PASS/FAIL given the same plan
- **Tied to a real failure mode** observed before, not a theoretical concern
- **Measurable** from quoted plan text (or codebase context when explicitly noted)

---

## 1. Architectural Coherence

### Outcome 1.1: Architectural component count is the minimum required for the task

- **Why:** Premature abstraction multiplies surface area, review cost, and failure modes.
- **Measure:** For each architectural component named in the plan (queue, broker, middleware, abstraction layer, new service), evaluate whether removing it would make the task un-implementable. If removable without breaking the feature, FAIL.
- **Applicable when:** plan introduces new architectural components beyond touching existing code.

### Outcome 1.2: Existing project primitives are reused over parallel competing systems

- **Why:** Parallel competing systems create maintenance burden and decision ambiguity.
- **Measure:** For each new architectural element, the plan demonstrates either reuse of an existing primitive OR explicitly justifies why the existing primitive is insufficient.
- **Applicable when:** project context is available (e.g., `.autopilot/project_context.md`) AND plan introduces new architectural components.

### Outcome 1.3: Data flow has the fewest hops for the task's non-functional requirements

- **Why:** Unnecessary intermediation hides bugs, slows debugging, and adds latency.
- **Measure:** Plan describes data flow with each named hop (queue, cache, transform, proxy) tied to a specific non-functional requirement (latency, scale, reliability, isolation) from the task. Hops without justification = FAIL.
- **Applicable when:** plan describes data movement between components.

---

## 2. Scope Integrity

### Outcome 2.1: Every work unit traces directly to a phrase in the task description

- **Why:** Scope creep wastes effort, increases blast radius, and lengthens review.
- **Measure:** For each work unit, the grader identifies the phrase in `.autopilot/task.md` (or equivalent) that necessitates it. A work unit not traceable to a task phrase = FAIL.

### Outcome 2.2: Plan contains no "while we're here" expansion

- **Why:** Hidden scope expansion creates surprise diffs and timeline risk.
- **Measure:** No work unit description begins with "also", "while we're at it", "additionally", or describes work not implied by the task. Cleanup/refactoring not in the task description = FAIL.

### Outcome 2.3: Adjacent work is explicitly bracketed when genuinely necessary

- **Why:** Sometimes adjacent work IS necessary (e.g., type definitions a feature depends on). Making it explicit lets reviewers consent rather than discover.
- **Measure:** Any work outside the strict task description appears in a clearly-labeled section (e.g., `safe-planner`'s "Blast radius" section, an "Adjacent work" subsection, or per-work-unit annotation) AND each adjacent concern has a 1-sentence justification tied to a task requirement. Adjacent work that's just listed in the file scope without justification = FAIL.
- **Applicable when:** plan touches code outside the strict task description.

---

## 3. Failure Resilience

### Outcome 3.1: Failure modes are named at every external boundary the plan touches

- **Why:** Silent failures lead to data loss, security issues, and bad UX.
- **Measure:** For each touched boundary (HTTP request, DB write, file I/O, third-party API call, queue publish), the plan states (a) what fails, (b) what the user sees, (c) what recovers (retry / fallback / surfaced error).
- **Applicable when:** plan touches external boundaries.

### Outcome 3.2: Destructive operations have a stated rollback path

- **Why:** One-way operations can't be undone after damage.
- **Measure:** For each destructive operation (DB migration, schema drop, file deletion, force push, cache invalidation, breaking API change), the plan names a recovery mechanism — snapshot, feature flag, expand-contract migration sequence, or manual recovery procedure.
- **Applicable when:** plan includes destructive operations.

### Outcome 3.3: Validation occurs at boundaries, not at internal helper signatures

- **Why:** Defensive coding at internal helpers adds noise without protection — the type system already guarantees those values. Validation belongs at the system edge (input boundaries from outcome 3.1).
- **Measure:** Each guard or validation step in the plan corresponds to an external boundary. Internal helper signatures are trusted to receive types they declare. No null-checks on type-system-guaranteed non-null values, no retries on idempotent operations that can't transiently fail, no validation duplicated at every internal call site.
- **Applicable when:** plan describes specific guard or validation logic.

### Outcome 3.4: Observability is stated for non-trivial async/external flows

- **Why:** Webhook handlers, queue consumers, payment flows, and background jobs fail silently without logs; postmortems become guesswork.
- **Measure:** For each work unit involving async processing, external webhook, payment, or background job, the plan names what gets logged (event type, key identifiers, outcome) and via which logger (project's structured logger, edge function logs, Sentry, etc.). Silence on logging for these flows = FAIL.
- **Applicable when:** plan includes async processing, external webhook, payment flow, or background job.

---

## 4. Verifiability

### Outcome 4.1: Plan states a concrete, deterministic verification check

- **Why:** "Should work" verification produces false positives and shipped bugs.
- **Measure:** Plan contains a specific check — runnable command + expected output OR observable user behavior — that an unfamiliar engineer could execute to confirm completion. Vague claims like "verify it works" without specifics = FAIL.

### Outcome 4.2: Test strategy is explicit per work unit

- **Why:** "Add tests later" without commitment leads to permanently untested code.
- **Measure:** For each work unit, the plan states one of: (a) what new tests are added, (b) what's explicitly deferred (with reason and a follow-up location), or (c) which existing tests already cover the change. Silence on testing = FAIL.

### Outcome 4.3: Live-system tests use the designated admin/test account

- **Why:** Real user data must not be touched by automated tests in live systems.
- **Measure:** Plan's testing approach for live systems uses the project's designated admin email (per `~/.claude/rules/testing-safety.md`) OR explicitly states an alternative with reason.
- **Applicable when:** plan includes integration tests against live services.

---

## 5. Stack Alignment

### Outcome 5.1: Technology choices match project defaults or overrides are justified inline

- **Why:** Stack divergence creates maintenance burden and team friction.
- **Measure:** New runtime/framework/library/service choices match the default stack (TypeScript, Supabase Edge Functions / Auth / RLS / Storage / DB, Stripe, Vercel, Vitest, Playwright, Tailwind, npm) OR are accompanied by ≥1 sentence inline justification tied to a specific task requirement.
- **Applicable when:** plan introduces a stack-level technology choice.

### Outcome 5.2: New dependencies are justified by named non-trivial functionality

- **Why:** Each dependency adds attack surface, build cost, and version-management burden. "Utilities" or "helpers" don't justify the cost.
- **Measure:** For each new npm/cargo/pip dependency, the plan states either (a) a specific non-trivial subsystem the dep provides — naming concrete functionality like "TLS handshake", "streaming JSON parser", "tree-shake-safe icon set", "Stripe webhook signature verification" — OR (b) that it's already a project standard used elsewhere (referencing an existing import). Generic justifications like "utilities", "helpers", "common functions" = FAIL.
- **Applicable when:** plan adds new dependencies.

### Outcome 5.3: New named entities follow existing repo conventions

- **Why:** Convention drift makes code feel foreign and slows future contributors.
- **Measure:** New names (files, functions, types, routes, env vars) follow the casing, structure, and patterns visible in the project context. New conventions invented in the plan without justification = FAIL.
- **Applicable when:** project context is available AND plan creates new named entities.

---

## 6. Plan Structure

### Outcome 6.1: Plan is decomposable into work units with explicit dependencies

- **Why:** Non-decomposed plans cannot be parallelized, batch-committed, or partially rolled back.
- **Measure:** Plan contains an enumerated work unit list. Each work unit has: (a) ID (e.g., `wu-1`), (b) one-line description, (c) file paths it creates/modifies, (d) dependencies (other work unit IDs or "none"), (e) agent type (frontend-specialist / general-purpose / etc.).

### Outcome 6.2: Each work unit has a single agent owner

- **Why:** Work units that bounce between agents lose context and produce inconsistent code.
- **Measure:** For each work unit, the plan names exactly ONE agent type. Phrasings like "frontend-specialist or general-purpose depending on what's needed" = FAIL.

### Outcome 6.3: Every work unit specifies concrete content, not deferral markers

- **Why:** Plans with placeholder language signal incomplete planning that fails at execution time. Concrete content unblocks autonomous implementation.
- **Measure:** Each work unit's description, file changes, and acceptance criteria contain specific intent. The plan does NOT use `TBD`, `implement later`, `fill in details`, `handle edge cases` (without specifics), or `add appropriate error handling` (without specifics). Cross-references between work units like "tests follow the same shape as wu-2" ARE acceptable shorthand and pass — they're concrete by reference.

### Outcome 6.4: Database migrations follow additive/non-breaking patterns

- **Why:** Breaking migrations against populated tables cause production downtime.
- **Measure:** Plan's migrations are additive-only (CREATE, ADD COLUMN with default/null, CREATE INDEX) OR follow the expand-contract pattern with explicit phases. No DROP/RENAME on populated tables in a single migration. Per `~/.claude/rules/database-safety.md`.
- **Applicable when:** plan includes database migrations.

---

## 7. Anti-Patterns Absent

These remain rule-shaped — they're inherently the absence of a forbidden pattern, not a property to exhibit. Each is a binary check on plan text.

### 7.1: No raw `console.log` in production code paths

- **Measure:** Plan describes logging via the project's structured logger (or omits logging entirely in production paths). Mentions of `console.log` / `console.error` in non-development contexts = FAIL.

### 7.2: No `git add .` or `git add -A`

- **Measure:** Git operations in the plan reference specific files. The phrases `git add .` or `git add -A` appearing as proposed commands = FAIL.
- **Applicable when:** plan describes git operations.

### 7.3: No verification claims without runnable evidence

- **Measure:** Every "verified", "tested", "confirmed working" claim in the plan is paired with a specific command, expected output, or observable check. Bare claims = FAIL.

### 7.4: No hook-bypass flags

- **Measure:** Plan does not include `--no-verify`, `--no-gpg-sign`, or similar bypass flags, UNLESS the original task description explicitly authorizes the bypass with reason.
- **Applicable when:** plan describes git operations.

---

## Output Format Expected from Grader

Per `outcomes-grader` contract in `~/.claude/agents/outcomes-grader.md`:

- Each outcome evaluated PASS / FAIL / AMBIGUOUS
- PASS evidence = quoted plan text demonstrating the outcome (plan-grading mode)
- FAIL evidence = quoted plan text showing the violation, plus what's missing/wrong
- Non-applicable items (per `Applicable when:` clauses) → PASS with reason `"not applicable: <clause>"`, NOT AMBIGUOUS
- AMBIGUOUS reserved for "the plan addresses this concern but unclearly" — not for non-applicability

If multiple outcomes FAIL, the orchestrator collects them and feeds them back to `safe-planner` for one revision pass per `~/.claude/rules/plan-verification.md`.
