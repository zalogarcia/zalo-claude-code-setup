#!/usr/bin/env node
// Tests for ~/.claude/workflows/fable-insights.js
//
// The workflow source is wrapped in an async function with stubbed workflow
// globals, so the real control flow runs offline against scripted agent
// outcomes. No agent, no token, no filesystem.
//
// Run:  node ~/.claude/workflows/fable-insights.test.mjs
//
// What this file gates (2026-09-19, the four defects the workflow's own Verify
// stage returned trustworthy:false over):
//   - selection states its own bias, and a sampled run is never called complete
//   - the manifest's counts reconcile, and a folded record is loud, not silent
//   - the friction taxonomy carries the categories the `other` bucket revealed
//   - verification_quality is derived from counts and cannot contradict the
//     friction log in its own row
// plus the run-integrity properties that were already right:
//   - a dead analyzer carries an error class and both attempts
//   - a dead agent is retried once on the other model tier
//   - stub batches run BEFORE the analysis wave and get a rescue pass
//   - coverage is reported against stated denominators

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.join(HERE, "fable-insights.js"), "utf8");
const BODY = SRC.replace(/^export const/m, "const");

const parallelStub = async (thunks) =>
  Promise.all(
    thunks.map((t) =>
      Promise.resolve()
        .then(() => t())
        .catch(() => null),
    ),
  );

const pipelineStub = async (items, ...stages) =>
  Promise.all(
    items.map(async (item, i) => {
      let acc = item;
      for (const s of stages) {
        try {
          acc = await s(acc, item, i);
        } catch {
          return null;
        }
      }
      return acc;
    }),
  );

function runWorkflow({ agentFn, args }) {
  const logs = [];
  const prompts = [];
  const wrapped = async (prompt, opts) => {
    prompts.push({ prompt, opts });
    return agentFn(prompt, opts);
  };
  const fn = new Function(
    "agent",
    "parallel",
    "pipeline",
    "log",
    "phase",
    "args",
    `return (async () => {\n${BODY}\n})();`,
  );
  const promise = fn(
    wrapped,
    parallelStub,
    pipelineStub,
    (m) => logs.push(String(m)),
    () => {},
    args,
  );
  return { logs, prompts, promise };
}

const session = (id, over = {}) => ({
  id,
  path: `/tmp/${id}.jsonl`,
  transcript_dir: "dev",
  start: "2026-09-14",
  last_activity: "2026-09-18",
  lines: 500,
  bytes: 900000,
  user_msgs: 10,
  typed_msgs: 10,
  repos_touched: ["delta-agents"],
  primary_repo: "delta-agents",
  in_progress: false,
  carried_over: false,
  ...over,
});

const FACET = {
  goal: "ship the thing",
  outcome: "fully_achieved",
  outcome_evidence: "deploy green",
  satisfaction: "satisfied",
  session_type: "deploy_ship",
  friction: [],
  done_claims: 2,
  done_claims_with_fresh_evidence: 2,
  verification_evidence: "ECS image tag matched the pushed SHA",
  brief_summary: "shipped",
  validates_prior_work: "",
  deferred_verification: false,
};

function manifestOf(selected, over = {}) {
  const substantive = over.substantive_count ?? selected.length;
  return {
    generated_on: "2026-09-19",
    window_start: "2026-09-12",
    window_end: "2026-09-19",
    manifest_path: "/tmp/manifest-7d-2026-09-19.json",
    candidate_total: substantive + (over.trivial_count ?? 0),
    accounted_total: substantive + (over.trivial_count ?? 0),
    substantive_count: substantive,
    trivial_count: over.trivial_count ?? 0,
    selected,
    not_selected_ids: [],
    stub_target_count: over.stub_target_count ?? 0,
    trivial_clusters: [],
    excluded: [],
    script_error: "",
    sampling: {
      method: "census",
      population: substantive,
      selected: selected.length,
      coverage_pct: 100,
      seed: "2026-09-19",
      strata: [],
      bias_statement: "Census: every substantive session in the window was analysed.",
    },
    ...over,
  };
}

let pass = 0;
let fail = 0;
function check(name, cond, detail) {
  if (cond) {
    pass += 1;
    console.log(`  ok   ${name}`);
  } else {
    fail += 1;
    console.log(`  FAIL ${name}${detail ? ` :: ${detail}` : ""}`);
  }
}

console.log("fable-insights.js");

// 1. Full census run: dates come from last_activity, coverage is complete.
{
  const seen = [];
  const agentFn = async (prompt, opts) => {
    seen.push(opts.label);
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1"), session("bbbbbbbb-2")], {
        trivial_count: 1,
        stub_target_count: 1,
      });
    if (opts.label.startsWith("stubs:"))
      return {
        sessions: [
          { session_id: "cccccccc-3", gist: "asked a thing", category: "quick_question" },
        ],
      };
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, logs } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  check("full census run is complete", out.coverage.complete === true, JSON.stringify(out.coverage));
  check("full census run is not flagged partial", out.partial_run === false);
  check("true coverage is 100%", out.coverage.true_coverage_pct === 100);
  check("sample coverage is 100% on a census", out.coverage.sample_coverage_pct === 100);
  check(
    "facet date uses last_activity, with the first-message date kept as provenance",
    out.facets[0].date === "2026-09-18" && out.facets[0].started_on === "2026-09-14",
    JSON.stringify({ date: out.facets[0].date, started_on: out.facets[0].started_on }),
  );
  check(
    "stubs run before the analysis wave",
    seen.indexOf("stubs:batch1") < seen.findIndex((l) => l.startsWith("analyze:")),
    seen.join(","),
  );
  check(
    "window is carried into the return",
    out.manifest_counts.window_start === "2026-09-12" &&
      out.manifest_counts.window_end === "2026-09-19",
  );
  check("manifest path is carried into the return", out.manifest_path.includes("manifest-7d"));
  check("no PARTIAL RUN line on a clean census", !logs.some((l) => l.startsWith("PARTIAL RUN:")));
}

// 2. An analyzer dead on both tiers: the placeholder carries the error class and
//    both attempts, and the run reports itself partial.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1"), session("bbbbbbbb-2")]);
    if (opts.label.includes("aaaaaaaa"))
      throw new Error("Claude AI usage limit reached for this session");
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const out = await runWorkflow({ agentFn, args: { days: 7 } }).promise;
  const dead = out.facets.find((f) => f.failed);
  check("dead analyzer produces a placeholder", Boolean(dead));
  check("placeholder carries the error class", dead.error_class.includes("usage_limit"), dead.error_class);
  check("placeholder records both attempts", dead.attempts.length === 2, JSON.stringify(dead.attempts));
  check("run is flagged partial", out.partial_run === true);
  check("facet coverage is halved", out.coverage.facet_coverage_pct === 50, `${out.coverage.facet_coverage_pct}`);
  check("failed list names the session", out.failed.includes("aaaaaaaa-1"));
}

// 3. An analyzer that dies on the primary model but recovers on the fallback.
{
  let attempts = 0;
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest")) return manifestOf([session("aaaaaaaa-1")]);
    if (opts.label.includes("aaaaaaaa")) {
      attempts += 1;
      if (attempts === 1) return null;
      return { ...FACET };
    }
    return null;
  };
  const out = await runWorkflow({ agentFn, args: { days: 7 } }).promise;
  check("dead analyzer is retried once", attempts === 2, `${attempts}`);
  check("recovered analyzer yields a real facet", out.facets[0].failed === undefined);
  check("recovery is labelled with the fallback model", out.facets[0].analyzed_by === "fable", out.facets[0].analyzed_by);
  check("recovered run is complete", out.coverage.complete === true);
}

// 4. Stub batch dies on both tiers, the small-batch rescue pass covers it.
//    (2026-08-28: all 5 batches died and 43 of 43 trivial sessions were lost.)
{
  const seen = [];
  const agentFn = async (prompt, opts) => {
    seen.push(opts.label);
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1")], { trivial_count: 4, stub_target_count: 4 });
    if (opts.label.startsWith("stubs:batch")) return null;
    if (opts.label.startsWith("stubs:rescue")) {
      const m = prompt.match(/stub_targets'\]\[(\d+):(\d+)\]/);
      const ids = [];
      for (let i = Number(m[1]); i < Number(m[2]); i += 1) ids.push(`tttttttt-${i}`);
      return { sessions: ids.map((id) => ({ session_id: id, gist: "g", category: "machine_lane" })) };
    }
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const out = await runWorkflow({ agentFn, args: { days: 7 } }).promise;
  check("rescue pass ran", seen.some((l) => l.startsWith("stubs:rescue")), seen.join(","));
  check("rescue recovered every trivial session", out.stubs.length === 4, `${out.stubs.length}`);
  check("stub coverage is 100% after rescue", out.coverage.stub_coverage_pct === 100);
  check("stub failures are recorded for diagnosis", out.manifest_counts.stub_failures.length > 0);
}

// 5. Stubs lost for good: coverage says so loudly and they land in `failed`.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1")], { trivial_count: 2, stub_target_count: 2 });
    if (opts.label.startsWith("stubs:")) return null;
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, logs } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  check("lost stubs make the run partial", out.partial_run === true);
  check("stub coverage is 0%", out.coverage.stub_coverage_pct === 0);
  check(
    "true coverage counts stubs in the denominator",
    out.coverage.true_coverage_pct === 33.3,
    `${out.coverage.true_coverage_pct}`,
  );
  check("lost stubs are counted, not dropped", out.coverage.stub_denominator === 2 && out.coverage.stubs === 0);
  check("a PARTIAL RUN line is logged", logs.some((l) => l.startsWith("PARTIAL RUN:")), logs.join(" | ").slice(0, 200));
}

// 6. DEFECT 1: a sampled run states its bias, is never called complete, and
//    names what it did not look at.
{
  const selected = [session("aaaaaaaa-1"), session("bbbbbbbb-2")];
  const sampling = {
    method: "stratified",
    population: 10,
    selected: 2,
    coverage_pct: 20,
    seed: "2026-09-19",
    strata: [
      { name: "deep", population: 4, drawn: 1, weight: 4, draw: "census of the band" },
      { name: "mid", population: 3, drawn: 1, weight: 3, draw: "seeded random" },
      { name: "light", population: 3, drawn: 0, weight: null, draw: "seeded random" },
    ],
    bias_statement:
      "STRATIFIED SAMPLE, NOT A CENSUS: 2 of 10 substantive sessions (20%). The deep band is a census and is over-represented by design.",
  };
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf(selected, {
        substantive_count: 10,
        sampling,
        not_selected_ids: ["s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10"],
      });
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, logs } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  check("a sampled run is NOT complete even with zero failures", out.coverage.complete === false);
  check("a sampled run is flagged partial", out.partial_run === true);
  check("sample coverage names the real denominator", out.coverage.sample_coverage_pct === 20, `${out.coverage.sample_coverage_pct}`);
  check("substantive population is carried, not the sample size", out.coverage.substantive_population === 10);
  check("the bias statement is in the returned output", String(out.sampling.bias_statement).includes("NOT A CENSUS"));
  check("the bias statement is logged where a human reads it", logs.some((l) => l.startsWith("SAMPLING:") && l.includes("NOT A CENSUS")), logs.join(" | ").slice(0, 300));
  check("the unanalysed sessions are named, not silently dropped", out.manifest_counts.skipped_ids.length === 8);
  check("skipped_by_sampling reconciles with the population", out.manifest_counts.skipped_by_sampling === 8);
  check("the PARTIAL RUN line states the sample coverage", logs.some((l) => l.startsWith("PARTIAL RUN:") && l.includes("20%")), logs.filter((l) => l.startsWith("PARTIAL RUN:")).join(""));
}

// 7. DEFECT 2a: counts that do not reconcile are loud and make the run partial.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1")], {
        candidate_total: 671,
        accounted_total: 439,
        substantive_count: 1,
        trivial_count: 141,
        stub_target_count: 0,
      });
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, logs } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  check("a reconciliation gap is logged loudly", logs.some((l) => l.startsWith("MANIFEST RECONCILIATION FAILED")), logs.join(" | ").slice(0, 200));
  check("the gap is quantified in the log", logs.some((l) => l.includes("232 sessions are unexplained")), logs.filter((l) => l.startsWith("MANIFEST")).join(""));
  check("a reconciliation gap makes the run partial", out.partial_run === true);
  check("reconciliation_ok is false in the return", out.manifest_counts.reconciliation_ok === false);
  check("both totals survive into the return", out.manifest_counts.candidate_total === 671 && out.manifest_counts.accounted_total === 439);
}

// 8. DEFECT 2b: a record that stands in for a group is detected as a fold.
//    This is the literal 2026-09-19 shape.
{
  const folded = {
    id: "dev-claude-telegram-bridge-devi-watch-scratch/* (232 transcripts)",
    reason:
      "DEVIATION FROM SPEC, DISCLOSED: these 232 candidates classify as trivial but the full manifest exceeded this response's output-token limit",
  };
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1")], { excluded: [folded] });
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, logs } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  check("a folded exclusion is detected", out.manifest_counts.folded_exclusions.length === 1, JSON.stringify(out.manifest_counts.folded_exclusions));
  check("the fold is logged loudly", logs.some((l) => l.startsWith("MANIFEST FOLD DETECTED")), logs.join(" | ").slice(0, 200));
  check("a fold makes the run partial", out.partial_run === true);
  check(
    "a real session id is not mistaken for a fold",
    (() => {
      const uuid = "a28c8821-c2be-4986-9e46-5094bab0f9f6";
      return !out.manifest_counts.folded_exclusions.some((e) => e.id === uuid);
    })(),
  );
}

// 9. DEFECT 2c: machine-lane clusters keep their full count on the way through.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("aaaaaaaa-1")], {
        trivial_count: 373,
        stub_target_count: 2,
        trivial_clusters: [
          {
            group: "dev-claude-telegram-bridge-devi-watch-scratch ~10 lines",
            count: 232,
            represented_by: ["r1", "r2"],
          },
        ],
      });
    if (opts.label.startsWith("stubs:"))
      return {
        sessions: [
          { session_id: "r1", gist: "poller", category: "machine_lane" },
          { session_id: "r2", gist: "poller", category: "machine_lane" },
        ],
      };
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const out = await runWorkflow({ agentFn, args: { days: 7 } }).promise;
  check("the trivial count is the true count, not the gisted count", out.manifest_counts.trivial === 373);
  check("the cluster and its size survive into the return", out.manifest_counts.trivial_clusters[0].count === 232);
  check("only the representatives were gisted", out.coverage.stub_denominator === 2 && out.stubs.length === 2);
}

// 10. DEFECT 3: the taxonomy carries the categories the `other` bucket revealed.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest")) return manifestOf([session("aaaaaaaa-1")]);
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, prompts } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  const analyze = prompts.find((p) => p.opts.label.startsWith("analyze:"));
  const enumValues = analyze.opts.schema.properties.friction.items.properties.type.enum;
  const added = [
    "schema_guess",
    "shell_or_edit_mechanics",
    "gate_or_test_defect",
    "stale_fact_inherited",
    "self_inflicted_regression",
    "harness_limitation",
    "concurrency_collision",
    "unverified_number",
    "owner_visible_side_effect",
    "preexisting_product_defect",
  ];
  check("every proposed category is in the facet schema enum", added.every((t) => enumValues.includes(t)), JSON.stringify(enumValues));
  check("the v1 types are all still there", ["claude_bug", "overclaimed_verification", "tooling_breakage", "usage_limit", "wrong_approach", "environment", "user_change_of_mind", "hook_by_design", "post_delivery_defect", "other"].every((t) => enumValues.includes(t)));
  check("every category is defined for the analyst in the prompt", added.every((t) => analyze.prompt.includes(t + " =")), added.filter((t) => !analyze.prompt.includes(t + " =")).join(","));
  check("the taxonomy version is returned so deltas are not computed across the change", out.taxonomy_version === 2, `${out.taxonomy_version}`);
  check("the verifier is given the pinned list to check against", prompts.some((p) => p.opts.label === "verify:aggregate" && p.prompt.includes("schema_guess")));
}

// 11. DEFECT 4: verification_quality is derived from counts and cannot
//     contradict the friction log in its own row.
{
  const rows = [
    { name: "no claims at all", facet: { done_claims: 0, done_claims_with_fresh_evidence: 0 }, expect: "none_needed", repaired: false },
    { name: "every claim evidenced", facet: { done_claims: 3, done_claims_with_fresh_evidence: 3 }, expect: "ground_truth", repaired: false },
    { name: "some evidenced", facet: { done_claims: 4, done_claims_with_fresh_evidence: 1 }, expect: "partial", repaired: false },
    { name: "none evidenced", facet: { done_claims: 2, done_claims_with_fresh_evidence: 0 }, expect: "claimed_only", repaired: false },
    {
      name: "ground_truth contradicted by its own overclaim friction",
      facet: {
        done_claims: 2,
        done_claims_with_fresh_evidence: 2,
        friction: [{ type: "overclaimed_verification", detail: "d", root_cause: "r", avoidable: true }],
      },
      expect: "partial",
      repaired: true,
    },
    {
      name: "evidenced above claims is clamped",
      facet: { done_claims: 1, done_claims_with_fresh_evidence: 9 },
      expect: "ground_truth",
      repaired: true,
    },
  ];
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf(rows.map((r, i) => session(`row${i}-aaaa`)));
    if (opts.label.startsWith("analyze:")) {
      const i = Number(opts.label.match(/row(\d)/)[1]);
      return { ...FACET, friction: [], ...rows[i].facet };
    }
    return null;
  };
  const { promise, logs } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  for (const r of rows) {
    const f = out.facets.find((x) => x.session_id.startsWith(`row${rows.indexOf(r)}-`));
    check(`verification_quality: ${r.name}`, f.verification_quality === r.expect, `${f.verification_quality} wanted ${r.expect}`);
    check(`  repair flag: ${r.name}`, Boolean(f.verification_quality_repaired) === r.repaired, f.verification_quality_repaired);
  }
  check(
    "no row can be ground_truth while logging an overclaim",
    !out.facets.some((f) => f.verification_quality === "ground_truth" && (f.friction || []).some((x) => x.type === "overclaimed_verification")),
  );
  check("the derivation inputs travel with the verdict", out.facets[1].verification_quality_derived_from.done_claims === 3);
  check("repairs are logged", logs.some((l) => l.includes("repaired mechanically")), logs.join(" | ").slice(0, 200));
  check("the analyst is not asked to judge verification_quality", !Object.keys(FACET).includes("verification_quality"));
}

// 12. DEFECT 4b: the useless `project` field is gone; repo attribution is
//     mechanical and comes from the manifest, not from the analyst.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([
        session("aaaaaaaa-1", { transcript_dir: "dev", repos_touched: ["delta-agents", "claude-telegram-bridge"], primary_repo: "delta-agents" }),
      ]);
    if (opts.label.startsWith("analyze:")) return { ...FACET, project: "dev" };
    return null;
  };
  const { promise, prompts } = runWorkflow({ agentFn, args: { days: 7 } });
  const out = await promise;
  const analyze = prompts.find((p) => p.opts.label.startsWith("analyze:"));
  check("the facet schema has no analyst-supplied project field", !Object.keys(analyze.opts.schema.properties).includes("project"));
  check("primary_repo is attached from the manifest", out.facets[0].primary_repo === "delta-agents");
  check("repos_touched is attached from the manifest", out.facets[0].repos_touched.length === 2);
  check("the transcript directory is kept as provenance only", out.facets[0].transcript_dir === "dev");
  check("the analyst is told not to return a repo field", analyze.prompt.includes("Do NOT return a project or repo field"));
  check("the verifier sees repo spread, not the directory slug", prompts.some((p) => p.opts.label === "verify:aggregate" && p.prompt.includes("primary_repos")));
}

// 13. carried_over sessions are kept and flagged, not dropped or re-dated.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest"))
      return manifestOf([session("old-1", { start: "2026-09-05", last_activity: "2026-09-17", carried_over: true })]);
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const out = await runWorkflow({ agentFn, args: { days: 7 } }).promise;
  check("carried-over session is kept", out.facets.length === 1);
  check("carried-over session is dated by last activity", out.facets[0].date === "2026-09-17");
  check("carried-over session keeps its true start", out.facets[0].started_on === "2026-09-05");
  check("carried-over ids are reported", out.manifest_counts.carried_over_ids.includes("old-1"));
}

// 14. Manifest dead on both tiers aborts with the error classes attached.
{
  const agentFn = async () => {
    throw new Error("model claude-fable-5 is inaccessible");
  };
  const out = await runWorkflow({ agentFn, args: { days: 7 } }).promise;
  check("no manifest aborts the run", out.error.includes("manifest agent failed twice"));
  check("abort carries the error class", JSON.stringify(out.error_attempts).includes("model_inaccessible"), JSON.stringify(out.error_attempts));
  check("abort is not reported as coverage", out.coverage.complete === false && out.partial_run === true);
}

// 15. The manifest agent runs the script; it does not scan the corpus itself.
{
  const agentFn = async (prompt, opts) => {
    if (opts.label.startsWith("manifest")) return manifestOf([session("aaaaaaaa-1")], { trivial_count: 2, stub_target_count: 2 });
    if (opts.label.startsWith("stubs:")) return { sessions: [{ session_id: "t1", gist: "g", category: "machine_lane" }, { session_id: "t2", gist: "g", category: "machine_lane" }] };
    if (opts.label.startsWith("analyze:")) return { ...FACET };
    return null;
  };
  const { promise, prompts } = runWorkflow({ agentFn, args: { days: 7, cap: 40, exclude_session_id: "own-uuid" } });
  await promise;
  const m = prompts.find((p) => p.opts.label === "manifest");
  check("the manifest agent is told to run the scan script", m.prompt.includes("session-manifest.py"));
  check("the cap and window are passed to the script", m.prompt.includes("--days 7") && m.prompt.includes("--cap 40"));
  check("the audit's own session is excluded by id", m.prompt.includes("--exclude own-uuid"));
  check("the manifest agent is told to relay verbatim, not to analyse", m.prompt.includes("VERBATIM"));
  check(
    "stub batches read their slice from the manifest file, not from the workflow's output",
    prompts.some((p) => p.opts.label.startsWith("stubs:") && p.prompt.includes("stub_targets'][0:2]")),
    prompts.filter((p) => p.opts.label.startsWith("stubs:")).map((p) => p.prompt.slice(0, 200)).join(" | "),
  );
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
