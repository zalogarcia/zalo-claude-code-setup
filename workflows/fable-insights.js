export const meta = {
  name: "fable-insights",
  description:
    "Weekly self-audit: a deterministic script builds the manifest and draws a stratified sample, one deep-analysis agent per sampled session, clustered gist extraction for trivial sessions, and a cross-model Verify stage over the aggregate.",
  whenToUse:
    "Weekly self-audit of Claude Code sessions; args {days} (default 7), {cap} (default 80), {exclude_session_id} (REQUIRED, the invoking conversation's own session id, the UUID segment of your scratchpad path; only that transcript is skipped. Open sessions from other terminals ARE analyzed, marked in_progress)",
  phases: [
    {
      title: "Manifest",
      detail:
        "one agent runs scripts/session-manifest.py, which scans the transcripts, classifies them and draws the stratified sample",
    },
    {
      title: "Stubs",
      detail:
        "clustered gist extraction for trivial sessions, read from the manifest file by index range",
    },
    {
      title: "Analyze",
      detail: "one deep-analysis agent per sampled substantive session (facets)",
    },
    {
      title: "Verify",
      detail:
        "one fable agent audits the opus fan-out's aggregate output for saturation, empty facets, invented taxonomy slugs and sampling honesty",
    },
  ],
};

// ---- args guard ---------------------------------------------------------------
// KNOWN BUG: background-launched workflows can receive `args` as undefined or as
// a JSON string, so never assume an object.
let parsedArgs = args;
if (typeof parsedArgs === "string") {
  try {
    parsedArgs = JSON.parse(parsedArgs);
  } catch (e) {
    parsedArgs = null;
  }
}
const argOf = (k) =>
  parsedArgs && typeof parsedArgs === "object" ? parsedArgs[k] : undefined;
const days = Number(argOf("days")) || 7;
const cap = Number(argOf("cap")) || 80;
// Session id of the audit's OWN conversation. Only this transcript is excluded;
// open sessions belonging to OTHER terminals are analyzed with in_progress true.
// (2026-07-19: the old drop-all-open rule silently excluded the week's
// highest-friction session, a 31MB still-open live-test transcript.)
const excludeSessionId =
  typeof argOf("exclude_session_id") === "string"
    ? argOf("exclude_session_id")
    : "";

const PRIMARY_MODEL = "opus";
const FALLBACK_MODEL = "fable";
const STUB_BATCH_SIZE = 9;
const STUB_RESCUE_SIZE = 3;
const MANIFEST_SCRIPT = "~/.claude/scripts/session-manifest.py";

// Taxonomy version. Bumped whenever the friction enum changes, because a
// week-over-week delta computed across a taxonomy change is not a delta.
// v1 (2026-07-19 to 2026-09-19): the ten pinned types.
// v2 (2026-09-19): ten types added after 113 of 567 frictions (19.9%) landed in
// `other` in the v1 week. They draw mass mostly out of `other`, and some out of
// `environment` and `wrong_approach`, so v1 and v2 weeks are comparable only on
// the `other` RATE and on types unchanged between them.
const TAXONOMY_VERSION = 2;

const FRICTION_TYPES = [
  "claude_bug",
  "overclaimed_verification",
  "tooling_breakage",
  "usage_limit",
  "wrong_approach",
  "environment",
  "user_change_of_mind",
  "hook_by_design",
  "post_delivery_defect",
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
  "other",
];

const FRICTION_GUIDE = `claude_bug = the harness or model misbehaved.
overclaimed_verification = a done/fixed/shipped claim with no fresh evidence behind it.
tooling_breakage = a tool, CLI or vendor API failed on its own terms.
usage_limit = a Claude or Codex limit wall.
wrong_approach = Claude chose a path that had to be abandoned.
environment = a machine, network or credential fact outside the repo bit the run.
user_change_of_mind = the user changed the target; not Claude's cost.
hook_by_design = a guard hook fired exactly as designed; a designed tax, not friction.
post_delivery_defect = a defect found while validating work an EARLIER session or autonomous run delivered as done; charge it to the producing pipeline.
schema_guess = a table, column, field or endpoint name written from memory or pattern instead of read from the live schema or snapshot; the Postgres 42703 / 42P01 class.
shell_or_edit_mechanics = the tool call itself was malformed and cost a retry: shell quoting, a non-unique edit anchor, a heredoc, an unquoted glob, a cwd reset, a wrong flag. No logic implication.
gate_or_test_defect = the verification instrument was wrong or lied: a cached replay green, a scenario set with a blind spot, an over-fitted or stale assertion, harness drift against main.
stale_fact_inherited = a fact from a brief, a memory file, a doc, a prior report or another engine was wrong and steered the run.
self_inflicted_regression = a defect Claude introduced while doing THIS session's work, usually caught by its own QA or gate.
harness_limitation = a missing primitive in Claude Code itself (no wait-on-subagent, the 600s Bash ceiling, a tool that cannot observe what it is asked to observe). Not avoidable by better behavior.
concurrency_collision = two workers, lanes or worktrees on one repo, row, branch or scratch path: rebases, overwrites, duplicate dispatch.
unverified_number = a figure, rate or cost was stated to the user or written into a brief before it was measured, and later corrected.
owner_visible_side_effect = the owner saw, heard or was paged by something the run did without forewarning: real alerts, a visible browser, mutated owner data, unrequested scope.
preexisting_product_defect = a defect in the user's own product or rig, found mid-task, that this session did not cause.
other = none of the above. If you reach for this, the detail must say what category is missing.`;

// ---- schemas ------------------------------------------------------------------
const SESSION_ITEM_SCHEMA = {
  type: "object",
  required: ["id", "path", "transcript_dir", "start", "last_activity", "lines"],
  properties: {
    id: { type: "string" },
    path: { type: "string" },
    transcript_dir: {
      type: "string",
      description: "provenance only: the projects/ directory slug",
    },
    start: { type: "string", description: "YYYY-MM-DD of the first timestamp" },
    last_activity: {
      type: "string",
      description: "YYYY-MM-DD of the last timestamp; the window's clock",
    },
    lines: { type: "integer" },
    bytes: { type: "integer" },
    user_msgs: { type: "integer" },
    typed_msgs: { type: "integer" },
    repos_touched: { type: "array", items: { type: "string" } },
    primary_repo: { type: "string" },
    in_progress: { type: "boolean" },
    carried_over: {
      type: "boolean",
      description: "started before window_start, still active inside it",
    },
  },
};

const MANIFEST_SCHEMA = {
  type: "object",
  required: [
    "generated_on",
    "window_start",
    "window_end",
    "manifest_path",
    "candidate_total",
    "accounted_total",
    "substantive_count",
    "trivial_count",
    "selected",
    "stub_target_count",
    "sampling",
  ],
  properties: {
    generated_on: { type: "string" },
    window_start: { type: "string" },
    window_end: { type: "string" },
    manifest_path: {
      type: "string",
      description: "absolute path to the full unabridged manifest JSON on disk",
    },
    candidate_total: {
      type: "integer",
      description: "every .jsonl the scan saw, before any classification",
    },
    accounted_total: {
      type: "integer",
      description:
        "substantive + trivial + excluded, read back OFF THE FILE. It must equal candidate_total or the run is partial.",
    },
    substantive_count: { type: "integer" },
    trivial_count: { type: "integer" },
    selected: { type: "array", items: SESSION_ITEM_SCHEMA },
    not_selected_ids: { type: "array", items: { type: "string" } },
    stub_target_count: { type: "integer" },
    trivial_clusters: {
      type: "array",
      items: {
        type: "object",
        required: ["group", "count", "represented_by"],
        properties: {
          group: { type: "string" },
          count: { type: "integer" },
          represented_by: { type: "array", items: { type: "string" } },
        },
      },
      description:
        "Machine lanes gisted by representatives and counted in full. Never a fold: the member ids are in the manifest file.",
    },
    sampling: {
      type: "object",
      required: ["method", "population", "selected", "bias_statement"],
      properties: {
        method: { type: "string" },
        population: { type: "integer" },
        selected: { type: "integer" },
        coverage_pct: { type: "number" },
        seed: { type: "string" },
        strata: { type: "array", items: { type: "object" } },
        bias_statement: { type: "string" },
      },
    },
    excluded: {
      type: "array",
      items: {
        type: "object",
        required: ["id", "reason"],
        properties: { id: { type: "string" }, reason: { type: "string" } },
      },
    },
    script_error: {
      type: "string",
      description: "stderr if the script failed; empty string otherwise",
    },
  },
};

const FACET_SCHEMA = {
  type: "object",
  required: [
    "goal",
    "outcome",
    "outcome_evidence",
    "satisfaction",
    "session_type",
    "friction",
    "done_claims",
    "done_claims_with_fresh_evidence",
    "verification_evidence",
    "brief_summary",
    "validates_prior_work",
    "deferred_verification",
  ],
  properties: {
    goal: {
      type: "string",
      description:
        "The underlying goal, what the user really wanted, not the surface request",
    },
    outcome: {
      enum: [
        "fully_achieved",
        "mostly_achieved",
        "partially_achieved",
        "failed",
        "abandoned",
        "unclear",
      ],
    },
    outcome_evidence: {
      type: "string",
      description:
        "Concrete evidence for the outcome verdict (deploy confirmed, tests green, user reaction)",
    },
    satisfaction: {
      enum: [
        "satisfied",
        "likely_satisfied",
        "neutral",
        "mixed",
        "frustrated",
        "unclear",
      ],
    },
    satisfaction_evidence: {
      type: "string",
      description: "Verbatim user reactions supporting the satisfaction verdict",
    },
    session_type: {
      enum: [
        "feature_build",
        "bug_fix",
        "deploy_ship",
        "content_creation",
        "research_analysis",
        "config_setup",
        "quick_question",
        "multi_task",
        "exploration",
        "other",
      ],
    },
    models_used: { type: "array", items: { type: "string" } },
    friction: {
      type: "array",
      items: {
        type: "object",
        required: ["type", "detail", "root_cause", "avoidable"],
        properties: {
          type: {
            enum: FRICTION_TYPES,
            description:
              "Pinned taxonomy v2. Never invent a slug. Reach for 'other' only when the detail can say which category is missing.",
          },
          detail: { type: "string" },
          root_cause: { type: "string" },
          avoidable: {
            type: "boolean",
            description:
              "true if better upfront behavior by Claude would have prevented it",
          },
        },
      },
    },
    // verification_quality is NOT asked for. It is DERIVED from these two counts
    // in the workflow. 2026-09-19: as a judged enum it answered ground_truth on
    // 79 of 80 sessions while those same 80 rows logged 17 overclaimed
    // verification frictions, 17 of 17 of them inside ground_truth rows. A field
    // that contradicts its own row is not a measurement.
    done_claims: {
      type: "integer",
      description:
        "COUNT the times this session asserted work was done / fixed / shipped / verified / complete. Not a judgement, a count. 0 if the session never claimed completion.",
    },
    done_claims_with_fresh_evidence: {
      type: "integer",
      description:
        "Of those, how many were accompanied IN THE SAME TURN by a command and its output, a live check, a screenshot or a run id that actually proves the claim. A green typecheck does not prove a behavior claim. Must be <= done_claims.",
    },
    verification_evidence: {
      type: "string",
      description:
        "Quote the proof for one evidenced claim, or quote the unevidenced claim if there were none. This is what makes the two counts checkable.",
    },
    validates_prior_work: {
      type: "string",
      description:
        "If this session live-tests, debugs or validates something an earlier session or autonomous run delivered as done, name that artifact or run; empty string otherwise.",
    },
    deferred_verification: {
      type: "boolean",
      description:
        "true if this session claimed work complete while its behavior-level verification was deferred (live tests skipped, ACs replaced by on-disk proxies, COMPLETE with live checks left for later)",
    },
    wasted_cycles: { type: "string" },
    standout: { type: "string" },
    notable_quote: { type: "string" },
    user_interruptions: { type: "integer" },
    brief_summary: {
      type: "string",
      description:
        "One or two sentences: what the user wanted and whether they got it",
    },
  },
};

const STUB_SCHEMA = {
  type: "object",
  required: ["sessions"],
  properties: {
    sessions: {
      type: "array",
      items: {
        type: "object",
        required: ["session_id", "gist", "category"],
        properties: {
          session_id: { type: "string" },
          gist: { type: "string" },
          category: {
            enum: [
              "aborted",
              "slash_command_only",
              "quick_question",
              "quick_task",
              "machine_lane",
              "other",
            ],
          },
        },
      },
    },
  },
};

// ---- helpers -------------------------------------------------------------------
function classifyError(err) {
  const m = String((err && err.message) || err || "").toLowerCase();
  if (!m) return "empty_return";
  if (m.includes("usage limit") || m.includes("rate_limit")) return "usage_limit";
  if (m.includes("inaccessible") || m.includes("model_not_found"))
    return "model_inaccessible";
  if (m.includes("overloaded") || m.includes("529")) return "overloaded";
  if (m.includes("timeout") || m.includes("timed out")) return "timeout";
  return "unknown:" + m.slice(0, 80);
}

async function tryAgent(prompt, opts) {
  // Returns {result, error_class}. A thrown error and a null return are both
  // failures; only the thrown one carries a class worth recording.
  try {
    const r = await agent(prompt, opts);
    return { result: r, error_class: r ? null : "empty_return" };
  } catch (e) {
    return { result: null, error_class: classifyError(e) };
  }
}

const UUIDISH = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function isFoldedExclusion(e) {
  // The 2026-09-19 shape: one excluded record whose id was
  // "dev-.../* (232 transcripts)" and whose reason explained the output limit.
  const id = String((e && e.id) || "");
  const reason = String((e && e.reason) || "").toLowerCase();
  if (!UUIDISH.test(id) && /[*(),\s]/.test(id)) return true;
  return /aggregat|truncat|output-token|output token|exceeded|folded/.test(reason);
}

function deriveVerificationQuality(f) {
  // Mechanical, from two counts, with the contradiction made impossible.
  const claims = Number.isFinite(f.done_claims) ? Math.max(0, f.done_claims) : 0;
  let evidenced = Number.isFinite(f.done_claims_with_fresh_evidence)
    ? Math.max(0, f.done_claims_with_fresh_evidence)
    : 0;
  const notes = [];
  if (evidenced > claims) {
    notes.push("evidenced>claims, clamped");
    evidenced = claims;
  }
  const overclaims = (Array.isArray(f.friction) ? f.friction : []).filter(
    (x) => x && x.type === "overclaimed_verification",
  ).length;
  let quality;
  if (claims === 0) quality = "none_needed";
  else if (evidenced === 0) quality = "claimed_only";
  else if (evidenced >= claims) quality = "ground_truth";
  else quality = "partial";
  if (overclaims > 0 && quality === "ground_truth") {
    // The row logs an unevidenced done-claim in its own friction list, so
    // "every claim was evidenced" is provably false. Repair it and count it.
    quality = evidenced > 0 ? "partial" : "claimed_only";
    notes.push(
      `repaired: ${overclaims} overclaimed_verification friction(s) contradict ground_truth`,
    );
  }
  return {
    verification_quality: quality,
    verification_quality_derived_from: {
      done_claims: claims,
      evidenced,
      overclaim_frictions: overclaims,
    },
    verification_quality_repaired: notes.length ? notes.join("; ") : "",
  };
}

// ---- Phase 1: Manifest ----------------------------------------------------------
// Workflow scripts cannot touch the filesystem, so ONE agent runs the scan
// script and relays its summary. The scan itself is deterministic Python: on
// 2026-09-19 an agent doing this scan in its own output had to fold 232 trivial
// sessions into a single record to fit its output limit, and the week's trivial
// count read 141 instead of 373.
const manifestPrompt = `Build the weekly session manifest by RUNNING ONE SCRIPT. Do not scan the transcripts yourself and do not reimplement any of this in bash.

STEP 1 - run exactly this (one Bash call):

python3 ${MANIFEST_SCRIPT} --days ${days} --cap ${cap}${excludeSessionId ? ` --exclude ${excludeSessionId}` : ""} --summary-out /tmp/fable-insights-summary.json

It scans ~/.claude/projects, computes per-session metadata, classifies substantive vs trivial, clusters machine lanes, draws the stratified sample and writes the full unabridged manifest to disk. It prints ONE line of JSON and takes a few seconds.

STEP 2 - if the command exits non-zero, return the structured output with script_error set to the last 500 characters of stderr and every count set to 0. Do NOT improvise a replacement scan.

STEP 3 - read the summary back:

cat /tmp/fable-insights-summary.json

STEP 4 - return that JSON through the structured output tool, field for field, VERBATIM. Do not re-order, re-compute, summarise, round, or drop any field, including not_selected_ids. You are a relay for this stage, not an analyst. The only field you add is script_error (empty string when the script succeeded).

Sanity check before you return: accounted_total must equal candidate_total, and the selected array must hold exactly sampling.selected records. If they disagree, return them as they are anyway and put one sentence about the disagreement in script_error. Never make the numbers agree by editing them.`;

phase("Manifest");
let manifestAttempts = [];
let manifest = null;
for (const model of [PRIMARY_MODEL, FALLBACK_MODEL]) {
  const got = await tryAgent(manifestPrompt, {
    label: model === PRIMARY_MODEL ? "manifest" : "manifest:retry",
    phase: "Manifest",
    schema: MANIFEST_SCHEMA,
    model,
  });
  manifestAttempts.push({ model, error_class: got.error_class });
  if (got.result) {
    manifest = got.result;
    break;
  }
  log(`Manifest agent failed on ${model} (${got.error_class})`);
}

if (!manifest) {
  return {
    error: "manifest agent failed twice, no work-list, aborting run",
    error_attempts: manifestAttempts,
    facets: [],
    stubs: [],
    failed: [],
    manifest_counts: null,
    coverage: {
      complete: false,
      facet_coverage_pct: 0,
      stub_coverage_pct: 0,
      true_coverage_pct: 0,
      sample_coverage_pct: 0,
    },
    partial_run: true,
    taxonomy_version: TAXONOMY_VERSION,
  };
}

const selected = Array.isArray(manifest.selected) ? manifest.selected : [];
const sampling = manifest.sampling || { method: "unknown", bias_statement: "" };
const excluded = Array.isArray(manifest.excluded) ? manifest.excluded : [];
const stubTargetCount = Number(manifest.stub_target_count) || 0;
const manifestPath = manifest.manifest_path || "";

log(
  `Manifest (${manifest.generated_on || "undated"}, ${manifest.window_start} to ${manifest.window_end}): ${manifest.candidate_total} candidates, ${manifest.substantive_count} substantive, ${manifest.trivial_count} trivial`,
);
log(`SAMPLING: ${sampling.bias_statement || "no bias statement returned"}`);

// ---- reconciliation: a count that does not add up is said out loud -------------
const reconciliation = {
  candidate_total: Number(manifest.candidate_total) || 0,
  accounted_total: Number(manifest.accounted_total) || 0,
  ok: Number(manifest.candidate_total) === Number(manifest.accounted_total),
  folded_exclusions: excluded.filter(isFoldedExclusion),
  script_error: manifest.script_error || "",
  // The one output budget left in the chain: the manifest agent relays up to
  // `cap` selected records. The script says how many it drew, so a relay that
  // silently dropped some is catchable by comparing the two.
  relay_ok:
    !Number.isFinite(Number(sampling.selected)) ||
    Number(sampling.selected) === selected.length,
  relay_expected: Number(sampling.selected),
  relay_received: selected.length,
};
if (!reconciliation.ok) {
  log(
    `MANIFEST RECONCILIATION FAILED: ${reconciliation.candidate_total} candidates scanned but ${reconciliation.accounted_total} accounted for. ${reconciliation.candidate_total - reconciliation.accounted_total} sessions are unexplained. Every count below is a floor, not a total.`,
  );
}
if (reconciliation.folded_exclusions.length) {
  log(
    `MANIFEST FOLD DETECTED: ${reconciliation.folded_exclusions.length} excluded record(s) stand in for a group instead of naming one session: ${reconciliation.folded_exclusions.map((e) => e.id).join(", ")}. Trivial and excluded counts are understated by whatever those records cover.`,
  );
}
if (!reconciliation.relay_ok) {
  log(
    `MANIFEST RELAY TRUNCATED: the script drew ${reconciliation.relay_expected} sessions but only ${reconciliation.relay_received} records arrived. The missing ones are in the manifest file and were NOT analysed; every count below is a floor.`,
  );
}
if (reconciliation.script_error) {
  log(
    `MANIFEST SCRIPT ERROR: ${reconciliation.script_error}. This run analysed whatever the script managed to return; it is not a week.`,
  );
}
if (reconciliation.candidate_total === 0) {
  log(
    "EMPTY SCAN: the manifest reports zero candidate transcripts. That is a broken scan, not a quiet week, and nothing below is coverage.",
  );
}

// ---- Phase 2: Stubs (before the expensive wave) ----------------------------------
// Stubs run first because they are cheap and because their failures change what
// the coverage line means for the whole run. The batch agents read the manifest
// file themselves: no trivial-session record ever passes through an agent's
// output budget.
const stubPrompt = (from, to, sizeNote) =>
  `Gist a slice of trivial Claude Code sessions.

STEP 1 - read the slice from the manifest file (one Bash call):

python3 -c "import json;d=json.load(open('${manifestPath}'));print(json.dumps(d['stub_targets'][${from}:${to}]))"

That prints ${sizeNote} records, each with an id and a path.

STEP 2 - for EACH record, extract the user side of the transcript:

jq -r 'select(.type=="user") | .message.content | if type=="string" then . elif type=="array" then (map(select(.type=="text") | .text) | join("\\n")) else empty end' '<path>' | head -c 3000

STEP 3 - return one entry per record: session_id, a one-sentence gist (what the user wanted and what happened, or "aborted before any real request"), and a category (aborted / slash_command_only / quick_question / quick_task / machine_lane / other). Entries containing "<command-name>" are slash-command invocations. A transcript that is one machine-generated poll or scratch run with no human turn is machine_lane.

Return ONLY via structured output, with all ${sizeNote} accounted for.`;

phase("Stubs");
const batches = [];
for (let i = 0; i < stubTargetCount; i += STUB_BATCH_SIZE)
  batches.push([i, Math.min(i + STUB_BATCH_SIZE, stubTargetCount)]);

const stubBatchResults = batches.length
  ? await parallel(
      batches.map(([from, to], i) => async () => {
        const opts = {
          label: `stubs:batch${i + 1}`,
          phase: "Stubs",
          schema: STUB_SCHEMA,
          model: PRIMARY_MODEL,
        };
        const note = `${to - from} session`;
        let got = await tryAgent(stubPrompt(from, to, note), opts);
        if (!got.result) {
          got = await tryAgent(stubPrompt(from, to, note), {
            ...opts,
            label: `stubs:batch${i + 1}:retry`,
            model: FALLBACK_MODEL,
          });
        }
        return { range: [from, to], result: got.result, error_class: got.error_class };
      }),
    )
  : [];

const stubs = [];
const stubFailures = [];
for (const b of stubBatchResults.filter(Boolean)) {
  if (b.result && Array.isArray(b.result.sessions)) stubs.push(...b.result.sessions);
  else stubFailures.push({ range: b.range, error_class: b.error_class });
}

// Rescue pass: a dead batch takes 9 sessions down with it. 2026-08-28: all 5
// batches died and 43 of 43 trivial sessions vanished from the weekly record.
if (stubFailures.length) {
  log(
    `${stubFailures.length}/${batches.length} stub batches failed; running the small-batch rescue pass`,
  );
  const rescueRanges = [];
  for (const f of stubFailures) {
    for (let i = f.range[0]; i < f.range[1]; i += STUB_RESCUE_SIZE)
      rescueRanges.push([i, Math.min(i + STUB_RESCUE_SIZE, f.range[1])]);
  }
  const rescued = await parallel(
    rescueRanges.map(([from, to], i) => async () => {
      const got = await tryAgent(stubPrompt(from, to, `${to - from} session`), {
        label: `stubs:rescue${i + 1}`,
        phase: "Stubs",
        schema: STUB_SCHEMA,
        model: PRIMARY_MODEL,
      });
      return got.result;
    }),
  );
  for (const r of rescued.filter(Boolean))
    if (Array.isArray(r.sessions)) stubs.push(...r.sessions);
}

const stubsMissing = Math.max(0, stubTargetCount - stubs.length);
if (stubsMissing)
  log(
    `${stubsMissing}/${stubTargetCount} trivial sessions have no gist after the rescue pass; they are counted in failed, not dropped`,
  );

// ---- Phase 3: Analyze -------------------------------------------------------------
const promptFor = (
  s,
) => `You are one analyst in a fleet producing a deep usage-insights report on Claude Code sessions. Analyze exactly ONE session transcript and return a structured facet.

TRANSCRIPT: ${s.path}
Repos touched: ${(s.repos_touched || []).join(", ") || "none detected"} | Last activity: ${s.last_activity} | ${s.user_msgs} user messages | ${s.lines} JSONL lines | ${s.bytes} bytes${s.carried_over ? " | STARTED BEFORE THIS WINDOW (" + s.start + ")" : ""}${s.in_progress ? " | STILL OPEN: analyze it as a snapshot" : ""}.

CRITICAL: the file may be tens of MB. NEVER Read or cat the whole file. Extract slices with these exact bash commands (you may lower the byte caps, never raise them):

1. User messages (the spine of your analysis):
jq -r 'select(.type=="user" and ((.isMeta // false)|not) and ((.isSidechain // false)|not)) | .message.content | if type=="string" then . elif type=="array" then (map(select(.type=="text") | .text) | join("\\n")) else empty end' '${s.path}' | head -c 25000

If output hits the cap, also sample the end: same command | tail -c 8000

2. Claude's visible text replies (to judge claims and tone):
jq -r 'select(.type=="assistant" and ((.isSidechain // false)|not)) | .message.content[]? | select(.type=="text") | .text' '${s.path}' | head -c 30000
(and | tail -c 10000 if truncated)

3. Tool usage profile:
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") | .name' '${s.path}' | sort | uniq -c | sort -rn | head -25

4. Models that drove the session:
jq -r 'select(.type=="assistant") | .message.model // empty' '${s.path}' | sort | uniq -c

5. Error and interruption signals:
grep -c '"is_error":true' '${s.path}' ; grep -o 'Request interrupted[^"]*' '${s.path}' | head -5
Optionally sample error payloads:
jq -r 'select(.type=="user") | .message.content | if type=="array" then (map(select(.type=="tool_result" and .is_error==true) | (.content | if type=="string" then . else (map(.text? // "") | join(" ")) end))[]) else empty end' '${s.path}' 2>/dev/null | head -c 4000

Notes on the format: entries with "<command-name>" or "local-command" in user content are slash-command invocations, not typed prompts. "Caveat:" blocks are harness boilerplate. isSidechain=true traffic is subagent internals, already filtered out above.

Context: the user is a solo operator running production SaaS (delta-agents = voice-AI platform), marketing sites (operatorbase-website, copymyaiagency), a course app (90-day-cmaa-game-app), and video/content production (black-umbrella, home sessions). Most work is delegated to background workers, so a transcript with ONE user message and hours of tool calls is normal and is not a shallow session. They demand ground-truth verification.

ANALYZE DEEPLY:
- Underlying goal: what did they actually want (read between requests)?
- Outcome plus concrete evidence. Do not credit "done" claims Claude never proved.
- Satisfaction: judge from verbatim reactions ("perfect", "much better", "no", "wrong", silence then topic change). Quote them.
- EVERY friction instance: what went wrong, root cause, whether Claude could have avoided it upfront. Use ONLY this taxonomy (version ${TAXONOMY_VERSION}):
${FRICTION_GUIDE}
- done_claims and done_claims_with_fresh_evidence are COUNTS, not a verdict. Count every assertion that work is done, fixed, shipped, verified or complete. Then count how many of those had, in the same turn, a command and its output, a live check, a screenshot or a run id that actually proves that claim. A green typecheck or unit-test run does NOT prove a behavior claim. If the session logs an overclaimed_verification friction, the second count MUST be lower than the first; a run that claims every claim was evidenced while also logging an overclaim is contradicting itself and the workflow will repair it against you.
- verification_evidence: quote the proof for one evidenced claim, or quote the unevidenced claim when there were none.
- validates_prior_work: if this session's real job is live-testing, debugging or validating something an earlier session or autonomous run delivered as done, name that artifact or run; else empty string.
- deferred_verification: true if THIS session claimed completion while behavior-level verification was deferred.
- Wasted cycles, standout, one short verbatim user quote, if any exist.

Do NOT return a project or repo field: those are attached mechanically from the manifest.

Return ONLY via the structured output tool.`;

phase("Analyze");
log(
  `Analyzing ${selected.length} sampled substantive sessions (of ${manifest.substantive_count}) plus ${stubTargetCount} stub targets`,
);

const facets = await pipeline(selected, async (s) => {
  const base = {
    session_id: s.id,
    transcript_dir: s.transcript_dir,
    repos_touched: s.repos_touched || [],
    primary_repo: s.primary_repo || "",
    date: s.last_activity,
    started_on: s.start,
    carried_over: Boolean(s.carried_over),
    in_progress: Boolean(s.in_progress),
    bytes: s.bytes,
  };
  const attempts = [];
  for (const model of [PRIMARY_MODEL, FALLBACK_MODEL]) {
    const got = await tryAgent(promptFor(s), {
      label:
        model === PRIMARY_MODEL
          ? `analyze:${String(s.primary_repo || s.transcript_dir || "").replace("dev-", "")}:${String(s.id).slice(0, 8)}`
          : `retry:${String(s.id).slice(0, 8)}`,
      phase: "Analyze",
      schema: FACET_SCHEMA,
      model,
    });
    attempts.push({ model, error_class: got.error_class });
    if (got.result)
      return {
        ...got.result,
        ...base,
        ...deriveVerificationQuality(got.result),
        analyzed_by: model,
      };
    log(`${String(s.id).slice(0, 8)} failed on ${model} (${got.error_class})`);
  }
  return {
    ...base,
    failed: true,
    attempts,
    error_class: attempts.map((a) => a.error_class).join(" then "),
  };
});

// ---- coverage: every denominator stated ------------------------------------------
const cleanFacets = facets.filter(Boolean).filter((f) => !f.failed);
const failed = facets
  .filter(Boolean)
  .filter((f) => f.failed)
  .map((f) => f.session_id);
const stubIds = new Set(stubs.map((s) => s.session_id));
for (const f of stubFailures) failed.push(`stub-range-${f.range[0]}-${f.range[1]}`);
const lostStubs = stubsMissing;

const pct = (n, d) => (d > 0 ? Math.round((1000 * n) / d) / 10 : 100);
const coverage = {
  facet_coverage_pct: pct(cleanFacets.length, selected.length),
  stub_coverage_pct: pct(stubs.length, stubTargetCount),
  true_coverage_pct: pct(
    cleanFacets.length + stubs.length,
    selected.length + stubTargetCount,
  ),
  // The denominator that matters for any week-level claim: how much of the
  // week's substantive population this run actually looked at.
  sample_coverage_pct: pct(selected.length, Number(manifest.substantive_count) || 0),
  analysed: cleanFacets.length,
  analysis_denominator: selected.length,
  stubs: stubs.length,
  stub_denominator: stubTargetCount,
  substantive_population: Number(manifest.substantive_count) || 0,
  complete: false,
};
coverage.complete =
  reconciliation.ok &&
  // A scan that found nothing, or a script that errored, is not a complete
  // week: pct(0, 0) is 100 and an empty population is not a census, so both
  // have to be excluded explicitly (found by the independent verifier,
  // 2026-09-19, which reproduced a "complete" run holding zero facets).
  reconciliation.candidate_total > 0 &&
  !reconciliation.script_error &&
  reconciliation.relay_ok &&
  !reconciliation.folded_exclusions.length &&
  failed.length === 0 &&
  lostStubs === 0 &&
  coverage.facet_coverage_pct === 100 &&
  coverage.stub_coverage_pct === 100 &&
  sampling.method === "census";
const partial_run = !coverage.complete;
if (partial_run) {
  log(
    `PARTIAL RUN: ${coverage.analysed}/${coverage.analysis_denominator} facets, ${coverage.stubs}/${coverage.stub_denominator} stubs, sample covers ${coverage.sample_coverage_pct}% of ${coverage.substantive_population} substantive sessions. Nothing here is a week total without the sampling weights.`,
  );
}

// verification_quality distribution and the repairs that had to be made
const vqCounts = {};
let vqRepaired = 0;
for (const f of cleanFacets) {
  const q = f.verification_quality || "unset";
  vqCounts[q] = (vqCounts[q] || 0) + 1;
  if (f.verification_quality_repaired) vqRepaired += 1;
}
if (vqRepaired)
  log(
    `verification_quality: ${vqRepaired} facet(s) claimed every done-claim was evidenced while logging an overclaimed_verification friction; repaired mechanically.`,
  );

const manifest_counts = {
  generated_on: manifest.generated_on || null,
  window_start: manifest.window_start || null,
  window_end: manifest.window_end || null,
  days,
  cap,
  candidate_total: reconciliation.candidate_total,
  accounted_total: reconciliation.accounted_total,
  reconciliation_ok: reconciliation.ok,
  relay_ok: reconciliation.relay_ok,
  relay_expected: reconciliation.relay_expected,
  relay_received: reconciliation.relay_received,
  folded_exclusions: reconciliation.folded_exclusions,
  substantive: Number(manifest.substantive_count) || 0,
  trivial: Number(manifest.trivial_count) || 0,
  analyzed: selected.length,
  skipped_by_sampling: (Number(manifest.substantive_count) || 0) - selected.length,
  skipped_ids: Array.isArray(manifest.not_selected_ids)
    ? manifest.not_selected_ids
    : [],
  stub_targets: stubTargetCount,
  stub_batches: batches.length,
  stub_failures: stubFailures,
  stubs_missing: lostStubs,
  trivial_clusters: Array.isArray(manifest.trivial_clusters)
    ? manifest.trivial_clusters
    : [],
  carried_over_ids: selected.filter((s) => s.carried_over).map((s) => s.id),
  in_progress_snapshots: selected.filter((s) => s.in_progress).map((s) => s.id),
  excluded,
  manifest_path: manifestPath,
  manifest_attempts: manifestAttempts,
};

log(
  `Done: ${cleanFacets.length}/${selected.length} facets, ${stubs.length}/${stubTargetCount} stubs, ${failed.length} failed`,
);
log(
  "Synthesis: follow ~/.claude/workflows/fable-insights-synthesis.md (artifact names, baseline comparison, mechanization + demotion bias)",
);

// ---- Verify -------------------------------------------------------------------
// The ONLY fable stage. Every fan-out above runs on opus (half the token price,
// no measured quality loss on high-volume work); fable is spent once, here, as a
// cross-model second opinion on the aggregate. Per ~/.claude/CLAUDE.md the model
// that verifies should differ from the model that authored.
phase("Verify");
const verifyPayload = {
  counts: manifest_counts,
  coverage,
  sampling,
  partial_run,
  facet_count: cleanFacets.length,
  stub_count: stubs.length,
  failed_count: failed.length,
  taxonomy_version: TAXONOMY_VERSION,
  verification_quality: vqCounts,
  verification_quality_repaired: vqRepaired,
  done_claim_totals: cleanFacets.reduce(
    (a, f) => {
      const d = f.verification_quality_derived_from || {};
      a.claims += d.done_claims || 0;
      a.evidenced += d.evidenced || 0;
      return a;
    },
    { claims: 0, evidenced: 0 },
  ),
  outcomes: cleanFacets.map((f) => f.outcome || null),
  primary_repos: cleanFacets.map((f) => f.primary_repo || ""),
  friction_types: cleanFacets.flatMap((f) =>
    Array.isArray(f.friction) ? f.friction.map((x) => x && x.type) : [],
  ),
  empty_fields: cleanFacets.map((f) => ({
    session_id: f.session_id,
    empty: Object.keys(f).filter((k) => {
      const v = f[k];
      return (
        v === null ||
        v === undefined ||
        v === "" ||
        (Array.isArray(v) && v.length === 0)
      );
    }),
  })),
};

const VERIFY_SCHEMA = {
  type: "object",
  required: [
    "trustworthy",
    "saturated_fields",
    "invented_slugs",
    "sampling_honest",
    "verdict",
  ],
  properties: {
    trustworthy: {
      type: "boolean",
      description:
        "false if this week's output cannot be relied on for decisions, whatever the reason",
    },
    saturated_fields: {
      type: "array",
      items: { type: "string" },
      description:
        "Enum fields where one value dominates so heavily the field carries no information this week",
    },
    invented_slugs: {
      type: "array",
      items: { type: "string" },
      description: "friction types outside the pinned taxonomy",
    },
    sampling_honest: {
      type: "boolean",
      description:
        "true only if the run states its own sampling bias and its counts reconcile",
    },
    empty_facet_sessions: { type: "array", items: { type: "string" } },
    other_bucket_pct: {
      type: "number",
      description: "share of frictions that landed in 'other', as a percentage",
    },
    verdict: {
      type: "string",
      description:
        "Two or three sentences a human reads first, leading with whatever is wrong",
    },
  },
};

const verifyPrompt = `You are the LAST stage of a weekly self-audit. Every analysis above was produced by opus agents. You are fable, and you are here as a cross-model second opinion on their AGGREGATE output. You are not re-analysing sessions and you have no transcript access.

Judge whether this week's output is trustworthy enough to make decisions from.

## The specific failures you exist to catch
On 2026-09-19 a sweep measured this workflow's own judge as saturated: verification_quality answered "ground_truth" on 79 of 80 sessions while those same rows logged 17 overclaimed_verification frictions, 17 of 17 of them inside ground_truth rows. It also took the 80 LONGEST sessions of 297 and reported them as if they were the week.

Both have been changed: verification_quality is now DERIVED from two counts per facet and repaired when it contradicts the friction log, and selection is a stratified sample with a published bias statement. Your job is to check the new versions, not to assume they work.

## Check all of these
- Every enum field: does its distribution carry information, or has one value swallowed it? Say so bluntly. verification_quality is now derived, so saturation there means the COUNTS are saturated, which is a different and worse problem.
- verification_quality_repaired above zero means analysts are still returning self-contradicting rows. Say how many.
- Friction types outside the pinned taxonomy (version ${TAXONOMY_VERSION}): ${FRICTION_TYPES.join(", ")}. Anything else is an invented slug and it breaks week-over-week deltas.
- other_bucket_pct: what share of frictions landed in "other"? Above 10% means the taxonomy is still missing a category; name what the residue looks like if you can tell.
- sampling_honest: the run must state its own sampling bias (sampling.bias_statement) AND reconcile its counts (counts.reconciliation_ok true, counts.folded_exclusions empty). If a count does not add up or a record stands in for a group, say it in the first sentence.
- Facets with empty required fields. An empty facet is a failed analysis that did not report itself as failed.

## The data
${JSON.stringify(verifyPayload).slice(0, 60000)}

Lead your verdict with whatever is WRONG. If the week is clean, say so in one sentence and do not pad it. A verdict that flatters the input is worse than no verdict, because the whole point of this stage is that the previous stage cannot audit itself.`;

const verifyGot = await tryAgent(verifyPrompt, {
  label: "verify:aggregate",
  phase: "Verify",
  schema: VERIFY_SCHEMA,
  model: FALLBACK_MODEL,
});
const verification = verifyGot.result;

if (verification && verification.trustworthy === false) {
  log(`Verify: NOT trustworthy. ${verification.verdict || "no verdict"}`);
} else if (verification) {
  log(`Verify: ${verification.verdict || "no verdict"}`);
} else {
  log(
    `Verify: the fable verifier returned nothing (${verifyGot.error_class}). Treat this week's output as UNVERIFIED, not as clean.`,
  );
}

return {
  facets: facets.filter(Boolean),
  stubs,
  failed,
  coverage,
  partial_run,
  sampling,
  taxonomy_version: TAXONOMY_VERSION,
  manifest_counts,
  manifest_path: manifestPath,
  verification: verification || { unavailable: true, error_class: verifyGot.error_class },
  synthesis_protocol: "~/.claude/workflows/fable-insights-synthesis.md",
};
