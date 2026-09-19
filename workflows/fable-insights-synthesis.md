# fable-insights — Synthesis Protocol

The workflow returns `{facets, stubs, failed, coverage, partial_run, sampling, taxonomy_version, manifest_counts, manifest_path, verification}`; synthesis happens in the ORCHESTRATOR (workflow scripts have no filesystem access). Follow this protocol every run: it encodes what worked in the 2026-07-19 run plus the mechanization bias adopted from the setup design review.

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
- **Manifest completeness (no silent truncation):** the report MUST show `manifest_counts.excluded` (id + reason) and `manifest_counts.in_progress_snapshots`. In-progress facets are snapshots — expect them re-analyzed next run; when the same session id appears in consecutive weeks, the NEWER facet supersedes (count the session once in cross-week aggregates). (Basis 2026-07-19: the old drop-all-open rule silently excluded the week's highest-friction session — 39 post-delivery defects invisible to the audit.)
- **Grade the pipeline, not the session (delivery↔validation pairing):** for every facet with a non-empty `validates_prior_work`, pair it with the producing session/run (same window or the prior week's facets file). Count that facet's `post_delivery_defect` friction entries against the DELIVERY, and report the week's **defects-per-autonomous-delivery** (defects / delivery, per delivery and aggregate) in the At-a-glance block. A delivery session graded `fully_achieved` with `deferred_verification: true` gets re-labeled in the report as "achieved-as-scoped / NOT live-verified" whenever its paired validation session logged ≥1 post-delivery defect — the session kept its promise, the pipeline didn't; recommendations must target the pipeline (plan gates, harness, activation runbook), not the session.

## The four honesty rules (added 2026-09-19, after the run that failed its own Verify stage)

The 2026-09-19 run returned `trustworthy: false` on four counts. Each has a rule here, and each rule is about what the REPORT must say, not only about what the workflow computes.

- **Print the sampling bias verbatim, above the numbers.** `sampling.bias_statement` goes in the report header, not a footnote, whenever `sampling.method` is not `census`. Every week-level figure drawn from a stratified run is labelled with `coverage.sample_coverage_pct` and its denominator (`coverage.substantive_population`), and any count taken from the mid or light band is multiplied by that stratum's `weight` before it is called a week total. A run whose header does not carry the bias statement is not publishable: the 2026-09-19 report presented the 80 longest sessions of 297 as if they were the week.
- **Show the reconciliation, not just the counts.** Print `manifest_counts.candidate_total` against `manifest_counts.accounted_total`. If `reconciliation_ok` is false, or `folded_exclusions` is non-empty, that goes in the FIRST paragraph of the report with the size of the gap: a record standing in for a group is the failure that made `trivial` read 141 when it was 373. `manifest_counts.trivial_clusters` is a count that survived, not a drop: report each cluster's group and full count, and say that only its representatives were gisted.
- **Do not compute friction deltas across a taxonomy change.** `taxonomy_version` is in the return. v1 weeks (2026-07-19 through 2026-09-19) and v2 weeks share the ten original types but v2 adds ten more, which draw mass mostly out of `other` and some out of `environment` and `wrong_approach`. Across that boundary compare only: the `other` RATE, total friction per session, and types unchanged in definition. Say in the report which side of the boundary each compared week is on.
- **verification_quality is derived, so report its inputs.** It is computed from `done_claims` and `done_claims_with_fresh_evidence` per facet and repaired when a row logs an `overclaimed_verification` friction while claiming every claim was evidenced. Report the distribution, the two totals, and the repair count. A non-zero repair count is itself a finding about the analyst fleet, not a footnote. (2026-09-19: the judged version answered `ground_truth` on 79 of 80 rows while 17 of 17 overclaim frictions sat inside those same rows.)

## PROPOSED_CHANGES rules (mechanization + demotion bias — non-negotiable)

1. **Enforcement form on every proposal**, chosen from: `PreToolUse/PostToolUse hook` | `script` | `CI step` | `skill` | `workflow edit` | `memory` | `prose rule`. Default to a mechanism. `prose rule` requires an explicit "judgment-laden because…" justification. A friction class a regex or exit code could catch MUST NOT be proposed as prose. (Basis: prose compliance decays under momentum — the model-split policy was skipped 3× in one week while sql-guard fired 4/4.)
2. **Rank by occurrences × avoidability**, severity-weighted when one event dominates.
3. **Each proposal**: what happened (session ids), root cause, why any existing measure failed to fire, the fix, enforcement form, effort estimate.
4. **Demotion candidates section**: always-loaded rules/sections with zero related friction AND zero invocations this window → nominate "prune" / "demote to on-demand (`rules-ref/`)" / "keep (insurance)". One week only NOMINATES — say so; act only with a second week of evidence (or a targeted grep of older transcripts).
5. **Dedupe before proposing**: `ls ~/.claude/skills/ ~/.claude/hooks/ ~/.claude/rules-ref/`, read the recurring-quirks memory + QUIRKS.md, and list in-week fixes already landed. If a cluster is already covered, the proposal must be "existing measure failed to fire — why?", never a duplicate measure.

## After the user approves changes

Implement per the Self-Learning Protocol's enforcement-form step (CLAUDE.md): mechanism first. Update META_RULE.md's hook list, README's hook table, and install.sh's script list in the SAME commit as any new hook. Test every new/changed hook with sample JSON inputs (block, allow, override, malformed) BEFORE wiring into settings.json — a broken PreToolUse Bash hook blocks all Bash.
