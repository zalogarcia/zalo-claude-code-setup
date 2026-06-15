---
name: typecheck-and-build
description: Run TypeScript typecheck and production build for a Node/Next.js/Vite project, capture exit codes, and surface only the failure region (not the full log). Use when verifying changes before commit, in QA loops, after a refactor, or whenever a "did this build?" check is needed. Replaces hand-written tsc + build chains with a consistent invocation and consistent output shape.
---

Run the project's typecheck and production build, then return a compact result Claude can reason about — without guessing what `tail -N` value to use.

## When to invoke

- After multi-file edits, before claiming "done"
- Inside a `/qa-loop` audit cycle
- After a refactor or rename across files
- Before any `git commit` that touches `.ts` / `.tsx` source
- When the user asks "does it build?"

Skip for: docs-only changes, README edits, single-comment-line edits.

## The invocation

Always run from the project root (where `package.json` lives). Detect package manager once per project (cache the answer in your session):

```bash
PM="npm"
[ -f pnpm-lock.yaml ] && PM="pnpm"
[ -f yarn.lock ] && PM="yarn"
[ -f bun.lockb ] && PM="bun"
```

### Step 1 — typecheck

```bash
npx tsc --noEmit > /tmp/tsc.out 2>&1; echo "EXIT=$?"
```

> **Why no pipe?** Capturing the exit code through a pipe (`… | tee …; echo "${PIPESTATUS[0]}"`) is shell-dependent: in **zsh** (the default shell here) `PIPESTATUS` is unset — the array is lowercase `pipestatus` and 1-indexed — so `EXIT=` comes out empty and you can't tell pass from fail. Redirecting to a file and reading `$?` is the command's own exit code and works identically in bash and zsh. Read the captured output from the file in the next step.

- If `EXIT=0` → typecheck passed; proceed to step 2.
- If `EXIT≠0` → DO NOT run the build. Show the user the failure region (see "Output shaping" below) and STOP.

### Step 2 — production build (only if typecheck passed)

```bash
$PM run build > /tmp/build.out 2>&1; echo "EXIT=$?"
```

- If `EXIT=0` → done. Report "typecheck + build clean".
- If `EXIT≠0` → show the failure region and STOP.

## Output shaping (the real value of this skill)

Do **not** dump the full log into the conversation. Extract only the part that matters:

**On failure** — show only lines around the error. The hand-written `tail -N` approach is unreliable because failure regions can be 3 or 80 lines depending on the error count. Use this instead:

```bash
# For tsc failures — show all error lines + 2 lines of context after each
grep -nE "error TS[0-9]+:" /tmp/tsc.out | head -20

# For build failures — first ~40 lines after the word "error" or "failed"
awk '/error|Failed|FAIL/{flag=1} flag{print; n++; if(n>40)exit}' /tmp/build.out
```

**On success** — one line:

```
typecheck: 0 errors | build: success (Xs)
```

## Anti-patterns

- ❌ `npm run build 2>&1 | tail -10` — guessed tail length; misses early errors
- ❌ `… | tee out; echo "${PIPESTATUS[0]}"` — `PIPESTATUS` is empty in zsh; the exit check silently fails. Redirect to a file and read `$?` instead (see Step 1).
- ❌ Running build before typecheck — wastes time when types are broken
- ❌ Running these in the wrong cwd — always confirm `pwd` shows the project root
- ❌ Reporting "build looks good" without showing the EXIT code

## Edge cases

- **Monorepo (turbo / nx / pnpm workspace)** — use `$PM run build` at the root; the workspace tool fans out. If a specific package is failing, drill in with `$PM --filter <pkg> run build`.
- **Next.js** — `npx tsc --noEmit` works; Next's own type-checking runs during `next build` but is slower, so run `tsc --noEmit` first for the fast feedback loop.
- **Vite / Vue / Svelte** — `npx tsc --noEmit` still works for the TS portion; the bundler handles the rest in build.
- **No `tsc` available** — `npx tsc` will fetch it; if you want to use the project's pinned version, `$PM exec tsc --noEmit`.

## Verification gate

This skill IS verification — but only if you actually run it. Per `~/.claude/rules/gates.md`, claiming "build passes" without an EXIT=0 in this turn is a verification violation. Show the EXIT code in your response.
