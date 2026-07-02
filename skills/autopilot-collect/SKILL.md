---
name: autopilot-collect
description: List all /autopilot worktrees + branches in the current repo with their terminal_state, commits ahead of a base, files touched, and task summary. Use when the user asks "which autopilots finished", "check autopilots", "all autopilots finished", "autopilots completed", "show pending autopilot runs", "what's left to merge", or as the discovery step inside /autopilot-merge. Returns a TSV table — parse it; don't paste it raw into the conversation.
---

Discover all `autopilot/*` worktrees in the current repo with state, by reading `git worktree list --porcelain` + each worktree's `.autopilot/state.json`. Deterministic shell — no agent dispatch, no decision-making.

## When to invoke

- Inside `/autopilot-merge` as the discovery step
- When the user asks "which autopilot runs are pending?" / "what finished?" / "list my autopilots"
- Before deciding whether to start a new `/autopilot` (check there isn't a stale one to clean up)
- As a sanity check after a long session of parallel autopilots

Skip for: single-autopilot workflows, fresh repos with no autopilot branches.

## Invocation

```bash
~/.claude/skills/autopilot-collect/collect.sh [BASE_BRANCH]
```

`BASE_BRANCH` defaults to `dev` if it exists, else `main`. The "commits ahead" column is measured relative to this base.

## Output shape

Tab-separated table with header. Example:

```
PATH	BRANCH	TERMINAL_STATE	COMMITS_AHEAD_OF_dev	FILES_TOUCHED	TASK_SUMMARY
/Users/zalo/.../myapp-autopilot-20260518-153313-6334	autopilot/20260518-153313-6334	complete	7	22	Build conversations tab in admin panel
/Users/zalo/.../myapp-autopilot-20260518-164212-7891	autopilot/20260518-164212-7891	complete_with_issues	4	11	Add retry to webhook handler
/Users/zalo/.../myapp-autopilot-20260518-171530-8234	autopilot/20260518-171530-8234	running	2	5	Migrate to Postgres 16
```

### Terminal-state legend

- `complete` — clean Phase 5 exit, ready to merge
- `complete_with_issues` — Phase 5 exit with deferred issues; mergeable but review the deferred_issues.md
- `aborted` — exited early (pre-flight failure, context exhaustion); usually NOT mergeable, inspect first
- `aborted_api_outage` — API circuit breaker tripped; partial work, may be mergeable
- `running` — `state.json.terminal_state` is null. Usually means still active, but could also be a crashed run that died before writing terminal_state. Do NOT merge; inspect (check `.autopilot/lock` mtime + PID liveness) before deciding to resume vs. discard
- `missing-state` — no `.autopilot/state.json` at all; corrupt or pre-protocol run, inspect manually

## Parsing in Claude

When invoked from a command (e.g. `/autopilot-merge`), capture stdout into a variable and parse line-by-line. Do NOT paste the raw TSV into user-facing output without formatting it into a readable table or filtered list.

```bash
TSV=$(~/.claude/skills/autopilot-collect/collect.sh)
# Skip header, filter to mergeable states
echo "$TSV" | tail -n +2 | awk -F'\t' '$3 == "complete" || $3 == "complete_with_issues"'
```

## Anti-patterns

- Pasting the full TSV into the conversation — format it as a readable table or filter to relevant rows first
- Using `git branch --list autopilot/*` instead — that finds the BRANCH but not the worktree path; you'd then have to re-derive the path, which is brittle. `git worktree list --porcelain` is the source of truth
- Trusting the branch list as "mergeable" without reading state.json — a `running` autopilot has a branch but is NOT mergeable
- Hand-parsing `git worktree list` (the human-readable form) — always use `--porcelain` for stable parsing

## Pair with

- `/autopilot-merge` — the orchestrator that uses this skill for discovery and then merges sequentially
- `/autopilot resume` — if you find a worktree in `running` state and want to continue it, `cd` there and run resume
