# Git Safety

Combined from obra/superpowers `using-git-worktrees` and gsd-build/get-shit-done universal anti-patterns.

## Staging Rules

- **Never `git add .`** or **`git add -A`** — accidentally stages secrets, generated files, or unrelated edits.
- **Stage specific files by name.** `git add path/to/file.ts path/to/other.ts`.
- If a directory has many files all relevant: `git add path/to/dir/file1 path/to/dir/file2 ...` (or use a glob, but verify with `git status` first).

## Pre-Operation Checks

Before any git operation:

1. **Check for stale lock files** — `[ -f .git/index.lock ]` blocks all git ops; investigate before deleting (may indicate another process running).
2. **Check working tree state** — `git status` first. Don't `git pull` / `git checkout` over uncommitted work.
3. **Verify branch** — `git branch --show-current` matches what you expect. Don't push to `main` thinking you're on `dev`.

## Auto-Generated Directory Safety

**Before any automated process creates a new top-level directory** (`temp/`, `worktrees/`, `output/`, `.cache/`, `dist/`, generated artifacts):

```bash
git check-ignore -q <dirname>
```

**If NOT ignored:**

1. Add the directory to `.gitignore`.
2. Commit the `.gitignore` change with a clear message.
3. Then proceed to create the directory.

**Why critical:** prevents accidentally committing generated artifacts, build outputs, or worktree contents to the repository. This is the rule from obra/superpowers `using-git-worktrees`.

## Destructive Operations

These require **explicit user permission** every time (per `~/.claude/CLAUDE.md` "Git & Deployment"):

- `git push` to any remote branch — confirm target branch first.
- `git push --force` — never to `main` or `dev`.
- `git reset --hard` — investigate uncommitted work first.
- `git checkout .` / `git restore .` — discards uncommitted changes.
- `git clean -f` / `git clean -fd` — discards untracked files.
- `git branch -D` — verify branch is merged or backed up.
- `git rebase` (any flavor on shared branches).
- Any `--no-verify` / `--no-gpg-sign` flag — bypasses hooks/signing.

## Commit Hygiene

- Never commit files containing secrets (`.env`, `credentials.json`, API keys, tokens) — `gitleaks-guard.py` runs as a `PreToolUse` Bash hook to catch this, but don't rely on it alone.
- Prefer creating a new commit over `--amend` (amending mid-hook-failure can destroy work).
- Use HEREDOC for multi-line commit messages to preserve formatting.
- Match the project's existing commit message style (check `git log --oneline -20`).

## Pull Request Hygiene

- Never open a PR without running tests in this turn (per `~/.claude/rules/gates.md` Verification Gate Function).
- PR body should reflect the **whole branch**, not just the latest commit.
- Don't use `gh pr create --no-edit` flags.
