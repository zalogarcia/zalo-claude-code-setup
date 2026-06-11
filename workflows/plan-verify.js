export const meta = {
  name: "plan-verify",
  description:
    "Plan Verification Loop: brainstorm-vet + principles-grader in parallel, then one safe-planner revision pass if either flags concerns. Mirrors ~/.claude/rules/plan-verification.md.",
  whenToUse:
    "The verification half of /plan (Steps 4-5). The interactive questioning and initial plan generation stay in the main thread; this runs the autonomous gates + revision.",
  phases: [
    {
      title: "Verify",
      detail: "Gate 1 (brainstorm) + Gate 2 (outcomes-grader) in parallel",
      model: "opus",
    },
    {
      title: "Revise",
      detail: "one safe-planner revision pass, only if a gate flagged concerns",
      model: "opus",
    },
  ],
};

// ---- args: { runDir: string } ------------------------------------------------
// runDir is the resolved .claude/.plan/<run-id>/ path. Agents read
// `${runDir}/task.md` and `${runDir}/plan.md` from disk; the revision agent
// overwrites `${runDir}/plan.md` in place.
const runDir =
  (args && typeof args.runDir === "string" && args.runDir) ||
  (typeof args === "string" ? args : null);

if (!runDir) {
  return {
    error: "plan-verify requires args.runDir (path to .claude/.plan/<run-id>/)",
  };
}

const taskPath = `${runDir}/task.md`;
const planPath = `${runDir}/plan.md`;

// ---- schemas -----------------------------------------------------------------
const BRAINSTORM_SCHEMA = {
  type: "object",
  properties: {
    hasSignificantConcerns: {
      type: "boolean",
      description:
        "true ONLY for correctness/completeness/scope issues worth a revision pass — not mere observations",
    },
    concerns: {
      type: "array",
      items: {
        type: "object",
        properties: {
          severity: { type: "string", enum: ["high", "medium", "low"] },
          issue: { type: "string" },
          suggestion: { type: "string" },
        },
        required: ["severity", "issue"],
      },
    },
    scaleGame: {
      type: "object",
      description:
        "MANDATORY when the plan involves architectural components, data flow, or throughput-relevant work",
      properties: {
        applicable: { type: "boolean" },
        at0_1x: {
          type: "string",
          description: "bottleneck + failure mode at 0.1x scale, or N/A",
        },
        at10x: {
          type: "string",
          description: "bottleneck + failure mode at 10x scale, or N/A",
        },
      },
      required: ["applicable"],
    },
    summary: { type: "string" },
  },
  required: ["hasSignificantConcerns", "concerns", "summary"],
};

const GRADER_SCHEMA = {
  type: "object",
  properties: {
    allApplicablePass: { type: "boolean" },
    failedItems: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: {
            type: "string",
            description: 'rubric outcome id, e.g. "3.1" or "Outcome 2.2"',
          },
          verdict: { type: "string", enum: ["FAIL", "AMBIGUOUS"] },
          evidence: {
            type: "string",
            description: "quoted plan text showing the violation",
          },
          whatsMissing: { type: "string" },
        },
        required: ["id", "verdict", "whatsMissing"],
      },
    },
    summary: { type: "string" },
  },
  required: ["allApplicablePass", "failedItems", "summary"],
};

const REVISION_SCHEMA = {
  type: "object",
  properties: {
    changesSummary: {
      type: "string",
      description: "what changed in the revised plan",
    },
    unresolvedConcerns: {
      type: "array",
      items: { type: "string" },
      description:
        "concerns from the review that could NOT be fully addressed without scope creep",
    },
  },
  required: ["changesSummary"],
};

// ---- gate prompts (mirror ~/.claude/rules/plan-verification.md) ---------------
const brainstormPrompt = `We produced a plan via safe-planner. Apply your critical-thinking pass.

## Original task
Read ${taskPath}

## Plan to evaluate
Read ${planPath}

## What to do
- Apply inversion: "what if the opposite assumption were true?"
- Apply the simplification cascade: "what would eliminate 5+ steps with one insight?"
- Apply the scale game (MANDATORY if the plan involves architectural components, data flow, or throughput-relevant work): at 0.1x scale, what's the bottleneck and the specific failure mode? At 10x scale, same. If the plan is purely cosmetic/refactor with no architectural surface, set scaleGame.applicable=false. Vague answers like "works fine at scale" are not acceptable — name a specific component and a specific user-observable failure mode.
- Apply meta-pattern recognition: have you seen this shape elsewhere — does an established pattern apply?
- Identify hidden assumptions, missing considerations, scope creep, premature optimization, single points of failure, unhandled edge cases, missing rollback paths.

Don't rubber-stamp. If the plan is sound, set hasSignificantConcerns=false and say so concisely. Set hasSignificantConcerns=true ONLY for correctness/completeness/scope issues that warrant a revision pass (not mere observations). Return your critique via the structured output schema.`;

const graderPrompt = `You are grading a PLAN (markdown describing intended work, not code). Apply your plan-grading mode.

## Artifact (the plan to grade)
Read ${planPath}

## Rubric
Read ~/.claude/rules/engineering-principles.md

For each rubric item with an "Applicable when:" clause, first determine applicability. If not applicable to this plan, mark it PASS with reason "not applicable: <clause>". For applicable items, return PASS / FAIL with concrete evidence quoted from the plan. Use AMBIGUOUS only if applicability itself is unclear.

Evidence must be quoted plan text — do NOT run greps, file checks, or build commands; the plan describes work that does not exist on disk yet. (Reading the plan artifact and the rubric is fine; verifying against a nonexistent implementation is not.)

Set allApplicablePass=true only if EVERY applicable item passes. List every FAIL/AMBIGUOUS item in failedItems with its id, the quoted evidence, and what's missing. Return via the structured output schema.`;

// ---- run: Gate 1 + Gate 2 in parallel ----------------------------------------
phase("Verify");
const [brainstorm, principles] = await parallel([
  () =>
    agent(brainstormPrompt, {
      label: "gate1:brainstorm",
      phase: "Verify",
      agentType: "brainstorm",
      model: "opus",
      schema: BRAINSTORM_SCHEMA,
    }),
  () =>
    agent(graderPrompt, {
      label: "gate2:outcomes-grader",
      phase: "Verify",
      agentType: "outcomes-grader",
      model: "opus",
      schema: GRADER_SCHEMA,
    }),
]);

if (!brainstorm && !principles) {
  return { error: "both verification gates failed to return" };
}

const bsConcerns = brainstorm ? !!brainstorm.hasSignificantConcerns : false;
const grPass = principles ? !!principles.allApplicablePass : true;
const revise = bsConcerns || !grPass;

// ---- build the combined findings markdown (orchestrator writes it to disk) ----
function brainstormBlock(b) {
  if (!b) return "_Gate 1 (brainstorm) did not return._";
  const lines = [b.summary || ""];
  lines.push("");
  lines.push(
    b.concerns && b.concerns.length
      ? b.concerns
          .map(
            (c) =>
              `- [${c.severity}] ${c.issue}${c.suggestion ? ` — ${c.suggestion}` : ""}`,
          )
          .join("\n")
      : "_No significant concerns._",
  );
  if (b.scaleGame && b.scaleGame.applicable) {
    lines.push(
      "",
      "**Scale game:**",
      `- 0.1x: ${b.scaleGame.at0_1x || "—"}`,
      `- 10x: ${b.scaleGame.at10x || "—"}`,
    );
  }
  return lines.join("\n");
}
function principlesBlock(p) {
  if (!p) return "_Gate 2 (outcomes-grader) did not return._";
  const head = p.summary || "";
  const body =
    p.failedItems && p.failedItems.length
      ? p.failedItems
          .map(
            (i) =>
              `- **${i.id}** (${i.verdict}): ${i.evidence ? `${i.evidence} — ` : ""}_missing:_ ${i.whatsMissing}`,
          )
          .join("\n")
      : "_All applicable items passed._";
  return `${head}\n\n${body}`;
}

const verificationMarkdown = [
  "# Plan Verification Findings",
  "",
  "## Brainstorm findings (Gate 1)",
  "",
  brainstormBlock(brainstorm),
  "",
  "## Principles findings (Gate 2)",
  "",
  principlesBlock(principles),
  "",
].join("\n");

log(
  `Gate 1 concerns: ${bsConcerns} | Gate 2 allApplicablePass: ${grPass} → revision ${revise ? "NEEDED" : "not needed"}`,
);

// ---- conditional single revision pass ----------------------------------------
let revised = false;
let revisionSummary = null;
let unresolvedConcerns = [];

if (revise) {
  phase("Revise");
  const bsText =
    brainstorm && brainstorm.concerns && brainstorm.concerns.length
      ? brainstorm.concerns
          .map(
            (c) =>
              `- [${c.severity}] ${c.issue}${c.suggestion ? ` (suggestion: ${c.suggestion})` : ""}`,
          )
          .join("\n")
      : brainstorm
        ? brainstorm.summary
        : "(none)";
  const grText =
    principles && principles.failedItems && principles.failedItems.length
      ? principles.failedItems
          .map(
            (i) =>
              `- ${i.id} (${i.verdict}): ${i.whatsMissing}${i.evidence ? ` [evidence: ${i.evidence}]` : ""}`,
          )
          .join("\n")
      : "(none)";

  const revisionPrompt = `The plan you produced was reviewed. Address the issues below.

## Original task
Read ${taskPath}

## Current plan
Read ${planPath}

## Brainstorm critique
${bsText}

## Principles violations
${grText}

Revise the plan to address each issue. Keep what works. Don't expand scope beyond the original task. Overwrite ${planPath} in place with the revised plan, preserving the same structured format (work units with IDs, files, dependencies, agent type, complexity; parallelizable batches; migrations; testing strategy; risks and rollback).

Return a short changesSummary and list any concerns you could NOT fully resolve without scope creep in unresolvedConcerns.`;

  const rev = await agent(revisionPrompt, {
    label: "revise:safe-planner",
    phase: "Revise",
    agentType: "safe-planner",
    model: "opus",
    schema: REVISION_SCHEMA,
  });

  if (rev) {
    revised = true;
    revisionSummary = rev.changesSummary || null;
    unresolvedConcerns = Array.isArray(rev.unresolvedConcerns)
      ? rev.unresolvedConcerns
      : [];
  } else {
    // Revision was needed but the agent did not return — surface as unresolved.
    unresolvedConcerns = [
      "revision pass did not complete; plan.md left at its pre-revision state",
    ];
  }
}

return {
  passed: !revise,
  revised,
  revisionSummary,
  unresolvedConcerns,
  brainstorm,
  principles,
  verificationMarkdown,
};
