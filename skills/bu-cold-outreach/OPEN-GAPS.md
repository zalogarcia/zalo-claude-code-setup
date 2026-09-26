# Open gaps in this skill, with what would close each

Known, decided, and deliberately not closed yet. Each entry says what is exposed, what
currently contains it, and the specific change that would close it. Read this before
adding a mechanism, so a gap is not "discovered" twice.

## 1. `sent_parts` is an assertion the lint cannot verify (opened 2026-09-12, CLOSED 2026-09-22)

The joke arm's continuation marker let a batch carry the remaining parts of a joke sequence
whose earlier parts went out on a previous day, and the lint could not read `sent-log.csv`
to check the claim. Closed two ways on 2026-09-22 by Zalo's one message rule: the marker,
the `part` field and the three part sequence are retired and refused on sight, and the lint
now DOES read `sent-log.csv` and `pipeline.csv`, refusing any message to a prospect the log
shows was already messaged. The fixtures the old "what would close it" asked for exist in
`scripts/fixtures/single-message/`.

## 2. Health check 5 has no executable form (opened 2026-09-12)

It is prose an agent reads and applies, so every proof of its behaviour (including the
2026-09-12 audit's five month walk that caught it silently disabled by a dead channel) is
a model of the prose, not an execution of it. Closing this means the health checks become
a script that reads `sent-log.csv` and `pipeline.csv` and prints each check's state, which
would also make them testable. Worth doing when a third channel opens, because the
reasoning across channels is where it went wrong the first time.

## 3. No `.claude/VERIFY.md` in `~/.claude` (opened 2026-09-12)

Flagged by the audit. This repo has no deploy surface, so the proof signal for a skill
change is its own test suite (`scripts/note-lint.test.py`, 202 cases as of 2026-09-14) plus
`codex-sync.py all`. If that stops being true, write the manifest.

## 4. The lint cannot see the fact a bridge is doing arithmetic on (opened 2026-09-14)

**What it is.** The arithmetic bridge (`templates/messages.md`) is legal only INSIDE what
the review or the posted hours already show: "closed at 5 and open at 8 is fifteen hours"
is arithmetic on two numbers that are on the screen. `scripts/note-lint.py` never loads the
screen, so it cannot confirm that fifteen is the right answer, or that the profile says 5
and 8 at all. A note claiming "that's twenty hours a day" on the same fact passes.

**What contains it today.** The lint catches the four shapes that are unsupported whatever
the fact was: a money amount, a percentage, an invented rate of calls per time window, and
an ROI claim. Those are the failure modes the research warns about and the ones a drafter
reaches for. Beyond that it is the same thing that already contains every other fact in a
note: the specificity law's paste test, the humanizer pass, and Zalo's batch approval. A
wrong bridge number is a wrong fact, and facts were never this script's job (see its
docstring, "Facts are not checked here").

**What would close it.** Carry the opener's source facts as structured fields on the note
object (`hours_open`, `hours_close`, `review_count_claimed`) and have the lint recompute the
arithmetic. That is a much larger change to the batch pipeline than the bridge law needed,
and it would only cover the two shapes that are computable.

**Priority.** Low. Nothing on the arithmetic bridge has shipped yet; the first batch written
under it is the one after 2026-09-14.

## 5. The Facebook groups channel is specified but unproven (opened 2026-09-14)

**What it is.** `G1`, the group post family, is specified end to end: copy contract, lint
laws, cap, ramp, log row, batch section, report line, learnings table, two gates. Zero posts
have been made and the channel is `Active: no`
with `facebook_groups_ramp_start_date: NOT STARTED`. Every claim about it is therefore a
model of the rules, not an observation of them. In particular: nobody has confirmed that a
group post carrying a phone number survives a real group's admin, the demo number does not
exist in `config.md` yet, and the interrupt gate has never been run.

**What contains it today.** The channel cannot start by accident: `NOT STARTED` is
unparseable as a date, so step 0 of the quota arithmetic returns zero, and `Active: no` in
the channel table is a second lock. No G1 note can even be drafted without a real phone
number, because the lint requires one and bans unfilled tokens.

**What would close it.** Zalo opening the channel, running the interrupt gate, and 20 posts
with their calls per post recorded. Until then the honest statement about this channel is
"specified, never run".

## 6. Two batches on one day can each carry the same prospect (opened 2026-09-22)

**What it is.** The one message gate reads `sent-log.csv` as it stands when the lint runs. If
two batches are drafted on the same day (a research session and a send session, or two
sessions) and both carry one prospect who has not been messaged yet, each file lints clean on
its own, and both could be typed if both are approved and sent without a re lint between.

**Why the obvious mechanism was not built.** Refusing a `prospect_id` that also appears in
another `notes.json` of the same day would refuse the normal flow: on 2026-09-22 the send
session's `session-2/notes.json` re linted a superset of `session-1/notes.json` (all 13 of
session 1's texts are in session 2's 25). A cross file refusal would have failed that day.

**What contains it today.** SKILL.md Step 3 requires a re lint of the exact `notes.json`
immediately before a send pass and again before resuming after any other batch has sent;
once the first batch's sends are in `sent-log.csv`, the re lint refuses the duplicate. Zalo
also approves each batch by name.

**What would close it.** A send time check per message rather than per batch: a tiny
`note-lint.py --before-send <prospect_id>` that exits non zero if the log already holds an
outbound message for that id, run before each message is typed. Worth building if a second
same day batch is ever approved while the first is still sending.

## 7. The walk up takes the nearest `pipeline.csv`, so a full snapshot under `evidence/` would shadow the live files (opened 2026-09-22)

**What it is.** Found by the independent verifier of the one message change. `find_folder`
in `scripts/note-lint.py` returns the first directory at or above `notes.json` that holds a
`pipeline.csv`. If a session ever copied `pipeline.csv`, `sent-log.csv` and `prospects.csv`
under those exact names into `evidence/YYYY-MM-DD/`, a batch linted from below it would be
checked against the stale copy, and a prospect messaged since the copy would pass as fresh.
Reproduced in `/tmp` only.

**What contains it today.** No such copy exists: the evidence tree's snapshots are named
`pipeline-before.csv`, `before-pipeline.csv` and `before-sent-log.csv` (all 9 day folders
scanned 2026-09-22), and a folder holding only `pipeline.csv` fails closed on the missing
`sent-log.csv` or `prospects.csv`. `--folder <working folder>` bypasses the walk entirely.

**What would close it.** Accept a walk up candidate only if it also holds `config.md`
(Zalo's file, never snapshotted), with a `config.md` stub added to the test working folders
and to `scripts/fixtures/single-message/`.

## 8. At 20 Facebook messages a day the named owner pool lasts little more than a day (opened 2026-09-26)

**What it is.** A Facebook row drafts when it carries an owner name before the browser
touches it: 16 to 19 percent of named rows verified an owner on 09-22 to 09-26 (16 of 83,
or 14 of 89 by a stricter count; `hunting-playbook.md` speed default 2 states both methods),
against 2 of 25 rows whose website names nobody (8 percent). On 2026-09-26 the seed had
1,963 qualified rows that no pipeline row or research ledger had touched: 152 named (a 2F.0
candidate or a seed `owner_name`), 1,069 with a `no_owner_reason` from the offline
resolver, and 742 the resolver never read (an independent recount the same morning, with a
slightly wider ledger set, got 1,954, 144, 1,069 and 741). Twenty drafts a day consume about
105 to 127 named rows a day, so the named pool carries a little over one full day, after
which the same 130 research minutes yield about 7 to 10 a day (87 to 127 rows at 8
percent).

**What contains it today.** The worklist order in `hunting-playbook.md` Step 2F.0 spends the
named rows first and the empty ones last, and the report states the rows left per group.

**What would close it.** More names before the browser. The owner resolver in
`~/dev/bu-cold-outreach/tools/owner-resolver/` read 1,363 rows and named 15 percent; the 742
rows it never read would add about 110 named rows at that rate (offline, no login, about 11
seconds a row). Beyond that, a new tranche that carries owner names (the LinkedIn rail rows
arrive named) is the only source that sustains 20 a day, and its spend is Zalo's call.

## 9. Browser and Codex availability decide more days than research does (opened 2026-09-26)

**What it is.** From 09-20 to 09-26 the Codex weekly limit blocked 09-20, 09-21 and 09-25
and the first attempt on 09-26; Computer Use or Chrome failed on 09-23 (first attempt),
09-24, 09-26 during research and 09-26 during the approved send (nothing sent). Research reached a
batch on three of those seven days. The 03:45 research block adds Codex Computer Use time
every day, so it moves the next weekly limit closer.

**What contains it today.** Verified rows are written to `pipeline.csv` as they are found and
the recovery list in Step 2b picks up anything a dead session left in `evidence/`, so a stall
costs the minutes it wasted, not the owners already verified.

**What would close it.** A Chrome health probe before each fire and a Codex usage read in
the 03:45 run, so a day that cannot run says so at 03:45 instead of at 06:00.

