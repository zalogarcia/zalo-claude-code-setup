---
description: 'Goal-driven autonomous loop: write .claude/GOAL.md (goal + acceptance criteria), then implement → verify each criterion with fresh evidence (live-test when UI/live behavior is in scope) → update status → repeat until all criteria pass or blocked. Use when the user states a goal with autonomy + completion phrasing: "until perfect", "do it all yourself", "fix without me", "live test until all is perfect", "brainstorm and fix without me".'
---

# /goal — Drive a Goal to Verified-Done

In-session, goal-driven convergence loop. Take the user's goal, pin it to disk as `.claude/GOAL.md` with concrete acceptance criteria, then cycle **understand → implement → verify → update status** until every criterion passes with fresh evidence or the run is blocked. The lighter sibling of `/autopilot`: no worktree, no work-unit decomposition — the main thread orchestrates (and may implement directly) in the current session. Prefer `/autopilot` for large decomposable projects; prefer `/goal` for "make X true and prove it" runs.

## Authoritative Rules

@~/.claude/rules/agent-contracts.md
@~/.claude/rules/gates.md
@~/.claude/rules/verification-patterns.md
@~/.claude/rules/testing-safety.md
@~/.claude/rules/problem-solving.md
@~/.claude/rules/checkpoints.md

## Constants

- `MAX_CYCLES = 6` — after 6 full cycles without all criteria passing, escalate (do not silently keep looping).
- `MAX_FIXES_PER_CRITERION = 3` — 3 failed fix attempts on the same criterion triggers the 3+ Fixes Rule (architecture gate).
- Goal file: `.claude/GOAL.md` in the project. **Single source of truth for progress.**

## Phase 0: Establish the Goal (write `.claude/GOAL.md`)

`$ARGUMENTS` is the goal. Record it **verbatim** — do not paraphrase it away.

1. **Derive acceptance criteria** from the goal text. Each criterion must be:
   - **Concrete and checkable** — "follow-up fires as ONE message in the live conversation" not "follow-ups work"
   - **Atomic** — one criterion per line
   - **Outcome-focused** — what must be observably true, not how to build it
   - **Paired with its verification method** — the command, query, or live-test observation that will prove it
   - If the goal says "fix the bugs we found", enumerate each known bug as its own criterion. If it says "live test until perfect", add an explicit criterion: "live-test pass over the affected flow(s) with zero new issues."
2. **Clarify only if genuinely ambiguous.** ONE `AskUserQuestion` round maximum (2-4 concrete interpretations, per `~/.claude/rules/questioning.md`). If the goal contains autonomy phrasing ("do it all yourself", "fix without me", "until perfect"), do NOT ask — derive best-effort criteria and proceed; the user opted out of back-and-forth.
3. **Capture run context:** active branch (`git branch --show-current`), test identity pointer (`.claude/test-identities.md` if present — check with a Glob/ls, don't assume).
4. **Write `.claude/GOAL.md`** (Write the whole file; this and every later update — never string-Edit a status file):

```markdown
# GOAL — <one-line summary>

**Invoked:** <ISO-8601 timestamp>
**Branch:** <active branch>
**Test identity:** .claude/test-identities.md (or: "none configured — live testing gated per ~/.claude/rules/testing-safety.md")

## Goal (verbatim)

> <$ARGUMENTS, unedited>

## Acceptance Criteria

- [ ] AC-1: <criterion> — verify via: <command / query / live-test observation>
- [ ] AC-2: ...

## Status Log

### Cycle 0 — <timestamp>

- GOAL.md created, N criteria derived. Starting cycle 1.
```

## The Loop (Revision Gate, cap `MAX_CYCLES`)

Each cycle has four steps. Never skip step 3 or 4.

### Step 1: Understand

Only as needed — skip when the failing criterion is already diagnosed.

- Broad "where does this live / how is this wired" questions → dispatch `Explore`.
- A defect with a symptom → dispatch `bug-fix` (4-phase debugging; route its confidence marker per `/bug` Step 2.5 semantics: only a `## ROOT CAUSE FOUND — CONFIDENCE 10/10` return is fix-ready).
- Live/prod evidence first when infra is involved: logs before hypotheses (`~/.claude/CLAUDE.md` Debugging Protocol).

### Step 2: Implement

- Small, well-scoped edits → main thread directly.
- Larger or UI-heavy units → dispatch the fitting agent (`frontend-specialist`, `general-purpose`), and paste the **Mandatory Dispatch Boilerplate** from `~/.claude/rules/agent-contracts.md` verbatim into every implementation dispatch. Do not check the diff back in on trust — verify the agent's changes yourself (diff + marker).
- Minimal changes only. The goal defines the scope; no "while we're here" work.

### Step 3: Verify — every criterion, fresh evidence

Apply the Verification Gate Function (`~/.claude/rules/gates.md` Part 2) to **EACH** acceptance criterion, every cycle:

1. State the verification command/observation for the criterion.
2. Run it **in this turn** (fresh — prior cycles' evidence is stale).
3. Capture actual output.
4. Grade PASS/FAIL against the criterion.

Rules for this step:

- **UI or live behavior in the criteria** → dispatch the `live-test` agent for a targeted flow check, or invoke the `live-test-campaign` skill when the goal demands breadth ("everything", "until perfect", pre-launch). Live testing uses ONLY the designated admin/test identity from `.claude/test-identities.md` (per `~/.claude/rules/testing-safety.md`) — never fabricated users. If no admin identity is configured, mark live criteria BLOCKED and escalate; do not invent one.
- **Code changed this cycle** → run typecheck/build (`typecheck-and-build` skill) before grading criteria.
- **Cycle touched 3+ files** → run `/qa-loop` before grading criteria (satisfies `~/.claude/rules/anti-patterns.md` rule 23; /goal's criterion-grading alone is not a bug audit).
- Existence ≠ implementation — apply `~/.claude/rules/verification-patterns.md` stub-detect + wiring checks to anything an agent claims done.

### Step 4: Update `.claude/GOAL.md`

After every cycle, rewrite GOAL.md (whole-file Write):

- Tick criteria that passed (`- [x]`), leave failures unticked.
- Append a `### Cycle N — <timestamp>` entry: what changed (files), per-criterion PASS/FAIL with one-line evidence each, fix-attempt count for any still-failing criterion, next action.

### Route

- **All criteria PASS** → exit loop, report (below).
- **Any criterion FAIL and cycles < MAX_CYCLES** → next cycle, targeting the failures.
- **Same criterion failed `MAX_FIXES_PER_CRITERION` fixes** → STOP fixing. Apply the 3+ Fixes Rule (`~/.claude/rules/problem-solving.md`): question the architecture, not the fix — dispatch `brainstorm` to challenge where the bug is assumed to live, then either resume with the new theory or escalate.
- **`MAX_CYCLES` reached, or genuinely blocked** (missing access, external vendor, no admin identity) → emit a `checkpoint:decision` / `checkpoint:human-action` per `~/.claude/rules/checkpoints.md` with: passing vs failing criteria, evidence so far, and concrete options. Stop and wait.

## Compaction Survival

- `.claude/GOAL.md` is the single source of truth for progress. **After ANY compaction: re-read `.claude/GOAL.md` first, then `.claude/HANDOFF.md`** (written by the PreCompact hook) before touching anything.
- Never compact mid-cycle — finish Step 3 + Step 4 (status written to disk), then compact.

## Hard Rules (non-negotiable)

1. **No `git push` — ever — without the user's explicit permission** (`~/.claude/rules/git-safety.md`). Commit freely with specific-file staging (`commit-with-heredoc` skill); report `PUSH_PENDING: <branch> <N> commits` instead of pushing.
2. **Live testing only with the designated admin/test account** — `.claude/test-identities.md` pointer, per `~/.claude/rules/testing-safety.md`. No generated emails, no real-user impersonation.
3. **No criterion is marked PASS without fresh command/observation evidence captured in the same turn.** "Should work" = the gate failed.
4. **3 failed fixes on one criterion → architecture gate**, not a 4th fix.
5. **6 cycles → escalation checkpoint**, not a 7th cycle.

## Report (on exit — success or escalation)

- **Goal:** verbatim one-liner
- **Criteria:** table — each AC, PASS/FAIL, evidence (command + key output line)
- **Cycles run:** N of MAX_CYCLES
- **Files changed:** list (from `git diff --stat` / commits made)
- **Push status:** `PUSH_PENDING: <branch> <N> commits` or "nothing to push"
- **Deferred/blocked:** anything not achieved, with the blocker

## Anti-Patterns (will not do)

- Mark a criterion PASS on stale or absent evidence.
- Push to any remote, or ask the user to run commands Claude can run.
- Fabricate test users or test against live systems with a non-admin identity.
- Keep fixing past the 3+ Fixes Rule or looping past MAX_CYCLES.
- Expand scope beyond the goal text ("while we're here" work).
- String-Edit GOAL.md — status files get whole-file Writes.
- Run more than one clarifying round — after Phase 0, the loop is autonomous until done or blocked.
