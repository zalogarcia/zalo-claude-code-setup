# Memory Sync Runbook

Keeps Zalo's persistent memory at `~/.claude/projects/-Users-zalo/memory/` current, so any
session can answer "where are we on X?" without re-reading repos or transcripts.

Two modes:

- **delta** (default, nightly 3am) — only what changed since the watermark.
- **backfill** — a wider window (e.g. 30 days), used for the initial build or after a gap.

---

## 0. Read state first

1. Read `~/.claude/projects/-Users-zalo/memory/MEMORY.md` — the one-line index of every memory.
2. Read `~/.claude/projects/-Users-zalo/memory/.sync-state.json`:
   ```json
   { "last_sync": "<ISO8601>", "last_mode": "delta|backfill", "sessions_seen": <int> }
   ```
   If missing/corrupt → treat `last_sync` as 24h ago (delta) or 30d ago (backfill), and note it.

`WATERMARK` = `last_sync` in delta mode, or the requested window start in backfill mode.

---

## 1. Gather what changed

**Git** — for each repo in `~/dev/*/` plus `~/zalo-ads/`:

- SKIP any path matching `*-autopilot-*` (throwaway worktrees) and `node_modules`.
- `git -C <repo> log --all --since="<WATERMARK>" --oneline --format='%h%d %s'` — **`--all`, never
  HEAD-only.** Skip the repo entirely only if this returns zero commits AND the working tree is
  clean. A HEAD-only `log --since` misses every commit that landed on a feature branch, inside a
  worktree, or on `origin/<default>` while local `<default>` sat behind — which is the normal
  shape of a day here, not an edge case. Measured 2026-08-22: the HEAD-only census reported 9
  delta-agents commits; `--all` found that `origin/main` was **7 commits AHEAD of local `main`**
  plus six merged feature branches and one unmerged local-only harness branch. Nearly the whole
  window was invisible to the prescribed command. (This line was worked around by hand in
  dispatch prompts for four consecutive runs before being fixed here.)
- Then RESOLVE what that census found, per branch with in-window commits:
  - merged? `git merge-base --is-ancestor <branch> origin/<default> && echo MERGED || echo UNMERGED`
  - pushed? `git rev-parse --verify -q origin/<branch>`
  - is local behind its own remote? `git log <default>..origin/<default> --oneline`
  - live worktrees: `git worktree list` (a worktree is where unmerged work actually lives)
- Also capture: current branch, uncommitted/untracked files, unpushed commits
  (`git log @{u}.. --oneline` where an upstream exists).

**Sessions** — Claude Code transcripts:

```bash
python3 ~/.claude/scripts/gather-transcripts.py --since "<WATERMARK>" --min-size 50000 --show-dropped
```

Output is TSV — `path  size_bytes  first_record  last_record  in_window_records` — sorted by
in-window record count, so the first rows are genuinely the richest sources. `--json` gives the
same data structured. `--show-dropped` prints the rejects to stderr; keep it on and glance at
them, since a surprising drop is usually the interesting signal.

- **Never gather by `mtime` alone.** `find -newermt` was the old step and it silently
  over-selects: Claude Code appends metadata-only lines (`last-prompt`, `custom-title`, `mode`)
  that carry **no timestamp**, so a session whose conversation ended days ago gets a fresh mtime
  and enters the window looking substantive. On 2026-08-03 that cost **three of six cluster
  agents their entire budget proving an empty window** — including a 90MB zalo-ads transcript
  briefed as "the richest source in the window" whose last real record was two days stale. The
  script keeps mtime as a cheap prefilter (it never *under*-selects) and then drops anything
  whose newest real record predates the watermark. Measured on that same window: 8 of 35 mtime
  candidates were fake, in 0.3s.
- **Brief agents with the transcript's true span, never its mtime.** The `first_record` /
  `last_record` columns exist for exactly this — put them in the dispatch prompt.
- The `/subagents/` and `/workflows/` paths are noise — always excluded (the script does this).
  For scale: a 30-day window is ~5700 files total but only ~300 top-level sessions, ~175 >50KB.
- `--min-size 50000` keeps this to substantive sessions. Drop the flag to sweep smaller ones when
  a project has no other signal.
- Map transcript dir → project: `-Users-zalo-dev-<repo>` → `~/dev/<repo>`;
  `-Users-zalo-zalo-ads` → `~/zalo-ads`; `-Users-zalo` → home/general;
  `-private-tmp-...-scratchpad` → ignore unless it's the only record of real work.

**What to extract from a session** (not a transcript summary — the *residue*):

- Current state: what's built, what works, what's deployed vs local-only.
- Decisions made and *why* (especially ones a future session would otherwise re-litigate).
- Blockers, and specifically **what is waiting on Zalo** vs waiting on code.
- Gotchas/traps discovered — anything that cost more than one wrong turn.
- Explicit user corrections and preferences.

---

## 2. Write memory

**Update in place. Never create a second file for a project that already has one.**
Match `MEMORY.md`'s index to the files on disk before writing anything.

Conventions (match the 25 existing files exactly):

- Naming: `project_<slug>.md`, `feedback_<slug>.md`, `reference_<slug>.md`.
- Frontmatter:
  ```yaml
  ---
  name: <kebab-slug>
  description: "<one line — this is what future-me reads to decide relevance>"
  metadata:
    node_type: memory
    type: project | feedback | reference | user
    originSessionId: <uuid if known>
  ---
  ```
- Body: dense prose in **bold-led paragraphs** (`**Data contract:**`, `**Ops gotchas:**`,
  `**Publish rail (date):**`). Cross-link other memories with `[[wikilinks]]`. Absolute dates,
  never "last week". See `project_zalo_os.md` as the reference shape.

**What NOT to record** — it wastes context and goes stale:

- Commit-by-commit history (git already has it). Record *state and why*, not a changelog.
- Anything derivable from the repo's own `CLAUDE.md` / `VERIFY.md` / code structure.
- Session play-by-play. Only the durable residue survives.

**Conflicts:** if new information contradicts an existing memory, the new information wins —
rewrite that section and keep the file single-source-of-truth. Delete memories proven wrong.
If a memory names a file/flag/command, verify it still exists before restating it.

Then update `MEMORY.md`: one line per memory, `- [Title](file.md) -- hook`. Add lines for new
files, revise the hook for changed ones. Never put memory content in MEMORY.md itself.

---

## 3. Close out

1. Write `.sync-state.json` with the new `last_sync` (the time the scan started, not finished —
   avoids a gap), `last_mode`, `sessions_seen`.
2. **Run silent — do NOT message Zalo's Telegram** (his explicit instruction, 2026-07-27).
   Return your summary as your final output only; it goes to the orchestrator, not to him.
   The ONLY exception: the sync itself failed or found something broken that needs his
   decision — then one short Telegram message explaining what and why.

---

## Guardrails

- **Read-only on repos.** Never commit, stage, push, checkout, or clean. This job observes.
- Budget the transcript reads — prefer many small targeted reads over loading whole 2MB files.
  Dispatch subagents per project for anything requiring more than a couple of file reads, and
  synthesise their returns yourself.
- If a project has changes you can't confidently summarise, say so in the memory file
  explicitly (`**Unclear as of <date>:** …`) rather than guessing. A wrong memory is worse than
  a missing one.
