# Persuasion Principles for Writing Rules

Adapted from obra/superpowers `writing-skills/persuasion-principles.md`. Reference when authoring or revising files in `~/.claude/rules/`, `~/.claude/CLAUDE.md`, agent definitions, or skill bodies.

## Why This Matters

LLMs respond to the same persuasion principles as humans. Meincke et al. (2025) tested 7 persuasion principles with N=28,000 AI conversations — persuasion techniques **more than doubled compliance rates** (33% → 72%, p < .001).

Bright-line rules reduce rationalization. Implementation intentions create automatic behavior. Use these deliberately when you need a rule to actually be followed.

## The Five Usable Principles

### 1. Authority — for discipline-enforcing rules

Imperative language ("YOU MUST", "Never", "Always"), non-negotiable framing, eliminates decision fatigue.

> Example: "Write code before test? Delete it. Start over. No exceptions."

Use for: TDD, verification gates, security boundaries, anything where one violation breaks the system.

### 2. Commitment — for procedural rules

Require announcements, force explicit choices, use tracking (`TaskCreate`).

> Example: "Before dispatching a subagent, name the agent and the marker you expect."

Use for: handoff protocols, multi-step procedures.

### 3. Scarcity — for sequencing rules

Time-bound requirements ("Before proceeding"), sequential dependencies ("Immediately after X").

> Example: "After completing a task, IMMEDIATELY request review before starting the next."

Use for: ordering, freshness requirements ("in this turn"), preventing batching that loses context.

### 4. Social Proof — for universal patterns

Universal patterns ("Every time", "Always"), failure modes ("X without Y = failure").

> Example: "Checklists without TaskCreate tracking = steps get skipped. Every time."

Use for: rules that look optional but always backfire when skipped.

### 5. Unity — for collaborative framing

Collaborative language ("our codebase", "we're working together").

> Example: "We're colleagues working on this together. I need your honest technical judgment."

Use for: code review, brainstorming, anywhere honest pushback matters.

## Avoid

- **Liking** — conflicts with honest feedback culture, creates sycophancy. ("You're absolutely right!" — forbidden.)
- **Reciprocity** — feels manipulative when overused.

## Principle Combinations by Rule Type

| Rule Type                                    | Use                                   | Avoid               |
| -------------------------------------------- | ------------------------------------- | ------------------- |
| Discipline-enforcing (TDD, verify, security) | Authority + Commitment + Social Proof | Liking, Reciprocity |
| Guidance / technique                         | Moderate Authority + Unity            | Heavy authority     |
| Collaborative process                        | Unity + Commitment                    | Authority, Liking   |
| Reference doc                                | Clarity only                          | All persuasion      |

## Construction Patterns

**Iron Law block:** Boxed all-caps rule + "no exceptions" list + rationalization table + red flags list. See `~/.claude/rules/gates.md` Part 2 for an example.

**Rationalization Table:** Two columns — "What you'll think" / "Reality." Pre-empts each escape route the model would take.

**Red Flags List:** Trigger phrases that mean "STOP — you're rationalizing." See `~/.claude/rules/gates.md`.

**Anti-rationalization counter:** "Violating the letter is violating the spirit." Closes the "I'm being pragmatic" loophole.

## Ethical Test

Would this technique serve the user's genuine interests if they fully understood it? If yes, use it. If no, don't.
