export const meta = {
  name: "qa-audit",
  description:
    "Read-only QA audit: fan out finders across bug dimensions, adversarially verify each finding, return only confirmed bugs. No fixes.",
  whenToUse:
    "The detection step of /qa-loop, or any time you want a high-confidence bug report on a changed scope without auto-fixing.",
  phases: [
    {
      title: "Scope",
      detail: "resolve the changed-file list when no explicit scope is passed",
    },
    {
      title: "Find",
      detail: "one finder agent per bug dimension, in parallel",
    },
    {
      title: "Verify",
      detail:
        "two adversarial skeptics per finding; confirm only if neither refutes",
    },
  ],
};

// ---- args: { files?: string[], base?: string, note?: string } ----------------
// files: changed files to focus on (from `git diff` in the caller). Optional.
// base:  git ref to diff against (default HEAD). Optional.
const files = Array.isArray(args?.files)
  ? args.files
  : Array.isArray(args)
    ? args
    : [];
const base = (args && typeof args.base === "string" && args.base) || "HEAD";
const note = (args && typeof args.note === "string" && args.note) || "";

// ---- scope guard ------------------------------------------------------------
// Failure mode (observed repeatedly in real runs): when this workflow is called
// with prose instead of {files:[...]}, `files` is [] and finders silently fall
// back to `git diff HEAD` — which, inside an autopilot worktree or against a
// wrong base, audits an unrelated tree. The `scope:[]` in the return is the tell.
// Guard: resolve empty scope to a concrete file list up front (single source of
// truth) and loudly warn if it can't, so the caller never trusts a verdict from
// an unverified scope.
let resolvedFiles = files;
let scopeWarning = null;
if (!files.length) {
  phase("Scope");
  const SCOPE_SCHEMA = {
    type: "object",
    properties: {
      changedFiles: {
        type: "array",
        items: { type: "string" },
        description: "relative paths of changed source files",
      },
      empty: {
        type: "boolean",
        description: "true if the diff produced no changed source files",
      },
    },
    required: ["changedFiles", "empty"],
  };
  const scope = await agent(
    `Resolve the QA audit scope (read-only — do not edit anything).
Run \`git diff --name-only ${base}\`. If that is empty, also try \`git diff --name-only --staged\` and \`git status --porcelain\`.
Return the relative paths of changed SOURCE files only — skip lockfiles, build output (dist/.next/out), node_modules, and generated artifacts.
Set empty=true only if there are genuinely no changed source files.`,
    { label: "scope:resolve", phase: "Scope", schema: SCOPE_SCHEMA },
  );
  resolvedFiles =
    scope && Array.isArray(scope.changedFiles) ? scope.changedFiles : [];
  if (!resolvedFiles.length || (scope && scope.empty)) {
    scopeWarning = `qa-audit was called with no explicit file scope and \`git diff ${base}\` resolved to ${resolvedFiles.length} changed source file(s). The audit may be running against the wrong tree (the known scope:[] failure mode). Do not trust a clean verdict — confirm the caller passed {files:[...]} or the correct base.`;
    log(`⚠️  ${scopeWarning}`);
  } else {
    log(
      `Resolved empty scope → ${resolvedFiles.length} changed file(s) via git diff ${base}`,
    );
  }
}

const scopeText = resolvedFiles.length
  ? `Scope — focus ONLY on these changed files:\n${resolvedFiles.map((f) => `  - ${f}`).join("\n")}`
  : `Scope — the current change set. Run \`git diff ${base}\` to discover what changed and focus only on changed lines. NOTE: the scope could not be resolved to specific files; if \`git diff ${base}\` is empty or unrelated to the task, return an empty findings array and say so.`;

const diffHint = resolvedFiles.length
  ? `Run \`git diff ${base} -- ${resolvedFiles.join(" ")}\` to see exactly what changed, then read the surrounding context with the Read tool before judging. FIRST confirm these files actually exist and changed; if the diff is empty, return an empty findings array.`
  : `Run \`git diff ${base}\` first to see what changed.`;

// ---- schemas -----------------------------------------------------------------
const FINDINGS_SCHEMA = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          file: { type: "string", description: "path relative to repo root" },
          line: {
            type: "integer",
            description: "best-guess line number of the defect",
          },
          severity: {
            type: "string",
            enum: ["critical", "high", "medium", "low"],
          },
          title: { type: "string", description: "one-line summary of the bug" },
          description: {
            type: "string",
            description: "what is wrong and why it matters",
          },
          evidence: {
            type: "string",
            description: "the offending code, quoted",
          },
          suggestedFix: {
            type: "string",
            description: "minimal fix hint, optional",
          },
        },
        required: [
          "file",
          "line",
          "severity",
          "title",
          "description",
          "evidence",
        ],
      },
    },
  },
  required: ["findings"],
};

const VERDICT_SCHEMA = {
  type: "object",
  properties: {
    refuted: {
      type: "boolean",
      description: "true = this is NOT a real, in-scope bug",
    },
    reason: {
      type: "string",
      description: "one sentence justifying the verdict",
    },
  },
  required: ["refuted", "reason"],
};

// ---- the bug dimensions (one parallel finder each) ---------------------------
const DIMENSIONS = [
  {
    key: "correctness",
    lens: "Logic and control-flow defects: wrong conditionals, off-by-one, inverted boolean, incorrect return value, broken early-return, mishandled async ordering, wrong operator.",
  },
  {
    key: "wiring",
    lens: "Existence ≠ Implementation. Verify the change is actually CONNECTED: component → API call shape is consumed, handler is bound (not just declared), state is rendered (not just set), import is used, route is registered. Flag declared-but-unwired code.",
  },
  {
    key: "error-handling",
    lens: "Silent failures and missing boundary validation: swallowed errors, unhandled promise rejections, missing try/catch at I/O or network boundaries, no validation of user input / API responses / webhook payloads, error paths that return success.",
  },
  {
    key: "security",
    lens: "Injection (SQL/command/XSS), missing or bypassed auth checks, secrets or tokens hardcoded, RLS/permission gaps, unsafe eval/deserialization, SSRF, leaking sensitive data in responses or logs.", // gitleaks:allow — prompt prose, not a credential
  },
  {
    key: "stubs",
    lens: 'Incomplete implementation shipped as done: TODO/FIXME/PLACEHOLDER in a production path, `return null`/`[]`/`{}` with no real logic, empty event handlers, "not implemented", lorem-ipsum, hardcoded sample/dummy data.',
  },
  {
    key: "types-edges",
    lens: "Null/undefined dereference, unhandled edge cases (empty array, zero, negative, very large input), unsafe type coercion, missing await, race conditions, unhandled enum/union case.",
  },
];

const finderPrompt = (
  d,
) => `You are a precise QA auditor. Hunt for REAL bugs along ONE dimension only.

## Dimension: ${d.key}
${d.lens}

${scopeText}
${note ? `\nCaller note: ${note}\n` : ""}
## How to work
${diffHint}
Read enough surrounding context to be sure a finding is a genuine defect — not a guess.

## Rules
- Report ONLY real defects in your dimension. No style nits, no preferences, no "could be cleaner".
- Do NOT flag pre-existing behavior that the change didn't introduce or expose.
- Every finding needs concrete evidence: the actual offending code, quoted.
- Give file path + best-guess line number.
- If you find nothing real, return an empty findings array. An honest empty result is correct and expected.
- This is read-only. Do not edit any files.

Return your findings via the structured output schema.`;

const reproPrompt = (
  f,
) => `A QA finder reported a potential bug. Your job is to REFUTE it by checking whether it actually reproduces.

## Reported bug
- Title: ${f.title}
- Location: ${f.file}:${f.line}
- Severity: ${f.severity}
- Description: ${f.description}
- Evidence: ${f.evidence}

## Your task
Read ${f.file} and the surrounding code. Trace the concrete execution path. Try to construct a specific input or call sequence that triggers the described faulty behavior.

- If you CAN construct a concrete trigger → refuted = false.
- If you CANNOT, or the path is unreachable, or the described behavior doesn't actually occur → refuted = true.
- Default to refuted = true when uncertain. We only act on bugs we can stand behind.

Return your verdict via the structured output schema.`;

const realPrompt = (
  f,
) => `A QA finder reported a potential bug. Your job is to REFUTE it as a false positive.

## Reported bug
- Title: ${f.title}
- Location: ${f.file}:${f.line}
- Severity: ${f.severity}
- Description: ${f.description}
- Evidence: ${f.evidence}

## Your task
Read ${f.file} and the surrounding code, then decide. Set refuted = true if ANY of these hold:
- It's a style/preference nit, not a defect.
- The code is actually correct on closer reading.
- It's pre-existing behavior unrelated to the change.
- It's out of scope for the changed files.

Set refuted = false ONLY if it's a genuine defect introduced or exposed by the change.
Default to refuted = true when uncertain.

Return your verdict via the structured output schema.`;

// ---- dedupe across all finders (barrier is justified: cross-finder merge) ----
function keyOf(f) {
  const t = (f.title || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
  return `${f.file}:${f.line}:${t}`;
}
function dedupe(findings) {
  const seen = new Map();
  for (const f of findings) {
    const k = keyOf(f);
    if (!seen.has(k)) seen.set(k, f);
  }
  return [...seen.values()];
}

// ---- run ---------------------------------------------------------------------
phase("Find");
const finderResults = await parallel(
  DIMENSIONS.map(
    (d) => () =>
      agent(finderPrompt(d), {
        label: `find:${d.key}`,
        phase: "Find",
        schema: FINDINGS_SCHEMA,
      }),
  ),
);
// FALSE-GREEN GUARD (added 2026-07-11): a finder killed by a usage limit or API
// error returns null, and filter(Boolean) used to erase it — an all-dead run
// returned confirmed:[] indistinguishable from a genuinely clean audit. Caught
// manually 4+ times in the 60-session audit (twice the rerun found real bugs).
// Dead finders now poison the verdict instead of counting as clean.
const deadFinders = DIMENSIONS.filter((d, i) => !finderResults[i]).map(
  (d) => d.key,
);
if (deadFinders.length) {
  log(
    `⚠️  ${deadFinders.length}/${DIMENSIONS.length} finder agents died (${deadFinders.join(", ")}) — verdict is UNTRUSTED. Resume/rerun this workflow; do NOT treat the result as a clean pass.`,
  );
}
const raw = finderResults
  .filter(Boolean)
  .flatMap((r) => (r && r.findings) || []);
const unique = dedupe(raw);
log(
  `${raw.length} raw findings across ${DIMENSIONS.length - deadFinders.length}/${DIMENSIONS.length} surviving dimensions → ${unique.length} after dedupe`,
);

if (unique.length === 0) {
  return {
    verdict: deadFinders.length
      ? "UNTRUSTED — finder agents died; rerun required before trusting this result"
      : "clean",
    untrusted: deadFinders.length > 0,
    deadFinders,
    confirmed: [],
    unverified: [],
    stats: {
      dimensions: DIMENSIONS.length,
      deadFinders: deadFinders.length,
      raw: 0,
      deduped: 0,
      confirmed: 0,
      refuted: 0,
      unverified: 0,
    },
    scope: resolvedFiles,
    scopeWarning,
  };
}

phase("Verify");
const judged = await parallel(
  unique.map(
    (f) => () =>
      parallel([
        () =>
          agent(reproPrompt(f), {
            label: `verify-repro:${f.file}`,
            phase: "Verify",
            schema: VERDICT_SCHEMA,
          }),
        () =>
          agent(realPrompt(f), {
            label: `verify-real:${f.file}`,
            phase: "Verify",
            schema: VERDICT_SCHEMA,
          }),
      ]).then((votes) => {
        const v = votes.filter(Boolean);
        // Strict: confirm only if BOTH skeptics fail to refute. Keeps the fix loop conservative.
        // FALSE-GREEN GUARD: a dead skeptic (null vote) used to silently count as
        // a refutation. A finding with fewer than 2 live votes is UNVERIFIED, not refuted.
        const confirmed = v.length === 2 && v.every((x) => !x.refuted);
        const unverified = v.length < 2;
        return {
          ...f,
          confirmed,
          unverified,
          refutedBy: v.filter((x) => x.refuted).map((x) => x.reason),
        };
      }),
  ),
);

const order = { critical: 0, high: 1, medium: 2, low: 3 };
const bySeverity = (a, b) =>
  (order[a.severity] ?? 9) - (order[b.severity] ?? 9);
const confirmed = judged
  .filter(Boolean)
  .filter((f) => f.confirmed)
  .sort(bySeverity)
  .map(({ confirmed: _c, unverified: _u, refutedBy: _r, ...rest }) => rest);
const unverified = judged
  .filter(Boolean)
  .filter((f) => f.unverified)
  .sort(bySeverity)
  .map(({ confirmed: _c, unverified: _u, refutedBy: _r, ...rest }) => rest);

const untrusted = deadFinders.length > 0 || unverified.length > 0;
log(
  `${unique.length} findings → ${confirmed.length} confirmed, ${unverified.length} unverified (dead skeptics) after adversarial verify${untrusted ? " — verdict UNTRUSTED, rerun the dead portions" : ""}`,
);

return {
  verdict: untrusted
    ? "UNTRUSTED — dead finder/verifier agents; rerun required before trusting this result"
    : confirmed.length
      ? "findings"
      : "clean",
  untrusted,
  deadFinders,
  confirmed,
  unverified,
  stats: {
    dimensions: DIMENSIONS.length,
    deadFinders: deadFinders.length,
    raw: raw.length,
    deduped: unique.length,
    confirmed: confirmed.length,
    refuted: unique.length - confirmed.length - unverified.length,
    unverified: unverified.length,
  },
  scope: resolvedFiles,
  scopeWarning,
};
