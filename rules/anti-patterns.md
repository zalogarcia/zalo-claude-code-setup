# Universal Anti-Patterns

Behavioral rules that apply regardless of project. Drawn from both gsd-build/get-shit-done universal anti-patterns and obra/superpowers writing-plans "No Placeholders" list.

## Context Budget Rules

1. **Never read agent definition files** (`~/.claude/agents/*.md`) — `subagent_type` auto-loads them.
2. **Never inline large files into subagent prompts** — tell agents to read files from disk instead.
3. **Read depth scales with context** — see `~/.claude/rules/context-budget.md` for tier behavior.
4. **Delegate heavy work to subagents** — the orchestrator routes; it does not build, analyze, research, or verify in main context.
5. **Proactive pause warning** — when context budget is heavy, surface it to the user before continuing.

## File Reading Rules

6. Do not re-read full file contents when frontmatter or summary is sufficient.
7. Do not read files outside the current task's scope to "understand the system" — that's a subagent's job.

## Subagent Rules

8. Use the most appropriate subagent for the task. Do not fall back to `general-purpose` when a specific agent fits.
9. Do not re-litigate decisions already locked in by the user or in a prior plan.
10. Do not dispatch multiple **implementation** subagents in parallel on the same files — conflicts. Multiple research/review agents in parallel is fine.

## Questioning Anti-Patterns

(See `~/.claude/rules/questioning.md` for the dream-extraction philosophy.)

11. Do not walk through checklists — use progressive depth.
12. Do not use corporate speak — avoid jargon like "stakeholder alignment", "synergize".
13. Do not apply premature constraints.
14. Never ask about the user's technical experience. Claude builds.

## Behavioral Rules

15. Do not create artifacts the user did not approve.
16. Do not modify files outside the task's stated scope.
17. Do not suggest multiple next actions without clear priority.
18. Do not use `git add .` or `git add -A` — stage specific files only. (See `~/.claude/rules/git-safety.md`.)
19. Do not include sensitive information (API keys, passwords, tokens) in commits or planning docs.

## No-Placeholders List (for plans, specs, design docs)

Plan/spec documents must not contain:

- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may read tasks out of order)
- Steps that describe **what** to do without showing **how**
- References to types, functions, or methods not defined elsewhere in the doc

If you catch yourself writing one of these, replace it with the actual content.

## Verification Anti-Patterns

(See `~/.claude/rules/gates.md` Part 2 for the full Verification Gate Function.)

20. Do not say "should work", "probably passes", "looks good" before running the verification command in this turn.
21. Do not commit, push, or open a PR without running the relevant tests in this turn.
22. Do not trust subagent success reports without checking the diff yourself.
