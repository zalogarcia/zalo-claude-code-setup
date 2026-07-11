---
name: commit-with-heredoc
description: Create a multi-line git commit using the correct heredoc-inside-$(...) quoting pattern, with the Co-Authored-By trailer. Use whenever the user asks to commit, when a workflow needs to commit changes, or when a multi-line commit message is required. Eliminates re-deriving the tricky quoting and ensures a consistent commit-message style.
---

Produce git commits with multi-line messages safely. The HEREDOC-inside-`$(...)` pattern is the only quoting that survives newlines, single quotes, and backticks in the body without escaping headaches.

## When to invoke

- Any time the user says "commit" / "commit this" / "create a commit"
- At the end of `/ship`, `/autopilot`, `/bug`, or any workflow that finishes by committing
- When asked to commit with a specific message style (conventional commits, etc.)

Skip for: trivial single-word commit messages where `git commit -m "fix typo"` is fine.

## Pre-commit checklist (always)

Before crafting the message:

1. **Format BEFORE staging.** If the repo has a formatter hook (deno fmt, prettier via husky, ruff — check `.claude/VERIFY.md` "Formatter / hooks" or the hook configs), run the formatter on your changed files NOW, then stage. Staging unformatted files lets the hook rewrite the whole file at commit time, turning a surgical diff into a 700-line reformat that must be restored and reapplied (recurring incident class in the 2026-07 audit — 4 sessions, 3 repos).
2. `git status` — confirm staged files match intent
3. `git diff --cached` — review the actual changes
4. `git log --oneline -5` — match the repo's existing commit style (conventional commits? imperative mood? capitalization?)
5. Confirm no secrets staged (`.env`, `credentials.json`, API tokens)
6. Stage only specific files — **never** `git add .` or `git add -A` (per `~/.claude/rules/git-safety.md`)

## The invocation

```bash
git commit -m "$(cat <<'EOF'
<subject line — imperative, ~50 chars, conventional-commit style if the repo uses one>

<body — wrap at ~72 chars, blank line before/after, focus on WHY not WHAT>

<optional: BREAKING CHANGE / Fixes #123 / Refs #456>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

**Critical quoting details:**

- `"$(cat <<'EOF' ... EOF)"` — the outer double quotes group the heredoc output as one argument
- `'EOF'` (quoted) — prevents shell variable expansion / backtick execution inside the message
- `EOF` (closing) — must be at column 0, no leading whitespace
- The body can contain `$`, backticks, single quotes, dollar signs — all safe with the quoted heredoc

## Subject line conventions

Match the repo's existing style. Common patterns:

- **Conventional commits**: `feat(scope): subject` / `fix(scope): subject` / `chore: subject` / `docs: subject` / `refactor(scope): subject`
- **Plain imperative**: `Add user authentication` / `Fix race condition in queue`
- **Type-prefixed**: `[fix] X` / `[feat] X`

Check `git log --oneline -20` to see what the repo uses, then match.

## Body guidelines

- **Focus on WHY**, not what. The diff already shows what.
- Wrap at ~72 chars per line
- Use bullet points for multiple unrelated changes (but prefer splitting into separate commits)
- Reference issues/PRs at the bottom: `Fixes #123`, `Refs #456`
- For breaking changes, include `BREAKING CHANGE: <description>` in the footer

## Trailer

Always include the Co-Authored-By trailer for AI-assisted commits:

```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

(Adjust the model name if running a different Claude version.)

## After committing

```bash
git status                       # confirm clean working tree
git log -1 --format="%H %s"      # verify the commit landed
```

**A commit may time out but LAND.** Pre-commit scans/hooks (e.g. the
gitleaks-guard PreToolUse hook) can eat the Bash tool-call budget, so the
tool call reports a timeout while git completed the commit underneath. Before
retrying a "timed out" commit, ALWAYS run `git log -1 --format="%H %s"` and
check whether the commit already landed — a blind retry creates a duplicate
commit (or commits a half-restaged index). If it landed: done, do not retry.
If it didn't: `git status` to confirm the index is still staged as intended,
then retry.

**Do NOT push** without explicit user permission (per `~/.claude/CLAUDE.md` "Git & Deployment"). The user must say "push" before any `git push`.

## Pre-commit hook failures

If the commit fails due to a pre-commit hook:

1. **Do not `--amend`** — the commit didn't happen, so `--amend` would modify the PREVIOUS commit (destroying work)
2. Read the hook output, fix the issue
3. Re-stage the fixed files
4. Create a NEW commit with the same heredoc invocation

## Anti-patterns

- ❌ `git commit -m "Line 1\nLine 2"` — backslash-n doesn't become a newline in `-m`
- ❌ `git commit -m "$(echo -e 'Line1\nLine2')"` — fragile, breaks with backticks/dollar signs in body
- ❌ Unquoted heredoc `<<EOF` — allows shell expansion, breaks on `$` or backticks in body
- ❌ Closing `EOF` with leading whitespace — heredoc doesn't terminate
- ❌ `git add .` followed by `git commit` — risks staging unrelated files / secrets
- ❌ Skipping the `git diff --cached` review — you commit blind

## Example (filled in)

```bash
git commit -m "$(cat <<'EOF'
feat(auth): add magic-link sign-in flow

Replaces the password-based flow for new users. Uses Supabase's
auth.signInWithOtp() under the hood. Existing password accounts
continue to work; this only adds a parallel entry path.

Why: reduces signup friction by ~40% based on the staging A/B test
(Linear EHR-204).

Refs #204

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```
