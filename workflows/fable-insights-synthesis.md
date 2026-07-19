# fable-insights — Synthesis Protocol

The workflow returns `{facets, stubs, failed, manifest_counts}`; synthesis happens in the ORCHESTRATOR (workflow scripts have no filesystem access). Follow this protocol every run — it encodes what worked in the 2026-07-19 run plus the mechanization bias adopted from the setup design review.

## Artifacts (write all three to `~/.claude/usage-data/`)

1. `fable-facets-weekly-<YYYY-MM-DD>.json` — the raw workflow return, saved verbatim (extract from the task output file's `result` field via python, never by hand).
2. `report-fable-weekly-<YYYY-MM-DD>.html` — self-contained HTML matching the previous report's CSS/section order: header stats → At a glance → Scoreboard by project → deltas vs baseline → standout moments → friction taxonomy → wasted-effort events → recommendations → all-sessions table → micro-sessions → footnote.
3. `PROPOSED_CHANGES-<YYYY-MM-DD>.md` — the action output (rules below).

Delegate the synthesis to ONE fresh-context agent (the facets are ~50K tokens; don't pull them into the main thread). Give it the pre-computed aggregates you extracted with python and require it to recount and flag any disagreement.

## Report rules

- Per-session normalization for baseline comparisons (session counts differ between windows).
- Every aggregate claim carries its denominator ("35 of 37"), per gates.md Coverage Claims.
- Cluster recurring root causes across sessions — one named cluster with N occurrences, not N scattered rows.
- `hook_by_design` friction is a designed tax: report it in its own bucket, never mixed into environment friction.

## PROPOSED_CHANGES rules (mechanization + demotion bias — non-negotiable)

1. **Enforcement form on every proposal**, chosen from: `PreToolUse/PostToolUse hook` | `script` | `CI step` | `skill` | `workflow edit` | `memory` | `prose rule`. Default to a mechanism. `prose rule` requires an explicit "judgment-laden because…" justification. A friction class a regex or exit code could catch MUST NOT be proposed as prose. (Basis: prose compliance decays under momentum — the model-split policy was skipped 3× in one week while sql-guard fired 4/4.)
2. **Rank by occurrences × avoidability**, severity-weighted when one event dominates.
3. **Each proposal**: what happened (session ids), root cause, why any existing measure failed to fire, the fix, enforcement form, effort estimate.
4. **Demotion candidates section**: always-loaded rules/sections with zero related friction AND zero invocations this window → nominate "prune" / "demote to on-demand (`rules-ref/`)" / "keep (insurance)". One week only NOMINATES — say so; act only with a second week of evidence (or a targeted grep of older transcripts).
5. **Dedupe before proposing**: `ls ~/.claude/skills/ ~/.claude/hooks/ ~/.claude/rules-ref/`, read the recurring-quirks memory + QUIRKS.md, and list in-week fixes already landed. If a cluster is already covered, the proposal must be "existing measure failed to fire — why?", never a duplicate measure.

## After the user approves changes

Implement per the Self-Learning Protocol's enforcement-form step (CLAUDE.md): mechanism first. Update META_RULE.md's hook list, README's hook table, and install.sh's script list in the SAME commit as any new hook. Test every new/changed hook with sample JSON inputs (block, allow, override, malformed) BEFORE wiring into settings.json — a broken PreToolUse Bash hook blocks all Bash.
