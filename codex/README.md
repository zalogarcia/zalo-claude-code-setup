# Codex projection

Codex CLI runs the same setup as Claude Code by reading a GENERATED projection
of `~/.claude`. There is one source of truth and it is `~/.claude`. Nothing
under `~/.codex` in the generated surfaces is hand-maintained. Top-level model
and effort settings outside the managed config block remain user-owned.

The `GPT-6 Astra behavior` section in `codex/AGENTS.delta.md` adapts the supplied
OpenAI guide's prompts for initiative, skill precedence, writing, delegation,
and calibrated testing. It makes existing owner approval and sandbox gates
explicit exceptions to autonomous follow-through. It also requires exact skill
citations when a skill causes a pause and bans em dashes and en dashes in
authored text, with one carve-out: the agent completion markers in
`rules/agent-contracts.md` are machine contracts that orchestrator regexes
match on, so their canonical separator is emitted as specified. System and developer instructions remain higher priority.

## What is generated, and from what

| Generated | Source | Target |
| --- | --- | --- |
| `~/.codex/AGENTS.md` | `codex/AGENTS.delta.md` + `META_RULE.md` + `CLAUDE.md` + `~/dev/CLAUDE.md` | `agents-md` |
| `~/.agents/skills/<name>` (symlinks) | `~/.claude/skills/<name>` | `skills` |
| `~/.agents/skills/<cmd>/SKILL.md` | `~/.claude/commands/<cmd>.md` | `skills` |
| `~/.codex/hooks.json` | `~/.claude/settings.json` hooks | `hooks` |
| `~/.codex/agents/*.toml` | `~/.claude/agents/*.md` | `agents` |
| `~/.codex/config.toml` managed block | `~/.claude.json` mcpServers | `mcp` |

```bash
python3 ~/.claude/scripts/codex-sync.py all     # regenerate everything
python3 ~/.claude/scripts/codex-sync.py check   # report drift, exit 1 if stale
python3 ~/.claude/scripts/codex-sync.py hooks   # one target
```

It runs itself in two places, so drift usually heals without anyone asking:

- A Claude Code `PostToolUse` hook calls `codex-sync.py --on-edit` after every
  edit, and regenerates only the projection that the edited file feeds.
- A Codex `SessionStart` hook calls `codex-sync.py all --if-stale --quiet`.

`~/.codex/config.toml` is spliced, not rewritten: only the region between
`# BEGIN codex-sync` and `# END codex-sync` belongs to the generator. Codex's
own `[projects.*]` trust entries outside it are preserved byte for byte, and
the file stays mode 600 because it carries MCP tokens.

## When hooks.json changes, re-trust it

Codex binds hook trust to the file's hash, so ANY change to `~/.codex/hooks.json`
leaves the mirrored guards untrusted and silent. The sync script shouts about
this on stderr when it happens. The fix is one time, in an interactive session:

```
codex          # then, at the prompt:
/hooks         # review and trust
```

There is no CLI flag that persists trust. `--dangerously-bypass-hook-trust`
exists but is for one-off probes in throwaway directories, never for normal use.

## Adding a per-repo AGENTS.md

Codex reads `AGENTS.md` from the git root down to the cwd, and it does NOT walk
above the git root. That is why `~/dev/CLAUDE.md` is folded into the global
`~/.codex/AGENTS.md`: Claude Code loads it for every repo under `~/dev`, and
Codex never would.

Per-repo instructions are not projected automatically. To give a repo its Claude
instructions in Codex, symlink them at the repo root:

```bash
cd ~/dev/<repo>
ln -s .claude/CLAUDE.md AGENTS.md     # or: ln -s CLAUDE.md AGENTS.md
```

Check what the repo's file assumes before you do it. A `.claude/CLAUDE.md` full
of `subagent_type`, `ToolSearch` and `Edit`/`Write` vocabulary will read as
nonsense in Codex unless the global adapter's translation table covers it. The
adapter is `codex/AGENTS.delta.md`; extend it rather than forking the repo file.

## What is deliberately not ported

- **`session-start.sh`.** It injects `META_RULE.md` as `additionalContext`, and
  Codex caps that at 2500 characters, which would truncate an 8 KB rule file
  into nonsense. `META_RULE.md` is concatenated into `AGENTS.md` instead, and
  the SessionStart slot is reused for the drift self-heal.
- **`agent-model-guard.py`** (Claude matcher `Agent|Task`). It blocks a
  model-less dispatch of a BUILT-IN agent type on a Fable session. In Codex
  every spawnable agent is a custom agent whose TOML pins its own model, and
  the guard's own logic exits 0 for custom agent types. Porting it would add a
  hook that can never fire.
- **`background-lane-guard.py`** on the same matcher. It returns 0 for any
  tool that is not `Bash`, so that registration is already inert in Claude
  Code. Its live half, the `Bash` matcher, IS ported.

## Known partials (ported, but not full parity)

- **`continue-if-incomplete.py`** (Stop hook) works, but weaker than in Claude.
  Its strongest signal is "the turn ended on a tool call with no summary text",
  read from the trailing content-block type. The shim's transcript projection
  only ever emits text blocks, so that branch never fires and the hook falls
  back to its lexical heuristics. It still nudges; it just misses the
  mid-action case.
- **`~/.codex/config.toml` has a narrow write race.** The generator reads the
  file, splices its block, and writes. Codex appends `[projects.*]` trust
  entries to the same file when it first sees a directory. If the two land in
  the same few microseconds, one loses and you re-approve a directory once.
  The read and the write are adjacent on purpose to keep that window as small
  as possible. No data outside the managed block is ever rewritten.
- **MCP tool calls need one approval.** All 7 servers are registered and
  `codex mcp list` shows them, but Codex asks for approval before calling a
  tool on a stdio server, and `codex exec` with `approval_policy = "never"`
  refuses rather than prompting. Interactive sessions prompt normally. A live
  `context7` call succeeded non-interactively; a `github` one did not.
- **A patch touching more than 40 files is refused before it is applied.**
  The shim guards at most 40 files per `apply_patch` call, so that a runaway
  patch cannot fork hundreds of guard processes. At PreToolUse it refuses the
  whole patch with an explanation (split it), because guarding only the first
  40 would leave a guard that looks alive and is not. At PostToolUse, where
  the write has already landed, it checks the first 40 and says on stderr
  which files went unchecked.

- **Only the GLOBAL MCP set is projected.** Project-scoped servers in a repo's
  own config are not, because the target is `~/.codex/config.toml`.

## The model map

`MODEL_MAP` in `codex-sync.py` owns generated custom-agent model choices:

| Claude pin | Codex model | Effort | Agents |
| --- | --- | --- | --- |
| `fable` | `gpt-6-astra` | `xhigh` | brainstorm, bug-fix, qa-agent, safe-planner |
| `opus` | `gpt-5.6-sol` | `high` | frontend-specialist, image-craft-expert, live-test, outcomes-grader |

Same shape as the Claude split policy: the low-volume thinkers whose one verdict
cascades get the flagship at the preserved `xhigh` effort; the high-volume implement and
verify tier keeps GPT-5.5 at `high`, which also keeps the verifier
in a different model generation from the author. Retune by editing that table
and running `codex-sync.py agents`.

The Astra migration preserves effective effort as the guide recommends.
The separate GPT-5.5 volume tier is intentionally retained: the guide provides
no requirement to migrate every tier, and changing it would alter the existing
workload split. This is a routing decision, not a measured cost claim. CLI
defaults and Telegram bridge defaults are separate surfaces outside this repo.
