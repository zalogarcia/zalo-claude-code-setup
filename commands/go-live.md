# /go-live — Activation & Live Verification Bridge

Closes the seam between "code complete on a branch" and "verified working in production" — the gap where the 2026-07 GHL post-mortem's 39 live-test defects lived. Consumes the activation runbook an `/autopilot` run wrote (or derives one), executes every step Claude can execute, checkpoints the steps only a human can do, then live-verifies with the traffic harness + live-test campaign so the user's first touch is UX judgment, not bug discovery.

## Authoritative Rules

@~/.claude/rules/gates.md
@~/.claude/rules/checkpoints.md
@~/.claude/rules/database-safety.md
@~/.claude/rules/testing-safety.md

## When to invoke

- After an `/autopilot` run ends `CODE-COMPLETE — NOT LIVE-VERIFIED` (its report names this command)
- "take it live", "activate it", "let's go to production" for a built-but-unactivated feature
- NOT for routine deploys of already-activated features — that's `ship-to-prod` / the repo's normal deploy flow

## Workflow

### Step 1: Resolve the runbook

1. `.autopilot/activation.md` exists → use it.
2. Else derive one now from: the plan's **Activation path** section (`.autopilot/plan.md` / `.claude/PLAN-*.md`), `.claude/VERIFY.md` (deploy surfaces + proof signals + traffic harness), and a grep for feature gates touching the change set (env flags, per-tenant flags, empty `.env` keys referenced by new code).
3. Neither source exists → STOP and say so; a go-live without an enumerated activation path is exactly the failure this command prevents. Offer to build the runbook from the diff.

The runbook has two parts — keep them separated:

- **Claude-automatable** (ordered): migrations (additive-only, per database-safety; ALWAYS before the code deploy), env/feature flags (global AND per-tenant), deploys (per VERIFY.md proof signal for EACH surface — never a different pipeline's green), harness + smoke commands.
- **Human-action**: vendor-console steps (webhook URLs + exact navigation, OAuth callbacks, API version, campaign/number assignment), credentials to obtain, approvals (App Review, A2P) — each with the verification Claude runs afterward.

### Step 2: Execute the Claude-automatable half

Run in runbook order. Per step: run → capture proof → log. Migrations gate deploys (migrate-before-deploy). Deploy claims use the VERIFY.md proof signal for that surface. If a step needs a secret that doesn't exist yet, move it to the human-action list rather than inventing config.

### Step 3: Human-action checkpoints

Emit ONE `checkpoint:human-action` block (per checkpoints.md) listing the remaining human steps in order, each with its post-step verification. Wait. When the user replies done, RUN each promised verification (probe the webhook endpoint, GET the vendor resource, confirm the flag state) — 2-strike probe rule applies: two failed guesses against a vendor API → ground-truth probe, never a third guess.

### Step 4: Live verification (the gate that makes "done" true)

1. **Traffic harness** (if VERIFY.md names one, or the build created one): run it against the activated stack. Simulated inbound payloads → assert rows, tenant scoping, emitted events, realtime publishes, replies.
2. **Live-test campaign**: invoke the `live-test-campaign` skill scoped to the activated surfaces, admin/test account only (testing-safety).
3. **Real-traffic spot check** where a vendor is involved: one real inbound per channel (user-triggered if it needs their phone/account), verified end-to-end in the UI.

Defects found here: fix → re-run the failed stage → continue (revision-gate, cap 3 per defect; 3 failures on one defect → stop and surface, per the 3+ Fixes Rule).

### Step 5: Report

- Per-surface: ACTIVATED + proof signal | BLOCKED (on what, e.g. vendor approval) | NOT ATTEMPTED (why)
- Coverage with denominators: "N of M runbook steps executed, K human steps verified"
- Remaining irreducibles: vendor approvals pending, UX-taste items for human eyes
- Claim ceiling per gates.md: surfaces without their proof signal are never reported "live".

## Anti-Patterns (will not do)

- Push/deploy without the user having approved going live (invoking /go-live IS that approval for the surfaces in the runbook — but never force-push, never skip migrate-before-deploy)
- Mark a vendor-gated step "done" from the code side without probing the vendor resource
- Substitute the harness for the campaign or vice versa — they catch different classes
- Silent partial activation: every runbook step lands in the report as executed / blocked / not-attempted
