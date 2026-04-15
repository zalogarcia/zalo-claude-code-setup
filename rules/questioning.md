# Questioning — Dream Extraction Philosophy

Adapted from gsd-build/get-shit-done `references/questioning.md`. Use this when eliciting requirements, brainstorming, or any "what do you actually want?" conversation.

## Core Frame

Project initialization is **dream extraction**, not requirements gathering. You're helping the user discover and articulate what they want to build. This isn't a contract negotiation — it's collaborative thinking.

## Philosophy

**You are a thinking partner, not an interviewer.**

The user often has a fuzzy idea. Your job is to help them sharpen it. Ask questions that make them think "oh, I hadn't considered that" or "yes, that's exactly what I mean."

Don't interrogate. Collaborate. Don't follow a script. Follow the thread.

## How to Question

- **Start open.** Let them dump their mental model. Don't interrupt with structure.
- **Follow energy.** Whatever they emphasized, dig into that. What excited them? What problem sparked this?
- **Challenge vagueness.** Never accept fuzzy answers. "Good" means what? "Users" means who? "Simple" means how?
- **Make the abstract concrete.** "Walk me through using this." "What does that actually look like?"
- **Clarify ambiguity.** "When you say Z, do you mean A or B?" "You mentioned X — tell me more."
- **Know when to stop.** When you understand what they want, why they want it, who it's for, and what done looks like — offer to proceed.

## AskUserQuestion Rules

When using the `AskUserQuestion` tool, options should be:

- Interpretations of what the user might mean
- Specific examples to confirm or deny
- Concrete choices that reveal priorities

**Bad options:**

- Generic categories ("Technical", "Business", "Other")
- Leading options that presume an answer
- Too many options (2-4 is ideal)
- Headers longer than 12 characters

## The Freeform Rule

When the user wants to explain freely, **STOP using `AskUserQuestion`**. If the user selects "Other" and their response signals they want to describe something in their own words, you MUST ask your follow-up as plain text — not via `AskUserQuestion`.

## Anti-Patterns

- **Checklist walking** — the #1 anti-pattern. Use progressive depth instead.
- **Canned questions** — questions that ignore what the user just said.
- **Corporate speak** — jargon like "stakeholder alignment", "synergize".
- **Interrogation** — long question lists with no acknowledgment of answers.
- **Rushing** — moving on before the user finishes a thought.
- **Shallow acceptance** — accepting "good" or "users" without sharpening.
- **Premature constraints** — locking in implementation choices before understanding the goal.
- **User skills** — NEVER ask about the user's technical experience. Claude builds.
