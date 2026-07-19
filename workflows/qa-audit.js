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
        "two adversarial skeptics per finding (cross-model: one fable, one opus); confirm only if neither refutes",
    },
  ],
};

// ---- args: { files?: string[], base?: string, note?: string } ----------------
// files: changed files to focus on (from `git diff` in the caller). Optional.
// base:  git ref to diff against (default HEAD). Optional.
//
// ARGS GUARD — background-launched workflows can hand `args` over as a JSON STRING
// rather than an object, so never assume an object. Parse a string form FIRST so a
// stringified `{files:[...]}` can still be recovered into a real array before we
// judge its shape.
let parsedArgs = args;
if (typeof parsedArgs === "string") {
  try {
    parsedArgs = JSON.parse(parsedArgs);
  } catch (e) {
    parsedArgs = null;
  }
}

// `files` may arrive as the whole args (a bare array) or as parsedArgs.files.
const rawFiles = Array.isArray(parsedArgs)
  ? parsedArgs
  : parsedArgs && typeof parsedArgs === "object"
    ? parsedArgs.files
    : undefined;

// Change 1 — THROW on a malformed `files` (observed false-green #1): a caller once
// passed `files` as a JSON-encoded STRING; the script treated it as [] → git-diff
// fallback on a committed tree → 0 files → a clean-looking verdict (replayed twice
// from cache). Any whole-args JSON string was already parsed above, so if `files`
// is STILL not an array here it cannot be recovered — fail loudly instead of
// silently auditing nothing. (undefined / null = "not passed" and is allowed —
// that path resolves scope from git and then refuses on 0 files; see Change 3.)
if (rawFiles !== undefined && rawFiles !== null && !Array.isArray(rawFiles)) {
  throw new Error(
    `qa-audit: \`files\` must be an array of paths, got ${typeof rawFiles} (${JSON.stringify(rawFiles).slice(0, 80)}). ` +
      `This is the background-args stringification bug — callers sometimes JSON-encode the args ` +
      `(or the file list) into a string, which used to be silently treated as empty scope and fall ` +
      `back to git-diff: a false-green audit. Pass the parsed shape:  args: {files: ["a.ts", "b.ts"]}  ` +
      `— NOT  args: "{\\"files\\":[\\"a.ts\\"]}".`,
  );
}

const files = Array.isArray(rawFiles) ? rawFiles : [];
const base =
  (parsedArgs &&
    typeof parsedArgs === "object" &&
    typeof parsedArgs.base === "string" &&
    parsedArgs.base) ||
  "HEAD";
const note =
  (parsedArgs &&
    typeof parsedArgs === "object" &&
    typeof parsedArgs.note === "string" &&
    parsedArgs.note) ||
  "";

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

// ---- scope resolution -------------------------------------------------------
// Failure mode (observed repeatedly in real runs): when this workflow is called
// with prose instead of {files:[...]}, `files` is [] and finders silently fall
// back to `git diff HEAD` — which, inside an autopilot worktree or against a
// wrong base, audits an unrelated tree. Worse, `git diff` MISSES untracked files,
// so brand-new edge functions / migrations (the session's riskiest artifacts) were
// never audited and most finders returned empty. We now (a) union untracked files
// into the diff-derived scope and (b) REFUSE to dispatch on a 0-file scope, so an
// unverified scope can never mint a clean-looking verdict.
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
        description:
          "relative paths of TRACKED changed source files (git diff / --staged)",
      },
      untrackedFiles: {
        type: "array",
        items: { type: "string" },
        description:
          "relative paths of UNTRACKED source files from `git status --porcelain` (?? lines), directories expanded to their files, same extension filter as changedFiles",
      },
      empty: {
        type: "boolean",
        description:
          "true only if BOTH the tracked and untracked sets are empty after filtering",
      },
    },
    required: ["changedFiles", "empty"],
  };
  const scope = await agent(
    `Resolve the QA audit scope (read-only — do not edit anything).

Gather the changed-file set from these sources and return them:
1. TRACKED changes: run \`git diff --name-only ${base}\`. If that is empty, also try \`git diff --name-only --staged\`.
2. UNTRACKED files — \`git diff\` does NOT list these, and brand-new files (a new edge function, a new migration) are often the most security-sensitive artifacts of a session: run \`git status --porcelain\` and take every line whose status is \`??\`. For any \`??\` entry that is a DIRECTORY (the path ends with \`/\`), expand it to its individual files with \`git ls-files --others --exclude-standard -- <dir>\` (or \`find <dir> -type f\`). Never return a bare directory path.

Filtering (apply to BOTH sets):
- Keep ONLY source-code files with these extensions: ts, tsx, js, jsx, mjs, py, sql, toml, json, sh, go, rs.
- Skip lockfiles (package-lock.json, yarn.lock, pnpm-lock.yaml, Cargo.lock, poetry.lock), build output (dist/, .next/, out/, build/), node_modules, and any generated artifacts — even when their extension is in the list above.

Return via structured output:
- changedFiles: the TRACKED source files (step 1, filtered).
- untrackedFiles: the UNTRACKED source files (step 2, directories expanded, filtered).
- empty: true only if BOTH sets are genuinely empty after filtering.`,
    {
      label: "scope:resolve",
      phase: "Scope",
      schema: SCOPE_SCHEMA,
      model: "opus",
    },
  );
  const trackedFiles =
    scope && Array.isArray(scope.changedFiles) ? scope.changedFiles : [];
  const untrackedFiles =
    scope && Array.isArray(scope.untrackedFiles) ? scope.untrackedFiles : [];
  // Change 2 — union untracked files into the diff-derived scope (deduped).
  resolvedFiles = [...new Set([...trackedFiles, ...untrackedFiles])];
  if (resolvedFiles.length) {
    log(
      `Resolved empty scope → ${resolvedFiles.length} changed file(s) (${trackedFiles.length} tracked + ${untrackedFiles.length} untracked) via git diff ${base} ∪ git status --porcelain`,
    );
  } else {
    scopeWarning = `qa-audit was called with no explicit file scope and \`git diff ${base}\` ∪ untracked files (git status --porcelain) resolved to 0 changed source files. Auditing would run against the wrong tree (the known scope:[] false-green). Refusing to dispatch — pass {files:[...]} or the correct base and rerun.`;
    log(`⚠️  ${scopeWarning}`);
  }
}

// Change 3 — REFUSE to dispatch on a 0-file scope. An empty scope used to warn but
// still run finders on the git-diff fallback and return a verdict that reads as a
// pass. Instead return the UNTRUSTED shape immediately, BEFORE any finder is
// dispatched, so a 0-file scope can NEVER be mistaken for a clean audit.
if (!resolvedFiles.length) {
  const reason =
    scopeWarning ||
    `qa-audit resolved 0 files in scope (explicit empty \`files\` and an empty diff). Refusing to dispatch finders.`;
  log(`⛔ Empty scope — refusing to dispatch finders; returning UNTRUSTED.`);
  return {
    verdict:
      "UNTRUSTED — 0-file scope; refused to dispatch finders (an empty scope audits nothing and would return a false-green pass)",
    untrusted: true,
    error: "empty_scope",
    deadFinders: [],
    confirmed: [],
    unverified: [],
    stats: {
      dimensions: DIMENSIONS.length,
      deadFinders: 0,
      raw: 0,
      deduped: 0,
      confirmed: 0,
      refuted: 0,
      unverified: 0,
    },
    scope: resolvedFiles,
    scopeWarning: reason,
  };
}

// Change 4 — scope-hash the finder cache identity. Workflow resume caching replays
// agent() calls whose (prompt, opts) are unchanged; a previous run's EMPTY finder
// results must never be replayed for a DIFFERENT resolved scope. A djb2 hex of the
// sorted file list is folded into every finder's label + prompt so the cache key
// moves whenever the scope moves. (No crypto, no Date.now / Math.random — those are
// unavailable in the workflow sandbox.)
function djb2Hex(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h * 33) ^ str.charCodeAt(i)) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}
const scopeHash = djb2Hex([...resolvedFiles].sort().join("\n"));

// Scope is guaranteed non-empty past the Change 3 refusal.
const scopeText = `Scope — focus ONLY on these changed files:\n${resolvedFiles
  .map((f) => `  - ${f}`)
  .join("\n")}`;

const diffHint = `Run \`git diff ${base} -- ${resolvedFiles.join(" ")}\` to see what changed in TRACKED files, then read the surrounding context with the Read tool before judging. Some scoped files are brand-new UNTRACKED files (e.g. a new edge function or migration) that will NOT appear in \`git diff\` — read those in full with the Read tool and audit them as newly-added code. FIRST confirm each file exists; only skip a file if it genuinely does not exist.`;

// ---- finder / skeptic prompts ------------------------------------------------
const finderPrompt = (
  d,
) => `You are a precise QA auditor. Hunt for REAL bugs along ONE dimension only.
[scope ${scopeHash}]

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
// MODEL PINS (2026-07-19, per CLAUDE.md "split by leverage, verifier ≠ author"):
// every agent() call pins a model explicitly — an unpinned call inherits the
// session model, which on a Fable session silently runs the whole fleet on
// Fable (the drift this fixes). Finders are breadth/recall work → opus. The
// skeptic pair is the precision gate that decides "confirmed" → cross-model
// (repro on fable, false-positive on opus): implementers run opus, so the
// fable skeptic restores the second-opinion dynamic at 1× findings exposure.
phase("Find");
const finderResults = await parallel(
  DIMENSIONS.map(
    (d) => () =>
      agent(finderPrompt(d), {
        label: `find:${d.key}:${scopeHash}`,
        phase: "Find",
        schema: FINDINGS_SCHEMA,
        model: "opus",
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
            model: "fable",
          }),
        () =>
          agent(realPrompt(f), {
            label: `verify-real:${f.file}`,
            phase: "Verify",
            schema: VERDICT_SCHEMA,
            model: "opus",
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
