# Read this first, Codex

Everything below this section is Zalo's Claude Code operating manual, copied
verbatim. It is the source of truth for HOW to work here: verification gates,
git safety, subagent policy, project map, the lot. The principles all transfer.
The vocabulary does not, because it names Claude Code tools that do not exist in
Codex.

This section is the adapter. Read it, then read the bodies with these
substitutions already in your head.

## Vocabulary translation

| What the manual says | What it means for you, in Codex |
| --- | --- |
| "dispatch the `X` agent", "use the Agent tool with `subagent_type: X`" | Call `spawn_agent` with `agent_type = "X"`. The agents live in `~/.codex/agents/*.toml` and carry the same instructions. |
| `model: fable` | The custom agent already pins the mapped model. If you are choosing by hand, that tier is the strongest GPT-5.6 variant at `xhigh` reasoning. |
| `model: opus` | The mapped high-volume tier: GPT-5.5 at `high` reasoning. |
| "the Bash tool" | Your shell tool. Same thing. |
| "Edit", "Write", "MultiEdit" | `apply_patch`. One tool covers all three. |
| "MCP tools are deferred, use `ToolSearch` first" | Not needed. Your MCP tools are preloaded and callable directly as `mcp__<server>__<tool>`. Ignore every instruction to search for a tool schema first. |
| `/skill-name` (a slash command) | `$skill-name`. The 15 Claude slash commands are projected into skills under `~/.agents/skills/`, so `/autopilot` is `$autopilot`. |
| `@~/.claude/rules/x.md` on its own line | An include directive. Read that file with your file tools before proceeding. It is not decoration; the rule text is load-bearing. |
| `AskUserQuestion` | `request_user_input`. |
| `run_in_background: true` | Not available. Run it in the foreground, or hand it to `~/dev/claude-telegram-bridge/bg.mjs`. |
| "hook-enforced", "`~/.claude/hooks/*` blocks this" | Those hooks are mirrored into `~/.codex/hooks.json` and really do fire on your shell commands and your `apply_patch` calls. A blocked call is a blocked call. |
| "memory", "recalled memories" | Not auto-injected here. At session start, read `~/.claude/projects/-Users-zalo-dev/memory/MEMORY.md` (the index) and open the linked file when a task touches that project. |
| `.claude/CLAUDE.md` in a repo | Read it yourself when you start work in that repo. Codex only auto-loads `AGENTS.md` files, and most repos here do not have one yet. |
| "Skill tool", "invoke the `X` skill" | Your skills system. Same names, same `SKILL.md` bodies. |

## Delegation is explicit here

Claude Code auto-routes work to subagents by description. **Codex never does.**
Nothing spawns unless you call `spawn_agent`. So wherever the manual says a step
runs in a subagent (planning via `safe-planner`, QA via `qa-agent`, browser
verification via `live-test`, thinking via `brainstorm`), that is an instruction
to YOU to make the `spawn_agent` call. Do it. The whole quality model here is
"the model that verifies is not the model that authored", and it collapses to
nothing if you just do the work inline and call it verified.

Spawnable agents: `brainstorm`, `bug-fix`, `frontend-specialist`,
`image-craft-expert`, `live-test`, `outcomes-grader`, `qa-agent`,
`safe-planner`.

## One source of truth

`~/.codex/AGENTS.md` is GENERATED. Never edit it. Edits there are silently
destroyed on the next sync.

When you learn something worth keeping (the Self-Learning Protocol below), write
it to the SOURCE:

- Global lesson, or a global rule change: `~/.claude/CLAUDE.md` (its Learned
  Mistakes section is at the bottom).
- Repo-specific lesson: that repo's `.claude/CLAUDE.md` or `.claude/rules/*.md`.
- Codex-only translation problem, i.e. something in this adapter is wrong or
  missing: `~/.claude/codex/AGENTS.delta.md`, which is this section.

Then run:

```
python3 ~/.claude/scripts/codex-sync.py all
```

That regenerates `~/.codex/AGENTS.md`, the skill symlinks, `~/.codex/hooks.json`,
the agent TOMLs, and the MCP block in `~/.codex/config.toml`. If it tells you
`hooks.json` changed, tell Zalo he needs to re-trust it once with `/hooks` in an
interactive Codex session; hook trust is bound to the file hash, so a changed
hooks file is an untrusted hooks file.

A SessionStart hook runs `codex-sync.py all --if-stale --quiet` for you, so
normal drift (someone edited `~/.claude/CLAUDE.md` from a Claude session) heals
itself before your first turn. You only need the manual run when you want the
change to take effect inside the session you are already in.

## Things in the manual that do not apply to you

- Instructions about `ToolSearch` and deferred tool schemas. Your tools are all
  loaded.
- Instructions to pass `model: "opus"` at dispatch time. Your agents carry their
  model in their TOML file; there is no per-call model argument.
- References to the Claude usage-limit rotation and the Fable fan-out preflight.
  Those are Claude account mechanics. The budget discipline behind them still
  applies: do not fan out a dozen agents for a task one agent can do.
- `/compact`, `/clear`, `/new` as Claude commands. Codex has its own.

Everything else is live.
