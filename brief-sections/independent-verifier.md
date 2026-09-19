# Brief section: independent verifier

Paste **Part A** and **Part B** below, verbatim, into any background worker brief that
delivers something. Part A is filled in by whoever writes the brief. Part B is copied in
untouched, slots empty, and is filled in by the worker at the end of its run.

## Why this section exists (the number)

A weekly self audit of this setup found 63 of 80 analysed sessions were the owner live
testing an earlier autonomous delivery, and those 63 sessions carry 83 of the 89 recorded
post delivery defects: 1.32 real defects per session, found by hand, after a worker had
already said "done". A worker cannot verify its own work. It has the same context and the
same blind spot, and it has already decided the thing works. So the verification comes
from a separate agent with fresh context, dispatched at the end of the run.

This is already the stated policy in `~/.claude/rules/plan-verification.md` ("don't
substitute self-critique for fresh-context dispatch") and in the `~/.claude/CLAUDE.md`
model policy ("the model that verifies should differ from the model that authored"). This
file is that policy in the one shape a model reliably carries to the end of a long run: a
self delimiting section with named slots and a closing checklist that names every slot.
Measured on this setup 2026-09-18 and again 2026-09-19: a prohibition, or a rule quoted
as a loose sentence, is dropped by generation. A section with slots is not.

## How the brief writer uses it

1. Fill Part A. Every criterion needs an observable result and the shape of the proof.
   Name the repo's `.claude/VERIFY.md` and the surfaces this delivery touches; the
   verifier reads VERIFY.md and picks the command. If the repo has no VERIFY.md, say so:
   that is itself a finding, and `/repo-init` is the fix.
2. Paste Part B with the slots left empty exactly as printed. The empty values are load
   bearing: a slot with no default gets invented content.
3. The bridge reads the finished report for the Part B block. A report claiming a delivery
   with no block, or with a verdict that contradicts its own headline, is delivered with a
   banner on it (`worker-verifier-guard.mjs` in `~/dev/claude-telegram-bridge`). The
   banner is a nudge, not a block: the report still arrives in full.

---

## Part A: Acceptance criteria (paste into the brief, filled in)

````markdown
## Acceptance criteria

These are the criteria the independent verifier will be handed verbatim. They are written
here, before the work starts, by the person who wants the work, so the worker is not the
author of its own passing grade.

| # | Criterion (observable, not "the code exists") | What would prove it | Expected result |
|---|-----------------------------------------------|---------------------|-----------------|
| 1 |                                               |                     |                 |
| 2 |                                               |                     |                 |

Repo: <path>
VERIFY.md: <path to the repo's `.claude/VERIFY.md`, or `none, this repo has no VERIFY.md`>
Surfaces this touches: <the deploy surfaces, named the way VERIFY.md names them, or `none`>
Live surface: <URL, port, phone number, or `none, this delivery has no live surface`>
Credentials the verifier needs: <names only, never values, or `none`>

The "What would prove it" column is the SHAPE of the proof (a green ECS deploy for this
service, a real inbound call that books, 43 scenarios passing), not the command. The
verifier chooses the command itself, from `.claude/VERIFY.md`. See Part B for why.
````

---

## Part B: Independent verifier (paste into the brief verbatim, slots empty)

````markdown
## Independent verifier (the last step of your run, before you write your report)

Your run ends with ONE dispatch to a fresh context agent, and its verdict goes in your
report word for word. Pick the agent by surface:

- A live UI or browser surface (a page renders, a button works, a form submits) goes to
  `live-test`. Its markers are `## UI VERIFIED` / `## UI ISSUES FOUND` / `## BLOCKED`.
- Code behaviour, data correctness, wiring, migrations, API responses go to `qa-agent`.
  Its markers are `## VERIFICATION PASSED` / `## ISSUES FOUND` / `## BLOCKED`.
- Both surfaces in one delivery: dispatch both, paste both blocks.

Dispatch them by name and nothing else. Their model pins live in their own frontmatter
(`~/.claude/CLAUDE.md` model policy); re-pinning a model in the prompt overrides the split
that makes the verifier a different model from the author. Their return contract,
including what each marker means, is `~/.claude/rules/agent-contracts.md`. Read it before
you dispatch.

### The dispatch prompt has exactly three parts

Build it from these three and stop. Everything you would naturally add is the blind spot
you are trying to escape: your narrative, your summary of what you changed, your
description of the diff, your list of what you already tested, and any sentence claiming
something works. A verifier that reads your conclusion inherits your conclusion, and then
two agents believe the same wrong thing instead of one.

1. **The acceptance criteria, verbatim**, copied from the Acceptance criteria section of
   this brief. You did not author them; do not reword, reorder, narrow or annotate them.
2. **The repo path and the path to its `.claude/VERIFY.md`**, plus the surfaces this
   delivery touches, named the way VERIFY.md names them. Not a command.
3. **This instruction, verbatim**:

   "Read the repo's `.claude/VERIFY.md` FIRST. For each surface named above, find the
   proof signal VERIFY.md requires for that surface and run THAT. Only if VERIFY.md names
   nothing for a surface do you derive a check from the acceptance criteria, and when you
   do, say so explicitly in your return under 'VERIFY.md gap', naming the surface, because
   that is a hole in VERIFY.md worth closing. Choose every command yourself before you
   read anything the worker says about what it ran. Run each command yourself. Paste the
   raw output including the exit code, plus the run id, deploy id or call id where the
   proof has one. Judge each criterion against its expected result only. If a command
   cannot run, say which one and why, and do not grade that criterion. Emit your contract
   marker."

### Why you do not hand the verifier a command

You may add, AFTER the three parts and under a heading that says exactly what it is
("Context, read this only after you have chosen your own checks"), the commands you ran
yourself. Never above, never as the instruction.

The reason is measured, on the same 89 post delivery defects. 51 of them were overclaims,
and 29 were log checkable: the report named a gate or a number the tool log did not
contain, which a guard can catch. The other 22 were **semantically wrong proofs**: a real
command ran green and proved the wrong thing. Nothing downstream can catch those, because
every artifact looks correct. The only thing that catches a wrong proof is a second agent
choosing the proof independently. Hand it your command and it runs your command, green,
and the wrong thing is proved twice.

Same measurement, the other half: 46 of the 89 defects were rig class, meaning no static
signature and a live check would have caught them, and 31 of those 46 were catchable by an
instrument that ALREADY EXISTS on this Mac (a synthetic caller rig, the traffic harness,
the GPT-Live call rig, `check.sh`, the `live-test` agent) and the producing run simply did
not run it. That is what `.claude/VERIFY.md` is for and why the verifier reads it first:
the bottleneck is not missing tooling, it is that the run which ships is not required to
run the thing that would have caught it.

### What the verifier owes you

Raw output, including the exit code, for every command it ran, and its own contract
marker. A verifier that returns "looks correct", "the implementation appears complete" or
a summary with no command output has not verified anything: re-dispatch it once with the
instruction above quoted, and if the second return is also bare, record that in the
`Could not verify because:` slot.

### One re-verify, then report honestly either way

A failing verdict gets ONE fix and ONE re-verify. After that you report what you have,
failing verdict included. Do not suppress it, do not summarise it away, do not soften it,
do not re-run the verifier hoping for a different answer. A delivery that lands labelled
broken is worth more than one that lands labelled done and is found broken by hand a day
later, which is the 1.32 defects per session this section exists to stop.

### Paste this block into your report, with every slot filled

## INDEPENDENT VERIFIER

Verifier agent: none
Criteria handed over: none
Proof source: none
Proof command (chosen by the verifier): none
Proof run id: none
Verdict marker: ## VERIFIER COULD NOT RUN
Raw output (verbatim, with exit code):
```
none
```
Re-verify: not needed
VERIFY.md gap: none
Could not verify because: n/a

### Closing checklist, run it before you send your report

Every one of these is a line in the block above. Read your own report and confirm each:

- [ ] `## INDEPENDENT VERIFIER` heading is present in the report.
- [ ] `Verifier agent:` names `qa-agent` or `live-test`, not `none`, unless the
      `Could not verify because:` slot says why.
- [ ] `Criteria handed over:` lists the criterion numbers you pasted verbatim.
- [ ] `Proof source:` is `.claude/VERIFY.md: <signal name>` when VERIFY.md named one, or
      `derived from criteria, VERIFY.md names nothing for <surface>` when it did not.
- [ ] `Proof command (chosen by the verifier):` is the command the VERIFIER picked and ran,
      not one you handed it and not a description of it.
- [ ] `Proof run id:` is the run id, deploy id, call id or workflow id the proof produced,
      or `none, this proof has no id`. This is what makes "which rig proved this"
      answerable next week.
- [ ] `Verdict marker:` is the marker the verifier actually emitted, copied character for
      character: `## VERIFICATION PASSED`, `## ISSUES FOUND`, `## UI VERIFIED`,
      `## UI ISSUES FOUND`, `## BLOCKED`, or `## VERIFIER COULD NOT RUN`.
      `## VERIFIER COULD NOT RUN` is this report's own slot, not an agent marker: use it
      only when no verifier ran at all.
- [ ] `Raw output` is the verifier's pasted command output with its exit code, not your
      paraphrase of it.
- [ ] `Re-verify:` is one of `not needed`, `passed on re-verify`, `still failing`.
- [ ] `VERIFY.md gap:` is `none`, or the surface VERIFY.md names no proof signal for. A gap
      here is a repo fix worth reporting to the owner, not a footnote.
- [ ] `Could not verify because:` is `n/a`, or one sentence naming the missing surface or
      credential.
- [ ] Your report's opening lines and the `Verdict marker:` line say the same thing. If
      the marker is `## ISSUES FOUND`, `## UI ISSUES FOUND`, `## BLOCKED` or
      `## VERIFIER COULD NOT RUN`, your opening lines do not say shipped, live, deployed
      or verified.
````

---

## Worked example of the finished block

````markdown
## INDEPENDENT VERIFIER

Verifier agent: qa-agent
Criteria handed over: 1, 2, 3 (verbatim from the brief)
Proof source: .claude/VERIFY.md: "bridge module change: the module's own suite plus bg-reports.test.mjs"
Proof command (chosen by the verifier): cd ~/dev/claude-telegram-bridge && node worker-verifier-guard.test.mjs && node bg-reports.test.mjs
Proof run id: none, this proof has no id
Verdict marker: ## VERIFICATION PASSED
Raw output (verbatim, with exit code):
```
48 passed, 0 failed
30 passed, 0 failed
EXIT=0
```
Re-verify: not needed
VERIFY.md gap: none
Could not verify because: n/a
````
