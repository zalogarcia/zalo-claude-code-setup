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
change is its own test suite (`scripts/note-lint.test.py`, 80 cases) plus
`codex-sync.py all`. If that stops being true, write the manifest.
