# When Stuck — Dispatch Table

Adapted from obra/superpowers-skills `problem-solving/when-stuck`. When you (or a subagent) feel stuck, name the symptom and pick the matching technique. Don't keep retrying the same approach.

## Symptom → Technique Table

| How You're Stuck                                                                     | Technique                                                                                                        |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| **Complexity spiraling** — same thing implemented 5+ ways, growing special-case list | Simplification cascade — find one insight that eliminates 10 things                                              |
| **Need innovation** — conventional solutions inadequate, every option feels wrong    | Collision-zone thinking — combine unrelated domains (e.g., what would game design do? what would networking do?) |
| **Recurring patterns** — same issue appearing in different places                    | Meta-pattern recognition — if 3+ domains show it, abstract the principle                                         |
| **Forced by assumptions** — "must be done this way", "there's only one approach"     | Inversion exercise — what if the opposite were true?                                                             |
| **Scale uncertainty** — what works at 10 fails at 10000 (or vice versa)              | Scale game — design for 10x and 0.1x; pick the right tier                                                        |
| **Code broken** — wrong behavior, test failing                                       | Systematic debugging (4-phase, see `~/.claude/agents/bug-fix.md`)                                                |
| **Multiple independent problems**                                                    | Dispatch parallel agents (see `~/.claude/rules/when-to-parallelize.md`)                                          |
| **Root cause unknown** — symptom clear, cause hidden                                 | Root-cause tracing — instrument component boundaries, trace data flow backward                                   |
| **3+ failed fixes in a row**                                                         | STOP. Question the architecture, not the fix.                                                                    |

## Inversion Exercise (worked example)

Assumption: "Cache to reduce latency."
Inversion: "Add latency to enable caching."
Reveals: debouncing, rate-limit windows, batch flushing.

Pattern: take the "must be" statement, write its opposite, see what becomes visible.

Red flags that mean inversion is needed:

- "There's only one way to do this"
- "This is just how it's done"
- "Everyone does it this way"

## Simplification Cascade (worked example)

Symptom: same thing implemented 5+ ways, growing list of special cases.
Move: find the one insight that makes them all instances of the same case.
Measure: "how many things can we delete?" not "how can we optimize this?"

## Meta-Pattern Recognition (worked example)

Pattern: rate limiting appears in API throttling + traffic shaping + circuit breakers + admission control.
Abstraction: "Bound resource consumption to prevent exhaustion."
New application: LLM token budgets are a rate-limiting problem.

Rule: 3+ domains showing the same shape = likely a universal principle worth naming.

## The 3+ Fixes Rule

If you've tried 3 distinct fixes and the bug still isn't gone:

- **STOP fixing.**
- **Question the architecture.**
- The bug is probably not where you've been looking. The system's shape allows the bug to exist.

This is from `~/.claude/agents/bug-fix.md`'s 4-phase systematic debugging — Phase 4 explicitly halts at 3+ failed fixes.
