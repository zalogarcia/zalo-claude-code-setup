---
name: create-skill
description: Author a new Claude Code skill following the established pattern. Use when the user says "create a skill", "add a skill", "let's skill-ify X", "promote this to a skill", or asks "should this be a skill?" Guides the decision (is it worth a skill?), picks the form factor (markdown-only vs shell script), generates the SKILL.md from the canonical template, optionally generates an accompanying shell script, and proposes the CLAUDE.md callout for deterministic firing. Replaces ad-hoc skill creation with a consistent shape that matches typecheck-and-build, commit-with-heredoc, dev-server-restart, autopilot-collect, and cf-crawl.
---

Create a new skill that fits the established pattern in `~/.claude/skills/`. Don't free-form a SKILL.md — work the decision tree, pick the form factor, fill the template, register.

## When to invoke

- User says "create a skill", "make a skill for X", "let's add a skill"
- User describes a recurring pattern and asks "should this be a skill?"
- During cleanup/analysis: a recurring inline command appears 3+ times across sessions
- After a `/qa-loop` or `/bug` session that re-derived the same tricky invocation

Skip for: one-off scripts, project-specific tooling (those belong in the project, not `~/.claude/skills/`).

## Step 1 — Decide if it's actually skill-worthy

Apply this gate **before** writing anything. A "no" here means don't create the skill. Be willing to push back on the user.

| Question                                                                        | Required answer |
| ------------------------------------------------------------------------------- | --------------- |
| Has the pattern appeared in **3+ different sessions** in the last 30 days?      | yes             |
| Is it **generic across projects**, not tied to one repo?                        | yes             |
| Is it **non-trivial** — 3+ lines OR 1 line with non-obvious flags?              | yes             |
| Is the output **deterministic** given consistent input?                         | yes             |
| Is it **NOT already covered** by an MCP, an existing skill, or a one-liner CLI? | yes             |

If any answer is "no", explain why and don't create the skill. Examples of legitimate rejections:

- ❌ "Run `git status`" — trivial one-liner
- ❌ "Query Supabase SQL" — already covered by `mcp__supabase__execute_sql`
- ❌ "Deploy this specific Edge function" — project-specific
- ❌ "Help me think about X" — judgmental, use `/brainstorm` instead
- ✅ "Standardize tsc + build with smart tail" — recurring, generic, non-obvious tail length

## Step 2 — Choose the form factor

| Skill type                                                       | Form                                         | Example                                      |
| ---------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------- |
| **Mechanical / deterministic** (kill+restart, file ops, polling) | Shell script + slim SKILL.md pointing to it  | `dev-server-restart/restart.sh`              |
| **Process / discipline / quoting / decision tree**               | Pure markdown SKILL.md                       | `commit-with-heredoc`, `typecheck-and-build` |
| **API wrapper with secrets**                                     | Markdown with env-var config + curl examples | `cf-crawl`                                   |
| **Library of options** (palettes, templates, presets)            | Markdown with structured tables              | `frontend-design`                            |

**Decision rule:** if the LLM's judgment adds value (when to invoke, what to check, how to interpret output), markdown. If the operation is purely mechanical (kill process X, format string Y), shell script.

When both apply — markdown SKILL.md that **points to** a sibling shell script. The SKILL.md gives Claude the trigger logic; the script gives Claude the deterministic execution.

## Step 3 — Fill the canonical template

Write to `~/.claude/skills/<kebab-case-name>/SKILL.md`:

````markdown
---
name: <kebab-case-name>
description: <RICH description with trigger phrases. Include "Use when X / Y / Z" phrases the model will pattern-match on. Mention what it replaces if it's replacing recurring inline patterns. End with one sentence on the consistency benefit. ~3-5 sentences total.>
---

<One-line value proposition. What does this skill DO? Not what it IS.>

## When to invoke

- <Concrete trigger 1 — what the user says or what the situation looks like>
- <Concrete trigger 2>
- <Concrete trigger 3>

Skip for: <opposite cases — trivial scope, wrong tool, etc.>

## Configuration (only if it uses secrets/env vars)

Secrets are stored in environment variables (configured in `~/.claude/settings.local.json`):

- **<NAME>:** `$ENV_VAR_NAME`

## The invocation / How to use

<Concrete commands or steps. Show the exact pattern. If shell script: show invocation. If markdown-only: show the template / pattern Claude should follow.>

```bash
# Show the actual command(s) Claude will run
```
````

## Output shape

<What Claude should report after invoking. Single-line success format. Multi-line failure format. NEVER paste full logs.>

## Anti-patterns

- ❌ <Common failure mode 1 with brief reason>
- ❌ <Common failure mode 2>
- ❌ <The seductive-but-wrong shortcut>

## Edge cases

- <Edge case 1 — how the skill handles it>
- <Edge case 2>

## Pair with

- <Related skill / agent / command> — when to chain them

````

### Description-field rules

The `description:` field is the **only** field Claude pattern-matches against to decide whether to auto-fire the skill. Bad description = skill never fires.

**Good descriptions:**
- Lead with the action: "Author a new...", "Kill any stale...", "Standardize...", "Encode the correct..."
- Name **concrete trigger phrases** the user might say: `Use when the user says "X" / "Y" / "Z"`
- Mention what it replaces (if anti-recurrence): `Replaces 100+ hand-written X chains`
- Cite paired skills/agents

**Bad descriptions:**
- Vague: "A helper for builds"
- Type-only: "Build skill"
- Missing triggers: "Useful for QA"
- Marketing-speak: "Production-grade utility for elite engineers"

## Step 4 — Generate the shell script (only if mechanical)

If the form factor calls for a shell script, write `~/.claude/skills/<name>/<name>.sh` (or a clearer name like `restart.sh`):

```bash
#!/usr/bin/env bash
# <one-line description>
#
# Usage:
#   <name>.sh [POS_ARG_1] [POS_ARG_2]
#   ENV_VAR=value <name>.sh
#
# Defaults: <list defaults>
# Exit codes: 0 = success, 1 = <reason>, 2 = <reason>

set -uo pipefail

# Positional args with env-var fallback
ARG1="${1:-${ARG1:-default}}"

# Pre-detection logic (if applicable)
# e.g., detect package manager, port, cwd

# The work
# ...

# Bounded output, clear exit code
echo "RESULT: <one-line summary>"
exit 0
````

Then `chmod +x <name>.sh`.

### Shell script conventions

- **Shebang:** `#!/usr/bin/env bash` (portable)
- **Strictness:** `set -uo pipefail` (not `-e` — sometimes you want to continue past a failure)
- **Args:** positional with env-var fallback (`PORT="${1:-${PORT:-3000}}"`)
- **Output:** ONE line on success, bounded failure region on error
- **Logs:** redirect to `/tmp/<name>-<context>.log`, surface only the relevant region with grep/awk
- **Exit codes:** 0 = success, 1 = setup error, 2 = runtime error (NOT zero / not one)
- **Paths in error messages:** absolute, so the user can grab them

## Step 5 — Register

Skills auto-register via session reload — you do NOT need to edit `META_RULE.md` unless you want to call attention to the new skill in the top-level summary.

But for **deterministic auto-firing**, add an explicit callout in `~/.claude/CLAUDE.md` near the workflow the skill applies to. Example callouts already in `CLAUDE.md`:

```markdown
- **Before marking any feature or fix complete**, invoke the `typecheck-and-build` skill — it standardizes the tsc+build chain with smart failure-region extraction. Do not roll your own `npm run build 2>&1 | tail -N` invocation.
- For commits, invoke the `commit-with-heredoc` skill — it encodes the correct `$(cat <<'EOF' … EOF)` quoting and the Co-Authored-By trailer.
- For dev-server restarts, invoke the `dev-server-restart` skill — it kills by port, restarts with nohup, polls for readiness, and smoke-tests a route.
```

The pattern: **declarative invocation hint, anchored to the natural trigger moment, with a "do not roll your own" anti-pattern reminder.**

## Step 6 — Verify

After writing:

1. `ls -la ~/.claude/skills/<name>/` — confirms files exist
2. `cat ~/.claude/skills/<name>/SKILL.md | head -5` — confirms frontmatter is valid YAML
3. If script: `~/.claude/skills/<name>/<name>.sh --help` (if you added one) or run with safe args to confirm exit 0
4. Next session start should show the new skill in the available-skills system reminder

## Anti-patterns of skill creation

- ❌ **Creating a skill before the pattern is proven recurring.** Wait for 3+ inline invocations across sessions, OR until the user explicitly says "this is annoying, can we skill-ify it".
- ❌ **Vague description.** If you can't write 3 concrete trigger phrases in the description, the skill won't auto-fire.
- ❌ **Duplicating an MCP.** Check `mcp__*` tools first; if the MCP covers it, point CLAUDE.md at the MCP instead of writing a skill.
- ❌ **Shell script for what's really a judgment call.** Scripts can't decide "should I do this?" — that's markdown's job. Don't push judgment into shell.
- ❌ **Markdown-only for what's really mechanical.** If the operation is `kill X, sleep N, curl Y` with no judgment, write the script — markdown skills get inconsistently re-derived.
- ❌ **Auto-fire dependencies that don't exist.** E.g., a skill that assumes `pnpm` is installed without detecting it.
- ❌ **Project-specific patterns.** Those belong in `<project>/.claude/skills/`, not `~/.claude/skills/`.
- ❌ **No anti-patterns section.** The anti-patterns list is half the value of a skill — it tells Claude what NOT to do, which is harder to derive from scratch.
- ❌ **Secret in plaintext.** Always use env-var pattern. Never write a secret into SKILL.md.

## Edge cases

- **The pattern is recurring but project-specific** — create the skill in `<project>/.claude/skills/`, not the global setup. Mention this distinction to the user.
- **The pattern is partially mechanical and partially judgmental** — markdown SKILL.md that points to a sibling script (the `dev-server-restart` pattern).
- **The pattern depends on a CLI that may not be installed** — add a Prerequisites section to the SKILL.md and have the script check (`command -v <tool> >/dev/null || { echo "Install <tool> first" >&2; exit 1; }`).
- **The pattern is one of many similar variants** — write ONE skill that handles the family via flags, not three near-duplicate skills.

## Pair with

- **`~/.claude/rules-ref/persuasion-principles.md`** — read it when writing the skill's rule-like language (Authority/Commitment/Scarcity framing for instructions that must stick); it lives in rules-ref (on-demand), not always-loaded rules
- **`/brainstorm`** — if unsure whether the pattern is truly recurring, dispatch brainstorm to stress-test the skill idea before writing it
- **30-day usage analysis** — for retroactive skill discovery (general-purpose agent scanning `~/.claude/projects/`)
- **`commit-with-heredoc`** — commit the new skill following the convention
- **CLAUDE.md** — add the explicit invocation callout for deterministic firing

## Example: this skill applied to itself

This very skill (`create-skill`) was written following its own decision tree:

- Recurring pattern? Yes — three skills created in one session by hand-derivation
- Generic? Yes — same shape works for any future skill
- Non-trivial? Yes — the decision tree + form-factor + template + registration is multi-step
- Deterministic? The TEMPLATE is; the judgment (whether to create) isn't, which is why this skill is markdown-only with no script

Form factor: markdown (process + template, no mechanical execution).
Registration: this file at `~/.claude/skills/create-skill/SKILL.md`. CLAUDE.md callout intentionally NOT added — this skill should fire only when the user explicitly asks to create one, not auto-fire on every recurring pattern detection (that would be too aggressive).
