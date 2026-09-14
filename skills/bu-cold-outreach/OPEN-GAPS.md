# Open gaps in this skill, with what would close each

Known, decided, and deliberately not closed yet. Each entry says what is exposed, what
currently contains it, and the specific change that would close it. Read this before
adding a mechanism, so a gap is not "discovered" twice.

## 1. `sent_parts` is an assertion the lint cannot verify (opened 2026-09-12)

**What it is.** The joke arm's continuation marker (`sent_parts`, `joke_setup`) lets a
batch carry only the remaining parts of a joke sequence whose earlier parts went out on a
previous day, which is what makes an interrupted sequence finishable at all. The lint
validates the marker's SHAPE (a strict prefix of setup, punchline, ask; the parts present
being the contiguous run after it; the punchline belonging to the named setup) but it
never reads `sent-log.csv`, so it cannot confirm the claimed earlier sends actually
happened. A marker that lies would let a fresh row skip its setup send.

**What contains it today.** Three things, and they are why this is a gap and not a hole.
Every part is still matched against the approved setups, punchlines and the fixed ask
regex, so no unapproved copy can ride in on a marker (the 2026-09-12 re audit fuzzed
158,256 marker batches: 19 accepted, 0 carrying text outside the approved strings). The
joke repetition cap counts continuations, so the marker cannot be used to send one joke
to the whole batch. And Zalo approves every batch by name before anything sends.

**What would close it.** Teach `scripts/note-lint.py` to read `sent-log.csv` and verify
that each row cited by a `sent_parts` marker exists with the stages it claims, failing the
batch when a claimed send is absent. That is a larger change than the finding asked for
and it gives the lint a new input, so it wants its own test fixtures for a missing row, a
stage mismatch and a row from the wrong prospect.

**Priority.** Low until the J arm has actually sent something. Facebook opened 2026-09-13 (moved from 09-15 on
2026-09-12) and `sent-log.csv` holds 0 J rows, so today the marker is proven at the lint layer only.

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
