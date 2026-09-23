# Agent Contracts

Completion markers and return contract for `~/.claude/agents/`. Skills/orchestrators detect agent completion by regex-matching these H2 markers in the agent's final output.

## Marker Registry

| Agent                 | Markers                                                                                                                |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `frontend-specialist` | `## IMPLEMENTATION COMPLETE` / `## IMPLEMENTATION DONE_WITH_CONCERNS` / `## BLOCKED`                                   |
| `qa-agent`            | `## VERIFICATION PASSED` / `## ISSUES FOUND` / `## BLOCKED` (verdict mapping below)                                    |
| `safe-planner`        | `## PLAN READY` / `## NEEDS DECISION` / `## BLOCKED`                                                                   |
| `brainstorm`          | `## EXPLORATION COMPLETE`                                                                                              |
| `live-test`           | `## UI VERIFIED` / `## UI ISSUES FOUND` / `## BLOCKED`                                                                 |
| `bug-fix`             | `## ROOT CAUSE FOUND — CONFIDENCE 10/10` / `## INVESTIGATION INCOMPLETE — CONFIDENCE <N>/10` (N ∈ 1..9) / `## BLOCKED` |
| `outcomes-grader`     | `## OUTCOMES PASSED` / `## OUTCOMES UNMET` / `## BLOCKED`                                                              |

### qa-agent verdict mapping

`~/.claude/agents/qa-agent.md` gives the agent a THREE value verdict (PASS / PASS WITH CONCERNS / FAIL) and the registry gives it two non blocked markers. The marker is therefore chosen by the **verdict**, not by the finding count:

| `Assessment:` in the body | Marker to emit           | Orchestrator route         |
| ------------------------- | ------------------------ | -------------------------- |
| `PASS`                    | `## VERIFICATION PASSED` | clean, proceed             |
| `PASS WITH CONCERNS`      | `## ISSUES FOUND`        | the concerns branch, below |
| `FAIL`                    | `## ISSUES FOUND`        | the concerns branch, below |

There is deliberately **no third marker**. `## VERIFICATION PASSED WITH CONCERNS` contains `## VERIFICATION PASSED` as a prefix, so any consumer not updated for it, and any regex anchored with `\b`, reads it as a clean pass: a new marker's failure mode would be silent and identical to the bug it was meant to fix. `## ISSUES FOUND` is already handled by every consumer, and when a consumer is out of date its failure mode is conservative (a concerned pass gets the findings branch, which is more scrutiny, never less).

**Two mandated fields.** A pass class marker (`## VERIFICATION PASSED`) requires BOTH of these in the body:

- an `Assessment:` line carrying exactly one of `PASS` / `PASS WITH CONCERNS` / `FAIL`, and
- an evidence line carrying a command **and its result**: `**Commands run:**` (qa-agent's own field name for the template's Verification field) or `**Verification:**`. A value of "none" or "n/a" does not satisfy it.

A return missing either is treated as **not passing**. Route it as `## ISSUES FOUND` with the concern "contract fields missing", or re dispatch that one agent ONCE with the field names quoted.

**Status takes precedence over the marker too.** A pass marker whose `**Status:**` says `DONE_WITH_CONCERNS` routes as `## ISSUES FOUND` (above). One whose Status says `NEEDS_CONTEXT` or `BLOCKED` is also not a pass, but it goes to THAT status's own branch in the Status Code Body Protocol below (supply the context and re dispatch; Tiered Decision Protocol), not to the concerns branch.

**The consequence.** A check with no defined consequence is a check nobody fixes. On a concerned verdict the orchestrator does exactly ONE of these, chosen by reading the concern, and does **not** re dispatch the same audit for the same concern (the verdict is already in):

1. The concern names a **finding**: fix CRITICAL and HIGH, defer MEDIUM and LOW. This is what the `## ISSUES FOUND` branch already does.
2. The concern names a **check that did not run** (a mock stood in for the real system, a coverage claim with no measured denominator, a surface not live verified): run that one check now. If it cannot be run, cap the run's terminal claim at the `CODE-COMPLETE, NOT LIVE-VERIFIED` status in `~/.claude/rules/gates.md` Part 2 and list the unproven surface FIRST in Remaining Issues.
3. The concern is an **observation** only (per DONE_WITH_CONCERNS below): say it to the user in the report and proceed.

**Mechanism, not just text.** `~/.claude/hooks/qa-verdict-guard.py` (PostToolUse on `Agent|Task`) parses the returned body and injects this routing when a `## VERIFICATION PASSED` return contradicts its own verdict line or is missing a mandated field. Contract text alone decays; the hook does not. Tests: `python3 ~/.claude/hooks/qa-verdict-guard.test.py`. The hook nudges, it does not block: the audit already ran, and blocking a returned verdict throws it away.

**Basis:** before this mapping existed, a large share of `## VERIFICATION PASSED` returns carried `PASS WITH CONCERNS`, `DONE_WITH_CONCERNS` or even `FAIL` in their body, and every one of them routed as a clean pass.

## Marker Rules

1. Markers must appear as H2 headings (`## `) at the start of a line in the agent's **final** output.
2. Use ALL-CAPS to maximize regex reliability.
3. Exactly one terminal marker per dispatch — agents that need multiple states pick the most recent applicable one.
4. The marker line stands alone; details follow underneath.
5. Some agents embed structured data in the marker line (e.g., `bug-fix` embeds confidence as `CONFIDENCE 10/10`). Orchestrators MUST parse the marker line via regex, not parse body text for the same data — single source of truth. Canonical separator for embedded data is the em-dash (—), not ASCII hyphen.

## Status Code Body Protocol

After the H2 marker, the agent's body must signal one of four states (adapted from obra/superpowers `subagent-driven-development`):

**DONE** — task complete, all acceptance criteria met. Proceed.

**DONE_WITH_CONCERNS** — work complete but agent flags doubts.

- If concerns are about correctness or scope → orchestrator addresses before proceeding.
- If concerns are observations (e.g., "this file is getting large") → note and proceed.

**NEEDS_CONTEXT** — agent needs information that wasn't provided. Orchestrator supplies it and re-dispatches.

**BLOCKED** — agent cannot complete. Orchestrator assesses:

1. Context problem → provide more context, re-dispatch with same model.
2. Reasoning gap → re-dispatch with more capable model.
3. Task too large → split into smaller pieces.
4. Plan is wrong → escalate to human (use `~/.claude/rules/checkpoints.md` checkpoint:decision).

**Never** ignore an escalation. Never re-dispatch the same model without changing context. If the agent said it's stuck, something must change.

## Standard Return Template

```markdown
## <MARKER>

**Status:** DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED

**Summary:** [1-2 sentences]

**Files changed:** [list]

**Verification:** [what was tested + result]

**Concerns / Blockers:** [if any]
```

`qa-agent` emits the `**Verification:**` field under its own name, `**Commands run:**` (see its Output format). Either name satisfies the field; consumers and `qa-verdict-guard.py` accept both.

## Mandatory Dispatch Boilerplate

Orchestrators MUST include this block verbatim in every implementation-agent prompt (any dispatch that will Edit/Write files). No paraphrasing — each line prevents a failure mode observed in real runs.

```text
## File-handling rules (non-negotiable)
- Read every file BEFORE Edit/Write — the harness rejects edits to unread files.
- Glob before Read; never construct paths from memory.
- After any compaction or "file modified" notice, re-Read the file before editing.
- For plan/status files, Write the whole file — do not string-Edit them.
- ToolSearch/deferred tools are unavailable in subagent contexts — use only the tools you were granted.
- Consult docs/CODEMAP.md (if present) before grepping; prefer one targeted Grep/Glob over repeated broad greps.
- git is READ-ONLY for you — never commit, stage, stash, reset, checkout, or clean; staging and commits are the orchestrator's job. (Hook-enforced: destructive git ops are blocked; one subagent's mass revert once wiped 11 sibling agents' work.)
```

## Why This Matters

Without contracts, subagent returns are prose blobs the orchestrator must re-read entirely. Contracts let:

- The main thread regex-detect terminal state and route accordingly.
- Multi-stage pipelines (planner → implementer → reviewer) chain reliably.
- The user see at a glance what the agent actually decided.

Treat the marker as a public commitment. If the agent emits `## VERIFICATION PASSED`, the verification was actually run.
