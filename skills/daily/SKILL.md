---
name: daily
description: >
  Run Zalo's daily content hour for the Zalo Kabche brand from ANY working
  directory — including Telegram/bridge sessions rooted at ~/dev. Invoke when
  Zalo says /daily, "what's today", "daily check-in", "today's reel", or opens a
  session to do his content hour. This is a thin router: the real procedure
  lives in ~/dev/zalo-kabche-brand/.claude/skills/daily/SKILL.md and is followed
  verbatim. Inside that repo, the repo-scoped skill wins and this one is unused.
---

# /daily (from anywhere)

The brand machine's daily loop lives in the `zalo-kabche-brand` repo. This skill
exists only so `/daily` also works from a session rooted elsewhere — mainly the
Telegram bridge, whose cwd is `~/dev`. **Do not restate the procedure here.**
Read the repo's files and follow them exactly; they are the single source of
truth and they change without this file changing.

## Router

`BRAND=~/dev/zalo-kabche-brand`

1. Read `$BRAND/.claude/skills/daily/SKILL.md` — the actual procedure. Follow it
   start to finish, except that its close step's push waits for Zalo's go-ahead (step 4).
2. Read `$BRAND/.claude/CLAUDE.md` — the repo runbook/guardrails do NOT auto-load
   in a session rooted outside the repo, so load them explicitly before producing
   anything (evergreen rule, why-first, fakeness filter, spoken-register rule,
   teleprompter formatting).
3. Every path in those files is repo-relative — prefix with `$BRAND/`
   (`process/cycle-state.md` → `~/dev/zalo-kabche-brand/process/cycle-state.md`).
4. Git runs with `-C $BRAND` (`git -C ~/dev/zalo-kabche-brand add <files>`), never
   a bare `cd`. The repo skill's close step commits in that repo; keep the commit. Pushing,
   deploying and migrations still need Zalo's go-ahead: ask for the push in the same
   short reply and push only after he says so.
5. The freestyle REEL CARD ships with every run (`$BRAND/.claude/skills/freestyle-reel/SKILL.md`,
   CARD mode) — it is part of the repo skill's contract, not an extra.

## Telegram shape (when running from the bridge)

Zalo is on his phone. The repo skill's "≤5 lines" announcement is the whole
reply — cycle day, today's ONE task, what's already prepped, the 15-min
fallback — then the REEL CARD as its own short block. No headers, no tables, no
walls of text.

**Announce first, prep second.** If the machine-side prep for today's task is
heavy (mining a transcript, drafting a script, rendering b-roll, batching
reels), send the announcement + card immediately, then hand the prep to a
background worker (`node ~/dev/claude-telegram-bridge/bg.mjs "<self-contained task>"`)
so the chat stays reachable. Never make him wait on a render to learn what
today's task is.

If he replies with a take (video/audio/transcript), that's RATE mode of the
freestyle-reel skill — same router rules apply.
