#!/usr/bin/env node
// Tests for ~/.claude/workflows/qa-audit.js
//
// Workflow scripts are plain JS with a top-level `return`, so they cannot be
// imported or `node --check`ed directly. This harness wraps the source in an
// async function and injects stub implementations of the workflow globals
// (agent / parallel / pipeline / log / phase / args), which lets the real
// control flow run offline with scripted agent outcomes.
//
// Run:  node ~/.claude/workflows/qa-audit.test.mjs
//
// Coverage focus (2026-08-28 audit, P4 "QA fails closed"):
//   - a dead agent is re-dispatched once on the other model tier
//   - a recovered retry keeps the run trustworthy
//   - an agent dead on BOTH tiers fails the workflow (throw), never returns
//   - empty scope and a dead scope agent are distinct failures

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = fs.readFileSync(path.join(HERE, "qa-audit.js"), "utf8");

// `export const meta` is workflow-runner syntax; strip the keyword to run it here.
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

// `agentFn(prompt, opts)` is supplied per test. It receives the same arguments
// the real runner would and returns the structured object (or null for death).
function runWorkflow({ agentFn, args = undefined, quiet = true }) {
  const logs = [];
  const fn = new Function(
    "agent",
    "parallel",
    "pipeline",
    "log",
    "phase",
    "args",
    `return (async () => {\n${BODY}\n})();`,
  );
  return {
    logs,
    promise: fn(
      agentFn,
      parallelStub,
      pipelineStub,
      (m) => {
        logs.push(String(m));
        if (!quiet) console.log("   log:", m);
      },
      () => {},
      args,
    ),
  };
}

const FINDING = {
  file: "src/a.ts",
  line: 12,
  severity: "high",
  title: "unchecked null deref",
  description: "x may be undefined",
  evidence: "return x.y",
};

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

async function expectThrow(name, runner, matcher) {
  try {
    const out = await runner();
    check(name, false, `expected a throw, got ${JSON.stringify(out).slice(0, 120)}`);
  } catch (e) {
    check(name, matcher(e), `message was: ${e.message.slice(0, 160)}`);
  }
}

// ---------------------------------------------------------------------------
console.log("qa-audit.js");

// 1. Happy path: explicit scope, all agents alive, both skeptics decline to refute.
{
  const calls = [];
  const agentFn = async (prompt, opts) => {
    calls.push(opts.label);
    if (opts.label.startsWith("find:correctness")) return { findings: [FINDING] };
    if (opts.label.startsWith("find:")) return { findings: [] };
    if (opts.label.startsWith("verify:") || opts.label.startsWith("verify-"))
      return { refuted: false, reason: "reproduces" };
    return null;
  };
  const { promise } = runWorkflow({
    agentFn,
    args: { files: ["src/a.ts"] },
  });
  const out = await promise;
  check("happy path returns a verdict", out.verdict === "findings", out.verdict);
  check("happy path is trusted", out.untrusted === false);
  check("happy path confirms the finding", out.confirmed.length === 1);
  check("happy path retried nobody", out.stats.retried === 0);
  check(
    "happy path dispatched 6 finders",
    calls.filter((c) => c.startsWith("find:")).length === 6,
    calls.join(","),
  );
}

// 2. A finder dies on its pinned model but recovers on the cross-model retry.
{
  const calls = [];
  let securityAttempts = 0;
  const agentFn = async (prompt, opts) => {
    calls.push(opts.label);
    if (opts.label.startsWith("find:security")) {
      securityAttempts += 1;
      if (securityAttempts === 1) return null; // dies on opus
      return { findings: [] }; // recovers on the fable retry
    }
    if (opts.label.startsWith("find:")) return { findings: [] };
    return null;
  };
  const { promise } = runWorkflow({ agentFn, args: { files: ["src/a.ts"] } });
  const out = await promise;
  check("dead finder is retried once", securityAttempts === 2, `${securityAttempts}`);
  check(
    "retry swaps opus to fable",
    calls.some((c) => c === "find:security:" + calls[0].split(":")[2] + ":retry-fable") ||
      calls.some((c) => c.endsWith(":retry-fable")),
    calls.join(","),
  );
  check("recovered run is trusted", out.untrusted === false);
  check("recovered run is clean", out.verdict === "clean");
  check("recovery is reported in stats", out.stats.retried === 1, `${out.stats.retried}`);
}

// 3. A finder dead on BOTH tiers fails the workflow instead of returning clean.
await expectThrow(
  "finder dead on both tiers throws (not a clean return)",
  async () => {
    const agentFn = async (prompt, opts) => {
      if (opts.label.startsWith("find:security")) return null;
      if (opts.label.startsWith("find:")) return { findings: [] };
      return null;
    };
    return (await runWorkflow({ agentFn, args: { files: ["src/a.ts"] } }).promise);
  },
  (e) =>
    e.message.includes("QA_AUDIT_RED_GATE") &&
    e.message.includes("dead_finders") &&
    e.message.includes("resumeFromRunId"),
);

// 4. A skeptic dead on both tiers leaves the finding unverified: also a throw,
//    and the partial findings ride along in the error payload for triage.
await expectThrow(
  "dead skeptic throws and carries the partial payload",
  async () => {
    const agentFn = async (prompt, opts) => {
      if (opts.label.startsWith("find:correctness")) return { findings: [FINDING] };
      if (opts.label.startsWith("find:")) return { findings: [] };
      if (opts.label.startsWith("verify-repro")) return null; // dead on both tiers
      if (opts.label.startsWith("verify-real")) return { refuted: false, reason: "real" };
      return null;
    };
    return (await runWorkflow({ agentFn, args: { files: ["src/a.ts"] } }).promise);
  },
  (e) =>
    e.message.includes("QA_AUDIT_RED_GATE") &&
    e.message.includes("dead_agents") &&
    e.message.includes("unchecked null deref"),
);

// 5. Empty resolved scope throws with the caller-error guidance (no resume).
await expectThrow(
  "empty scope throws empty_scope and says do NOT resume",
  async () => {
    const agentFn = async (prompt, opts) => {
      if (opts.label.startsWith("scope:resolve"))
        return { changedFiles: [], untrackedFiles: [], empty: true };
      return null;
    };
    return (await runWorkflow({ agentFn, args: {} }).promise);
  },
  (e) =>
    e.message.includes("empty_scope") && e.message.includes("Do NOT resume"),
);

// 6. A dead scope agent is NOT an empty scope: distinct class, distinct advice.
await expectThrow(
  "dead scope agent throws scope_agent_died, not empty_scope",
  async () => {
    const agentFn = async () => null;
    return (await runWorkflow({ agentFn, args: {} }).promise);
  },
  (e) =>
    e.message.includes("scope_agent_died") && !e.message.includes("[empty_scope]"),
);

// 7. Pre-existing guard still holds: a stringified `files` arg throws loudly.
await expectThrow(
  "stringified files arg still throws",
  async () =>
    (await runWorkflow({
      agentFn: async () => null,
      args: { files: '["src/a.ts"]' },
    }).promise),
  (e) => e.message.includes("must be an array of paths"),
);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
