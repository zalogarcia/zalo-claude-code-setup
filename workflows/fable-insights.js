export const meta = {
  name: "fable-insights",
  description:
    "Weekly self-audit: one deep-analysis agent per substantive Claude Code session (last N days), batched gist extraction for trivial sessions, manifest built at run time by an agent (workflow scripts have no filesystem access).",
  whenToUse:
    "Weekly self-audit of Claude Code sessions; args {days} (default 7)",
  phases: [
    {
      title: "Manifest",
      detail:
        "one agent builds the session work-list from ~/.claude/projects at run time",
    },
    {
      title: "Analyze",
      detail: "one deep-analysis agent per substantive session (facets)",
    },
    {
      title: "Stubs",
      detail: "batched gist extraction for trivial sessions (batches of 9)",
    },
  ],
};

// ---- args guard ---------------------------------------------------------------
// KNOWN BUG: background-launched workflows can receive `args` as undefined or as
// a JSON string — never assume an object.
let parsedArgs = args;
if (typeof parsedArgs === "string") {
  try {
    parsedArgs = JSON.parse(parsedArgs);
  } catch (e) {
    parsedArgs = null;
  }
}
const days =
  (parsedArgs && typeof parsedArgs === "object" && Number(parsedArgs.days)) ||
  7;

const ANALYZE_CAP = 80;
const STUB_BATCH_SIZE = 9;

// ---- schemas ------------------------------------------------------------------
const SESSION_ITEM_SCHEMA = {
  type: "object",
  required: ["id", "path", "start", "user_msgs", "lines", "project"],
  properties: {
    id: { type: "string", description: "transcript basename without .jsonl" },
    path: {
      type: "string",
      description: "absolute path to the .jsonl transcript",
    },
    start: {
      type: "string",
      description: "YYYY-MM-DD of the first timestamp in the file",
    },
    user_msgs: { type: "integer" },
    lines: { type: "integer" },
    project: {
      type: "string",
      description:
        'directory slug with "-Users-zalo-" prefix stripped; "home" for the bare -Users-zalo dir',
    },
  },
};

const MANIFEST_SCHEMA = {
  type: "object",
  required: ["generated_on", "substantive", "trivial"],
  properties: {
    generated_on: {
      type: "string",
      description: "today, YYYY-MM-DD, stamped via date +%F",
    },
    substantive: { type: "array", items: SESSION_ITEM_SCHEMA },
    trivial: { type: "array", items: SESSION_ITEM_SCHEMA },
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
    "verification_quality",
    "brief_summary",
  ],
  properties: {
    goal: {
      type: "string",
      description:
        "The underlying goal — what the user really wanted, not the surface request",
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
        "Concrete evidence for the outcome verdict (deploy confirmed, tests green, user reaction, etc.)",
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
      description:
        "Verbatim user reactions that support the satisfaction verdict",
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
            enum: [
              "claude_bug",
              "overclaimed_verification",
              "tooling_breakage",
              "usage_limit",
              "wrong_approach",
              "environment",
              "user_change_of_mind",
              "hook_by_design",
              "other",
            ],
            description:
              "Pinned taxonomy (2026-07-19: analysts were inventing singleton types, breaking week-over-week deltas). Use 'other' + detail rather than a new slug. 'hook_by_design' = a guard hook (sql-guard / git-guard / agent-model-guard) firing exactly as designed — a designed tax, not real friction.",
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
    verification_quality: {
      enum: ["ground_truth", "partial", "claimed_only", "none_needed"],
      description:
        "Did Claude prove its done-claims with fresh evidence (live checks, test output) or just assert?",
    },
    wasted_cycles: {
      type: "string",
      description:
        "What burned time unnecessarily, if anything; empty string if nothing",
    },
    standout: {
      type: "string",
      description:
        "Most impressive thing Claude did this session; empty string if nothing notable",
    },
    notable_quote: {
      type: "string",
      description:
        "One short verbatim user quote that captures the session; empty string if none",
    },
    user_interruptions: { type: "integer" },
    brief_summary: {
      type: "string",
      description:
        "One-two sentences: what the user wanted and whether they got it",
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
          gist: {
            type: "string",
            description: "One sentence: what the user wanted and what happened",
          },
          category: {
            enum: [
              "aborted",
              "slash_command_only",
              "quick_question",
              "quick_task",
              "other",
            ],
          },
        },
      },
    },
  },
};

// ---- Phase 1: Manifest ----------------------------------------------------------
// Workflow scripts cannot touch the filesystem — one agent builds the work-list.
const manifestPrompt = `Build a manifest of Claude Code session transcripts from the last ${days} days. Run these exact bash steps (adjust nothing except where noted) and return ONLY via the structured output tool.

STEP 1 — candidate files (note: -maxdepth 2 and the subagents exclusion are both required):
find "$HOME/.claude/projects" -maxdepth 2 -type f -name '*.jsonl' -mtime -${days} ! -path '*/subagents/*'

STEP 2 — exclude the currently-running session if detectable:
lsof +D "$HOME/.claude/projects" 2>/dev/null | grep -o '/[^ ]*\\.jsonl' | sort -u
Any path that command prints is an open (live) transcript — drop it from the candidate list. If lsof prints nothing (or errors), fall back to dropping candidates modified in the last 3 minutes: find "$HOME/.claude/projects" -maxdepth 2 -type f -name '*.jsonl' -mmin -3

STEP 3 — per remaining file "$f", compute:
- id: basename without the .jsonl extension
- path: the absolute path
- lines: wc -l < "$f"
- user_msgs (real typed user messages — excludes tool_results, meta, and subagent sidechain traffic):
jq -r 'select(.type=="user" and ((.isMeta // false)|not) and ((.isSidechain // false)|not)) | .message.content | if type=="string" then "m" elif type=="array" then (if (map(select(.type=="text")) | length) > 0 then "m" else empty end) else empty end' "$f" | wc -l
- start (YYYY-MM-DD of the first timestamp):
head -20 "$f" | jq -r '.timestamp // empty' | head -1 | cut -c1-10
(if empty, fall back to the file mtime date: stat -f '%Sm' -t '%Y-%m-%d' "$f")
- project: basename of the parent directory. Strip the leading "-Users-zalo-" prefix (e.g. "-Users-zalo-dev-delta-agents" -> "dev-delta-agents"). If the directory basename is exactly "-Users-zalo", use "home".

Run Step 3 as SEPARATE simple Bash calls per file (one jq/wc/head/stat invocation at a time). Do NOT use while-read loops, process substitution, command substitution, xargs -I, or any compound shell construct — keep each call auditable and permission-friendly. Many small calls are fine; a typical week is under ~100 files.

STEP 4 — classify:
substantive = user_msgs >= 3 OR lines >= 100. Everything else is trivial.

STEP 5 — stamp generated_on with: date +%F

Return the full manifest via structured output: { generated_on, substantive: [...], trivial: [...] } with every surviving candidate accounted for in exactly one of the two arrays. Do NOT read transcript contents beyond the commands above — this is a metadata pass only.`;

phase("Manifest");
let manifest = await agent(manifestPrompt, {
  label: "manifest",
  phase: "Manifest",
  schema: MANIFEST_SCHEMA,
});
if (!manifest) {
  log("Manifest agent failed on primary model — re-dispatching on opus");
  manifest = await agent(manifestPrompt, {
    label: "manifest:retry",
    phase: "Manifest",
    schema: MANIFEST_SCHEMA,
    model: "opus",
  });
}
if (!manifest) {
  return {
    error: "manifest agent failed twice — no work-list, aborting run",
    facets: [],
    stubs: [],
    failed: [],
    manifest_counts: null,
  };
}

const substantive = Array.isArray(manifest.substantive)
  ? manifest.substantive
  : [];
const trivial = Array.isArray(manifest.trivial) ? manifest.trivial : [];
log(
  `Manifest (${manifest.generated_on || "undated"}): ${substantive.length} substantive + ${trivial.length} trivial sessions in the last ${days} days`,
);

// ---- cap safety (no silent caps) ------------------------------------------------
let toAnalyze = substantive;
if (substantive.length > ANALYZE_CAP) {
  log(
    `TRUNCATION: ${substantive.length} substantive sessions exceed the cap of ${ANALYZE_CAP} — analyzing the ${ANALYZE_CAP} largest by lines, skipping ${substantive.length - ANALYZE_CAP}`,
  );
  toAnalyze = [...substantive]
    .sort((a, b) => (b.lines || 0) - (a.lines || 0))
    .slice(0, ANALYZE_CAP);
}

// ---- Phase 2: Analyze -------------------------------------------------------------
const promptFor = (
  s,
) => `You are one analyst in a fleet producing a deep usage-insights report on Claude Code sessions. Analyze exactly ONE session transcript and return a structured facet.

TRANSCRIPT: ${s.path}
Project: ${s.project} | Started: ${s.start} | ~${s.user_msgs} user messages | ${s.lines} JSONL lines.

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

Notes on the format: entries with "<command-name>" or "local-command" in user content are slash-command invocations, not typed prompts. "Caveat:" blocks are harness boilerplate. isSidechain=true traffic is subagent internals — already filtered out above.

Context: the user is a solo operator running production SaaS (delta-agents = voice-AI platform), marketing sites (operatorbase-website, copymyaiagency), a course app (90-day-cmaa-game-app), and video/content production (black-umbrella, home sessions). They delegate whole build-test-deploy workflows and demand ground-truth verification.

ANALYZE DEEPLY — this is a Fable-tier pass, expected to beat a shallow facet extraction:
- Underlying goal: what did they actually want (read between requests)?
- Outcome + concrete evidence. Do not credit "done" claims Claude never proved.
- Satisfaction: judge from verbatim reactions ("perfect", "much better", "no", "wrong", silence then topic change). Quote them.
- EVERY friction instance: what went wrong, root cause, and whether Claude could have avoided it upfront. Use ONLY the pinned type taxonomy (claude_bug / overclaimed_verification / tooling_breakage / usage_limit / wrong_approach / environment / user_change_of_mind / hook_by_design / other) — never invent a new slug; if none fits, use 'other' and explain in detail. A guard hook (sql-guard / git-guard / agent-model-guard) blocking or holding as designed is 'hook_by_design', NOT environment friction.
- Verification quality: did Claude ground-truth its claims (live checks, fresh test output, probes) or assert "should work"?
- Wasted cycles: repeated attempts, blind alleys, re-derived environment quirks.
- Standout: the single most impressive thing, if any.
- One short verbatim user quote that captures the session, if any exists.

Return ONLY via the structured output tool.`;

phase("Analyze");
log(
  `Analyzing ${toAnalyze.length} substantive sessions + ${trivial.length} stubs`,
);

const facets = await pipeline(toAnalyze, async (s) => {
  const opts = {
    label: `analyze:${String(s.project || "").replace("dev-", "")}:${String(s.id).slice(0, 8)}`,
    phase: "Analyze",
    schema: FACET_SCHEMA,
  };
  let analyzedBy = "fable";
  let r = await agent(promptFor(s), opts);
  if (!r) {
    analyzedBy = "opus-fallback";
    log(
      `${String(s.id).slice(0, 8)} failed on primary model — re-dispatching on opus`,
    );
    r = await agent(promptFor(s), {
      ...opts,
      label: `retry:${String(s.id).slice(0, 8)}`,
      model: "opus",
    });
  }
  return r
    ? {
        ...r,
        session_id: s.id,
        project: s.project,
        date: s.start,
        analyzed_by: analyzedBy,
      }
    : { session_id: s.id, project: s.project, date: s.start, failed: true };
});

// ---- Phase 3: Stubs ---------------------------------------------------------------
const stubPrompt = (
  batch,
) => `Analyze ${batch.length} tiny Claude Code session transcripts (each under ~200 JSONL lines — safe to extract fully). For EACH, run:

jq -r 'select(.type=="user") | .message.content | if type=="string" then . elif type=="array" then (map(select(.type=="text") | .text) | join("\\n")) else empty end' '<path>' | head -c 3000

Sessions:
${batch.map((s) => `- ${s.id} → ${s.path} (project: ${s.project}, ${s.start})`).join("\n")}

For each session return: session_id, one-sentence gist (what the user wanted + what happened, or "aborted before any real request"), and category (aborted / slash_command_only / quick_question / quick_task / other). Entries containing "<command-name>" are slash-command invocations. Return ONLY via structured output, one entry per session, all ${batch.length} accounted for.`;

phase("Stubs");
const chunks = [];
for (let i = 0; i < trivial.length; i += STUB_BATCH_SIZE)
  chunks.push(trivial.slice(i, i + STUB_BATCH_SIZE));
const stubResults = chunks.length
  ? await parallel(
      chunks.map(
        (c, i) => () =>
          agent(stubPrompt(c), {
            label: `stubs:batch${i + 1}`,
            phase: "Stubs",
            schema: STUB_SCHEMA,
          }),
      ),
    )
  : [];

const stubs = stubResults
  .filter(Boolean)
  .flatMap((r) => (Array.isArray(r.sessions) ? r.sessions : []));
// No-silent-caps guard: a dead stub-batch agent returns null and its sessions
// would simply vanish from the weekly record. Reconcile returned session_ids
// against the manifest and record the missing ones as failures.
const stubIds = new Set(stubs.map((s) => s.session_id));
const missingStubs = trivial.filter((s) => !stubIds.has(s.id)).map((s) => s.id);
if (missingStubs.length) {
  log(
    `⚠️  ${missingStubs.length}/${trivial.length} trivial sessions missing from stub results (dead batch agent or omitted entry): ${missingStubs.join(", ")}`,
  );
}
const failed = facets
  .filter(Boolean)
  .filter((f) => f.failed)
  .map((f) => f.session_id)
  .concat(missingStubs);

const manifest_counts = {
  generated_on: manifest.generated_on || null,
  days,
  substantive: substantive.length,
  trivial: trivial.length,
  analyzed: toAnalyze.length,
  skipped_by_cap: substantive.length - toAnalyze.length,
  stub_batches: chunks.length,
  stubs_missing: missingStubs.length,
};

log(
  `Done: ${facets.filter(Boolean).filter((f) => !f.failed).length}/${toAnalyze.length} facets, ${stubs.length}/${trivial.length} stubs, ${failed.length} failed`,
);
log(
  "Synthesis: follow ~/.claude/workflows/fable-insights-synthesis.md (artifact names, baseline comparison, mechanization + demotion bias)",
);

return {
  facets: facets.filter(Boolean),
  stubs,
  failed,
  manifest_counts,
  synthesis_protocol: "~/.claude/workflows/fable-insights-synthesis.md",
};
