# Writing Rules That Current Models Follow

Read this when authoring or revising files in `~/.claude/rules/`, `~/.claude/CLAUDE.md`, agent definitions, or skill bodies. It started as an adaptation of obra/superpowers `writing-skills/persuasion-principles.md`, which recommended authority framing ("YOU MUST", "IMMEDIATELY", "No exceptions"). That advice fit older models that under-followed instructions. Rewritten 2026-09-23 for the models this setup runs (Claude Opus 5.5 and Claude Fable 5.1), which follow the system prompt closely.

## Why the register changed

Current models read every instruction as actionable. Capitals, "CRITICAL" and stacked MUST/NEVER now over-apply: the model gets rigid where a rule does not fit, and when several rules are all marked critical the markers stop carrying information. The prompt's register also becomes the output's register, so an anxious prompt produces a cautious, hedging model. The opposite failure is real too: "try to" or "if possible" attached to an actual requirement is read as permission to skip it.

## How to write a rule

1. **Say exactly what to do, at normal volume, with the reason beside it.** "Stage files by name, because `git add -A` has committed secrets here" beats "NEVER use git add -A!!!". The reason lets the model apply the rule to cases the wording did not foresee.
2. **Requirements are stated as requirements.** "Include a summary." Not "try to include a summary if possible".
3. **Describe the outcome, not a script,** unless order really matters. Keep numbered steps for fragile operations (quoting, migrations, deploy sequences, anything where a skipped or reordered step breaks something) and say why the order matters.
4. **Keep prohibitions for failures that actually happened,** with one clause of provenance ("a subagent's mass revert once wiped 11 sibling agents' work"). A prohibition against a mistake the model was not going to make costs tokens and can anchor it toward that mistake.
5. **Say it once, in the right place.** Duplicated rules drift apart, and the model spends effort reconciling two wordings. Point to the one authoritative copy instead.
6. **State the behavior you want, not a trait.** "Keep responses to the length the question needs", not "you tend to be verbose".

## When emphasis is still right

Emphasis is a tested, scoped fix, not a first-draft register. Use it for the one or two constraints where a single miss causes real damage and you have seen the plain version underweighted. In this setup that is the admin-email-only rule in `testing-safety.md` and the two named central rules in `gates.md` ("NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE" and the measured-denominator rule), which other files cite by name. Everything else stays at normal volume.

## When prose is not enough

If a rule keeps getting skipped, write a mechanism rather than louder prose: a hook, a lint rule, a script, a test. The Self-Learning Protocol in `~/.claude/CLAUDE.md` puts mechanism first because prose compliance decays under momentum while a hook fires every time. Leave at most a one-line pointer to the mechanism in the prose.

## Framing that still helps

- **Collaborative framing** ("we are working on this together; I need your honest technical judgment") helps where honest pushback matters: code review, brainstorming, planning.
- **Explicit commitments** help multi-step procedures: name the agent and the marker you expect before dispatching; track steps in a plan file.
- **Avoid flattery and reciprocity.** They invite sycophancy ("You're absolutely right!") and cost honest feedback.

## Useful construction patterns

- **Red flags list:** phrases that mean the model is rationalizing ("should work", "just this once"). `gates.md` Part 2 has one.
- **Rationalization table:** "What you'll think" and "Reality", for a rule with a known escape route. Use it sparingly and keep each row factual.

## Ethical test

Would this technique serve the user's genuine interests if they fully understood it? If yes, use it. If no, don't.
