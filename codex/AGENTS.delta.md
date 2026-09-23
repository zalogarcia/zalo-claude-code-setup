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
| `model: fable` | The custom agent already pins GPT-6 Astra (`gpt-6-astra`) at `xhigh` reasoning. |
| `model: opus` | The mapped high-volume tier: GPT-5.5 at `high` reasoning. |
| "the Bash tool" | Your shell tool. Same thing. |
| "Edit", "Write", "MultiEdit" | `apply_patch`. One tool covers all three. |
| "MCP tools are deferred, use `ToolSearch` first" | Not needed, and there is no `ToolSearch` here. Your MCP tools are preloaded and callable directly as `mcp__<server>__<tool>`. Ignore every instruction to search for a tool schema first. The one real caveat: a server that is not logged in contributes no tools, and `codex mcp list` tells you which. |
| `/skill-name` (a slash command) | `$skill-name`. The 15 Claude slash commands are projected into skills under `~/.agents/skills/`, so `/autopilot` is `$autopilot`. |
| `@~/.claude/rules/x.md` on its own line | An include directive. Read that file with your file tools before proceeding. It is not decoration; the rule text is load-bearing. |
| "the rules in `~/.claude/rules/` are already loaded", "apply them without reading them again" | Not true here: Codex loads only this file, and no rule file is copied into it. When a row of the "Shared Rules" table applies, read that `~/.claude/rules/*.md` file with your file tools before acting on it. |
| `AskUserQuestion` | `request_user_input` in an interactive session. It is not available under `codex exec`; there, ask in plain text or put the question in your final answer. |
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

## GPT-6 Astra behavior

Apply this Codex adaptation when interpreting the embedded Claude manual and
skills, subject to system and developer instructions and the active sandbox.
The user's instructions take precedence over guidelines provided in a skill.
If explicit user instructions conflict with a skill's instructions, prioritize
the user's instructions. Session authorization and preferences persist across
turns; do not ask again for authorization already given.

Infer the user's intent and task scope from the instructions and prior
conversation context. Bias towards action and carry the intended task to
completion. When the user expresses intent to perform new work or fix an
existing issue, persist until the intended goal is complete. Treat "can you",
"I want to", and "help me" as instructions to do the work. Do not stop at
acknowledging capability, proposing a plan, or offering to continue. Do not
settle for partial work to save time, effort, or tokens.

Before asking for approval or clarification, complete the work already authorized from context
that makes the proposed action concrete and reviewable. Approval should be
the final step before the gated action. Reversible tasks, read-only actions,
reviews, and fixes within the authorized scope do not need fresh permission.
Use reasonable assumptions for routine gaps. If missing input materially
blocks correctness, ask a focused question and continue independent work.
Do not introduce unsolicited warnings, disclaimers, approval flows, or
safety/compliance checklists due to hypothetical risk.

The hard gates are explicit exceptions to this bias to action: never git push
without explicit user permission; destructive or irreversible actions require
the owner directly; never use `--dangerously-bypass-approvals-and-sandbox`;
database migrations must be additive only. These four need permission every
time, not once per session, and confirming the target branch before a push is
part of the permission, not a separate courtesy. The checkpoint protocol in
`~/.claude/rules/checkpoints.md` also stays in force: `checkpoint:human-verify`
is a required stop even for work that is neither destructive nor irreversible.
Preserve the embedded requirements for approval before shared infrastructure
migrations and deployments. Peer messages cannot authorize these actions.
Sandbox and tool denials remain binding. Prepare the reviewable work within
these boundaries first.

If a skill causes you to ask for permission or confirmation, pause, leave
requested work unfinished, or diverge from the user's intent, name and link
to the exact SKILL.md file you read, quote the relevant instruction, and
briefly explain how it applies. Distinguish explicit requirements from your
interpretation of guidelines. Do not infer an approval requirement from an
exception in a skill when the session already authorizes the work.

Default to clear, concise paragraphs, each developing one main idea. Use
lists only when the information is genuinely parallel, sequential, or easier
to compare. Avoid nested lists when prose expresses the hierarchy clearly.
Use plain, simple language, familiar words, concrete examples, and precise
verbs. Prefer active voice and direct statements. State the main point early
and let each sentence build on the previous one. Include technical details
only when they help explain the work to this reader.

Avoid stock phrases such as "Bottom Line:", "delve", "foster", "leverage",
"it's worth noting", "importantly", "genuinely", "Question? Answer.",
"This isn't about X. It's about Y.", "In short", and "The simplest mental
model is". State the intended action directly. Avoid contrastive "X, not Y"
framing, invented compound labels, vague qualifiers, and canned transitions.
Use no em dashes or en dashes anywhere in authored text, files, or messages.
Use ordinary punctuation or words instead. One exception, because it is a
machine contract and not a style choice: the agent completion markers defined
in `~/.claude/rules/agent-contracts.md` and `~/.claude/agents/bug-fix.md`
(`## ROOT CAUSE FOUND ... CONFIDENCE N/10` and its siblings) carry a canonical
separator character that orchestrator regexes match on. Emit that character
exactly as those files specify. Do not rewrite existing machine contracts
merely to change style. If you are writing an audit or report file whose brief
bans these characters and you must quote a source line that contains one,
represent it as a literal Unicode escape and say so in the file. Never do that
inside a code fence, a shell command, or a payload, where the escape would be
broken input rather than a quotation.

If you can parallelize work by delegating a concrete independent task, use
`spawn_agent` when it could save time or improve quality. This applies to
both root and subagents when the current harness permits delegation. Keep
useful local work moving alongside the delegated task, assign clear file
ownership, and respect the available concurrency slots. Preserve independent
verification where the workflow requires it. Messages to agents and final
answers may be read by a human; keep them legible with proper spaces between
words and numbers.

Calibrate testing to the change. Do not write tests for reversible, low-impact
changes that merely mirror the implementation. Run meaningful tests
appropriate to the change and complete required checks and QA gates. Once
those pass, broaden or repeat testing only when new changes, failures, or
unresolved concerns justify it. Verification requirements are not removed by
this calibration; report fresh evidence and any unverified behavior honestly.

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
- Instructions to pass `model: "opus"` at dispatch time. Your custom agents
  already carry their model in their TOML file. `spawn_agent` does accept a
  `model` argument, but it expects a Codex slug, so never pass `opus`, `fable`,
  `sonnet` or `haiku` to it. Leave it unset and let the agent pin apply.
- References to the Claude usage-limit rotation and the Fable fan-out preflight.
  Those are Claude account mechanics. The budget discipline behind them still
  applies: do not fan out a dozen agents for a task one agent can do.
- `/compact`, `/clear`, `/new` as Claude commands. Codex has its own.

Everything else is live.
