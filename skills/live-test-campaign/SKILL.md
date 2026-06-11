---
name: live-test-campaign
description: Run a master live-test campaign against a deployed app or feature — design-review the code first, enumerate edge cases by lifecycle stage, split live-vs-lab, then execute a cheapest-first phase ladder (preflight → read-only API → side-effect-free calls → UI → state writes → guard/abort paths → real external sends → cleanup) with positive-evidence discipline and a state-neutralization protocol. Use after shipping a feature, before launch, or whenever the user asks to "live test everything" / "make sure it's perfect" / "catch all edge cases". Battle-tested on a multi-day production campaign that found bugs static QA and 100+ unit tests missed.
---

Run a production-grade live-test campaign that finds the bugs only reality can surface: real DB row shapes, vendor API behavior, webhook routing, Redis counters, cache staleness, race timing, and operator-facing UX drift. This is NOT a smoke test — it is a designed campaign with an evidence standard.

## When to invoke

- After shipping a feature (or a batch of changes) that touches external boundaries: sends, webhooks, queues, billing, vendor APIs
- Before launch / "must be perfect" requests
- When the user says "live test everything", "cover all edge cases", "master test"
- After a refactor of a previously-live-proven flow (regression campaign, smaller scope)

Skip for: pure-UI copy tweaks (use the `live-test` agent alone), logic fully provable by unit tests, changes with no deployed surface.

## Phase -1 — Design the campaign (do NOT skip; this is where half the bugs are found)

Dispatch TWO agents in parallel before touching anything:

1. **`brainstorm` agent — edge-case storm + code design review.** Give it: what the feature does, what changed recently (recency-ranked — last-48h changes are P0), what was already live-proven, and the hard environment constraints. Ask for: (a) an edge-case taxonomy organized BY LIFECYCLE STAGE (config → ingest/seed → execute → post-execute → cancel → kill/abort → observability), applying inversion ("what would a hostile/unlucky sequence do?"), the scale game (0 items vs many; first step vs last step), and the codebase's OWN recurring bug classes (check project memory: phantom columns, local-vs-external IDs, stale closures, fail-open vs fail-closed); (b) a live-vs-lab split; (c) how the TEST PLAN ITSELF could lie (see catalog below); (d) a cheapest-first sequencing with cleanup steps. **The brainstorm reads code — expect it to find real bugs before a single test runs.** When it does, FIX AND SHIP THE BUG FIRST so the campaign verifies the fix, not pins the bug.
2. **`Explore` agent — deployed-surface inventory.** Exact endpoints (method + path + auth + error codes), env flags (+ fail-open/closed semantics + current values in task defs), every structured log event name on the paths under test (with metadata keys), DB tables/columns/status values, cron/sweeper cadences, UI data-testids, and where config saves. The plan must be grounded in what is DEPLOYED, not what you remember.

Then write the plan to a file (`.claude/PLAN-<feature>-livetest.md`): phases, per-phase checklists, evidence requirements, the neutralization protocol, and a "deliberately skipped (lab-pinned)" section. Update it as phases complete — it must survive compaction.

**Live-vs-lab discipline:** unit/seam-pinned pure logic (validators, predicates, math, string transforms, retry state machines) gets ZERO live budget. Live budget goes exclusively to seams only reality proves: real data shapes (e.g. identifiers living in side tables with NULL legacy columns), vendor calls, cross-service wiring, caches, counters, and anything that changed in the last 48h.

## The "how a test can lie" catalog (check EVERY item against your plan)

1. **State poisoning** — residue from prior tests (completed rows, cooldown stamps, lifetime caps, opt-out flags) silently blocks the paths you think you're testing. Audit + neutralize FIRST; snapshot every mutable column you'll touch.
2. **Cleanup that arms guards** — the reason/status you write during cleanup can itself trigger business rules (e.g. a cancel reason that arms a 30-day re-engagement block). Use a dedicated inert marker (`test_cleanup`) and strip side-band keys (stamps, timestamps) explicitly.
3. **Fail-open components lie by succeeding** — rate limiters and budget caps that fail open on infra trouble make "no send happened" meaningless. Only POSITIVE evidence counts: capture the 429 body, the cap-hit log with count/ceiling — never the absence of an effect.
4. **Cache/deploy skew** — verify the deployed artifact actually carries your change before testing it (grep the served JS bundle for a new string; confirm the ECS deploy of the exact SHA went green). Frontend and backend deploy on different pipelines.
5. **Jitter and windows** — scheduled times carry jitter and clamp into send windows/timezones. Assert ranges and window membership, never exact timestamps. Run time-windowed sends INSIDE the window or every result is a reschedule masquerading as a failure.
6. **Activity clocks reset themselves** — your own test actions (outbound sends, syncs) bump `last_activity`-style columns and de-qualify the entity you just qualified. Re-backdate between cycles, inside any floor (e.g. >threshold but <30-day floor).
7. **One shared test identity** — serialize scenarios on it; a second identity with the same email/phone risks vendor-side auto-merge. Snapshot/restore its columns between phases.
8. **Verify via the system of record** — vendor thread/conversation API, DB rows, structured logs. Inbox lag and UI refresh lag produce false failures.
9. **Inbound routing ≠ outbound creds** — a tenant can send via copied vendor creds while the vendor location forwards inbound webhooks to a DIFFERENT tenant. Trace where inbound actually lands before designing reply-driven tests.
10. **Draft/param contracts** — API draft/override params often expect the WHOLE config object, not a fragment; a wrong shape degrades silently (count:0, configured:false) instead of erroring. Prove the contract with a positive case before trusting negatives.

## The phase ladder (cheapest-first, destructive-last)

**Phase 0 — Preflight (free).** Deploys green for the exact SHAs under test. Env flags + cron/sweeper heartbeats in logs. Served bundle carries the change. Residue audit + neutralization. State snapshot of the test identity. Confirm prerequisites (e.g. ≥1 outbound message exists if eligibility needs it).

**Phase 1 — Read-only API (free).** Every typed error path: malformed inputs, missing auth (401/403), cross-tenant smuggling attempts, oversized payloads, invalid enums. Count endpoints used as free predicate oracles. Admin round-trips (suspend/resume + audit rows). RBAC spot checks.

**Phase 2 — Side-effect-free real calls (cents).** Preview/dry-run endpoints against real vendor APIs with real keys: happy path on the RISKIEST model/provider class (e.g. thinking models for truncation), grounded vs ungrounded, forced policy violations (deny-lists → flags), rate-limit burst to the positive 429. Capture the structured events with token counts.

**Phase 3 — UI (free).** Dispatch the `live-test` agent against the PROD dashboard (SSO-hash login recipe in project memory). Full interaction script with data-testids, console + network watch (zero errors tolerated), responsive at 375/768/1440, and END STATE = the exact saved config later phases reuse. Verify persistence by reloading AND by reading the saved row via API/SQL — UI echo is not proof.

**Phase 4 — State-machine writes (free).** Trigger the ingestion/seeding machinery and verify: exactly-once (second tick = 0 new), payload contents (the config you saved actually flows into rows), jitter/window clamps, exclusions (mock data, ineligible entities), counters that add up (candidates = seeded + suppressed\_\*).

**Phase 5 — Guard/abort paths (cheap, zero external sends).** Force each guard to trip: compliance flags set between seed and fire, policy blocks, feature/channel toggled off. For each: the exact skip/log event AND the row's terminal state. **Lifecycle honesty is the #1 bug class here:** a blocked/skipped/aborted item must never end in a state that reads as "delivered/completed" (consuming caps, stamping cooldowns) NOR linger as a zombie `pending` (suppressing future work, showing phantom UI chips). Run destructive guard tests LAST within the phase; re-seed after.

**Phase 6 — Real external sends (the only spend phase; budget ≤5).** Order by irreversibility — e.g. vendor thread history can't be deleted, so test the no-history branch before creating history. Per send verify: delivery via the vendor's own API, the full event chain, model/config overrides actually applied, cost/tokens vs the UI's estimate, and the row lifecycle (intermediate steps complete WITHOUT terminal stamps; final step stamps). Budget/cap tests: hourly mid-phase, daily LAST (prod counters persist for the UTC day; recover by raising the config ceiling, which reads fresh at fire).

**Phase 7 — Human-only steps (batched, at the END).** Anything needing a real human reply/click gets ONE `checkpoint:human-action` after everything else is done — never block mid-campaign. Pre-position the state it needs (e.g. leave a pending row as the cancel target). If wiring makes it unreachable (inbound routes elsewhere), say so and rely on prior human-proven evidence + unit pins — disclosed, not silently skipped.

**Phase 8 — Cleanup + evidence report.** Restore config + snapshot columns. Neutralize rows with the inert marker. Full log sweep across ALL services for `*_failed` events in the campaign window — the ONLY failures present must be your deliberate negative tests. Final report: per-phase PASS/FAIL with evidence, findings ranked (fix-now vs note), deferred items WITH REASONS, and what state was left behind.

## Execution machinery (the recipes)

- **Force-fire scheduled work:** backdate `due_at` AND clear the scheduler/dedup flag in the same UPDATE (`context - 'scheduler'` or equivalent) — versioned job IDs need a fresh due time to re-enqueue. A "stranded" row is re-fireable the same way.
- **Watchers, not sleeps:** background `until`-loop greps on CloudWatch/log filters keyed to the specific row/trace ID, with `run_in_background: true`. The notification resumes you. Filter for BOTH the success and failure event names — silence must not look like success.
- **Fix-as-you-go:** a bug found mid-campaign gets fixed → tested → shipped → deployed → and the NEXT phase verifies the fix live. Never let the campaign pin buggy behavior as "expected".
- **Admin-only identities** (per `~/.claude/rules/testing-safety.md`): the designated admin email/phone, never fabricated third-party contacts.
- **Evidence per claim** (per `~/.claude/rules/gates.md`): a "delivered" claim = vendor API record + event log + DB row state, in the same turn. A "blocked" claim = the skip event + the row's terminal state + the alert/operator surface.
- **Subagent fan-out:** brainstorm + Explore in parallel for design; `live-test` for UI; `qa-agent` on any code you ship mid-campaign. Keep the main thread as orchestrator.
- **Track phases** with TaskCreate/TaskUpdate; tick the plan file as you go.

## Severity + reporting standard

- P0 = changed in the last 48h on a compliance/cost/external boundary. P1 = recent guard/cap logic. P2 = spot re-verification of previously-proven flows (one pass, no matrix).
- Findings ship in the report with: what breaks, root cause file:line, reproduction, and a recommendation. Distinguish FIXED-AND-VERIFIED / fix-recommended / design-note / doc-gap.
- The report's last section is always "what's left behind": config state, surviving rows, anything the user must do (the human checkpoint), and deferred tests with reasons.

## Anti-patterns

- ❌ Starting to test without the brainstorm design review (it found a real cap-consuming lifecycle bug from code alone, pre-test)
- ❌ Spending live budget on unit-pinned logic ("predicate combinatorics live" = waste)
- ❌ Trusting "nothing happened" from a fail-open component as a pass
- ❌ Sleeping fixed durations instead of arming log watchers
- ❌ Cleanup with semantically-loaded statuses/reasons that arm business rules
- ❌ Two test identities sharing an email/phone (vendor auto-merge)
- ❌ Asking the user for human steps mid-campaign instead of one batched end checkpoint
- ❌ Declaring done without the all-services failure-event sweep
