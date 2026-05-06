"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const ORCH_ROOT = path.resolve(__dirname, "..");
const ORCH_PATH = path.resolve(
  __dirname,
  "..",
  "src",
  "symphony",
  "orchestrator.js",
);
const LINEAR_PATH = path.resolve(
  __dirname,
  "..",
  "src",
  "symphony",
  "linear.js",
);
const BUDGET_PATH = path.resolve(
  __dirname,
  "..",
  "src",
  "symphony",
  "budget.js",
);
const GIT_PATH = path.resolve(__dirname, "..", "src", "symphony", "git.js");
const VERIFIER_PATH = path.resolve(
  __dirname,
  "..",
  "src",
  "symphony",
  "verifier.js",
);
const HARNESS_PATH = path.resolve(
  __dirname,
  "..",
  "src",
  "harness",
  "index.js",
);
const MANIFEST_PATH = path.resolve(
  __dirname,
  "..",
  "src",
  "runs",
  "manifest.js",
);
const CONFIG_PATH = path.join(ORCH_ROOT, "config.json");

// Speed heartbeats up so tests run in milliseconds.
process.env.SYMPHONY_HEARTBEAT_MS = "5";

// ---------- config snapshot/restore ----------

let _origConfig = null;
let _hadConfig = false;
try {
  _origConfig = fs.readFileSync(CONFIG_PATH, "utf8");
  _hadConfig = true;
} catch (_) {
  _hadConfig = false;
}

function writeConfig(obj) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(obj, null, 2));
}

function restoreConfig() {
  if (_hadConfig) fs.writeFileSync(CONFIG_PATH, _origConfig);
  else {
    try {
      fs.unlinkSync(CONFIG_PATH);
    } catch (_) {}
  }
}

// ---------- mock injection ----------

function clearCache() {
  for (const p of [
    ORCH_PATH,
    LINEAR_PATH,
    BUDGET_PATH,
    GIT_PATH,
    VERIFIER_PATH,
    HARNESS_PATH,
    MANIFEST_PATH,
  ]) {
    delete require.cache[p];
  }
}

function injectMock(modulePath, exportsObj) {
  require.cache[modulePath] = {
    id: modulePath,
    filename: modulePath,
    loaded: true,
    exports: exportsObj,
    children: [],
    paths: [],
  };
}

function freshTmpWorkdir(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sym-orch-"));
  t.after(() => {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch (_) {}
  });
  return dir;
}

function defaultBudgetMock(overrides = {}) {
  return {
    resetDailyIfNeeded: () => {},
    isStopRequested: () => false,
    isExhausted: () => false,
    isTicketExhausted: () => false,
    record: () => {},
    state: () => ({ dailyTotal: 0, perTicket: {}, lastResetDate: "" }),
    ...overrides,
  };
}

function defaultLinearMock(overrides = {}) {
  const calls = {
    poll: [],
    transition: [],
    commentPlan: [],
    comment: [],
    label: [],
    getTicket: [],
  };
  const base = {
    _calls: calls,
    poll: async (label) => {
      calls.poll.push(label);
      return [];
    },
    transition: async (id, status) => {
      calls.transition.push([id, status]);
    },
    commentPlan: async (id, body) => {
      calls.commentPlan.push([id, body]);
      return { commentUrl: "https://linear/c/1" };
    },
    comment: async (id, body) => {
      calls.comment.push([id, body]);
    },
    label: async (id, name) => {
      calls.label.push([id, name]);
    },
    getTicket: async (id) => {
      calls.getTicket.push(id);
      return {
        id,
        title: "T " + id,
        description: "desc",
        project: { name: "" },
      };
    },
  };
  return Object.assign(base, overrides);
}

function defaultGitMock(overrides = {}) {
  const calls = {
    ensureBranch: [],
    commitAll: [],
    openPR: [],
    filesChangedSince: [],
    hasUncommittedChanges: [],
  };
  const base = {
    _calls: calls,
    ensureBranch: (workdir, branch) => {
      calls.ensureBranch.push([workdir, branch]);
    },
    commitAll: (workdir, message, paths) => {
      calls.commitAll.push([workdir, message, paths]);
    },
    currentBranch: () => "symphony/test",
    filesChangedSince: (workdir, base) => {
      calls.filesChangedSince.push([workdir, base]);
      return ["src/foo.ts"];
    },
    hasUncommittedChanges: (workdir) => {
      calls.hasUncommittedChanges.push([workdir]);
      return false;
    },
    openPR: async (workdir, opts) => {
      calls.openPR.push([workdir, opts]);
      return { url: "https://github.com/x/y/pull/1" };
    },
  };
  return Object.assign(base, overrides);
}

function defaultVerifierMock(overrides = {}) {
  const calls = { run: [] };
  const base = {
    _calls: calls,
    run: async ({ stateDir, workdir, filesChanged }) => {
      calls.run.push({ stateDir, workdir, filesChanged });
      return { passed: true, layers: {} };
    },
  };
  return Object.assign(base, overrides);
}

function makeFakeAdapter(behavior = {}) {
  // behavior.statusSeq: array of statuses to return in order; last value sticks.
  // behavior.preExitWrite: function(stateDir) -> writes plan.md before "exited".
  // behavior.collectResult: result returned by collect().
  // behavior.onSpawn: optional callback receiving the intent.
  let statusIdx = 0;
  const statusSeq = behavior.statusSeq || ["exited"];
  const handle = {
    pid: 99999,
    pgid: -99999,
    agentLog: "/tmp/fake-agent.log",
    start: new Date(),
    cancelCount: 0,
    async cancel() {
      this.cancelCount += 1;
    },
  };
  const calls = { spawn: [], status: [], collect: [], cancel: 0 };
  const adapter = {
    id: "claude-code",
    tier: 1,
    capabilities: {
      subagents: true,
      streamJsonEvents: true,
      appendSystemPrompt: true,
      budgetCap: true,
    },
    _calls: calls,
    _handle: handle,
    async spawn(intent) {
      calls.spawn.push(intent);
      if (typeof behavior.onSpawn === "function") {
        behavior.onSpawn(intent);
      }
      if (typeof behavior.preExitWrite === "function") {
        behavior.preExitWrite(intent.stateDir);
      }
      return handle;
    },
    async status(h) {
      calls.status.push(h.pid);
      const s = statusSeq[Math.min(statusIdx, statusSeq.length - 1)];
      statusIdx += 1;
      return s;
    },
    async collect(h) {
      calls.collect.push(h.pid);
      return (
        behavior.collectResult || {
          exitCode: 0,
          reason: "clean",
          filesChanged: [],
          markers: ["PLAN READY"],
        }
      );
    },
    async dispatchSubagent() {
      throw new Error("not used");
    },
  };
  return adapter;
}

function injectAll({ linear, budget, git, verifier, adapter }) {
  clearCache();
  // Real manifest module is fine — we want it to actually write the manifest.
  // But we DO need to clear it from cache so it picks up the same fs.
  // (No mock; let it run.)
  injectMock(LINEAR_PATH, linear);
  injectMock(BUDGET_PATH, budget);
  injectMock(GIT_PATH, git);
  injectMock(VERIFIER_PATH, verifier);
  injectMock(HARNESS_PATH, {
    pickAdapter: (id) => {
      if (id !== "claude-code") throw new Error("unknown adapter " + id);
      return adapter;
    },
    adapters: { "claude-code": adapter },
  });
}

function loadOrchestrator() {
  return require(ORCH_PATH);
}

// ---------- tests ----------

test("processNextTicket: stop requested -> skipped, never polls Linear", async (t) => {
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: ["/tmp/proj"] });

  const linear = defaultLinearMock();
  const budget = defaultBudgetMock({ isStopRequested: () => true });
  const git = defaultGitMock();
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter();

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.processNextTicket();
  assert.deepEqual(result, { skipped: "stop-requested" });
  assert.equal(linear._calls.poll.length, 0, "should not poll Linear");
  assert.equal(adapter._calls.spawn.length, 0, "should not spawn adapter");
});

test("processNextTicket: budget exhausted -> skipped, never polls Linear", async (t) => {
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: ["/tmp/proj"] });

  const linear = defaultLinearMock();
  const budget = defaultBudgetMock({ isExhausted: () => true });
  const git = defaultGitMock();
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter();

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.processNextTicket();
  assert.deepEqual(result, { skipped: "budget-exhausted" });
  assert.equal(linear._calls.poll.length, 0);
  assert.equal(adapter._calls.spawn.length, 0);
});

test("processNextTicket: missing LINEAR_API_KEY -> graceful skip", async (t) => {
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: ["/tmp/proj"] });

  const linear = defaultLinearMock({
    poll: async () => {
      throw new Error(
        "LINEAR_API_KEY not configured in config.json — Symphony idle",
      );
    },
  });
  const budget = defaultBudgetMock();
  const git = defaultGitMock();
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter();

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.processNextTicket();
  assert.deepEqual(result, { skipped: "missing-linear-key" });
  assert.equal(adapter._calls.spawn.length, 0);
});

test("processTicket happy path: planning -> commentPlan -> awaiting-approval", async (t) => {
  const workdir = freshTmpWorkdir(t);
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: [workdir] });

  const ticket = {
    id: "TKT-1",
    title: "Add foo",
    description: "Body of ticket",
    project: { name: path.basename(workdir) },
  };

  const linear = defaultLinearMock({
    poll: async () => [ticket],
  });
  const budget = defaultBudgetMock();
  const git = defaultGitMock();
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter({
    statusSeq: ["exited"],
    preExitWrite: (stateDir) => {
      fs.mkdirSync(stateDir, { recursive: true });
      fs.writeFileSync(path.join(stateDir, "plan.md"), "# Plan\nDo the thing.");
    },
  });

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.processNextTicket();
  assert.deepEqual(result, { processed: "TKT-1" });

  // transition called with planning + awaiting-approval
  const transitionStatuses = linear._calls.transition.map((c) => c[1]);
  assert.ok(
    transitionStatuses.includes("Symphony Planning"),
    "transitions should include Symphony Planning",
  );
  assert.ok(
    transitionStatuses.includes("Awaiting Plan Approval"),
    "transitions should include Awaiting Plan Approval",
  );

  // commentPlan called with the plan body
  assert.equal(linear._calls.commentPlan.length, 1);
  assert.match(linear._calls.commentPlan[0][1], /# Plan/);

  // adapter spawn called with the right system prompt
  assert.equal(adapter._calls.spawn.length, 1);
  const intent = adapter._calls.spawn[0];
  assert.match(intent.systemPromptFile, /symphony-plan\.md$/);
  assert.equal(intent.workdir, workdir);

  // manifest written and reflects awaiting-approval
  const manifestPath = path.join(
    workdir,
    ".symphony",
    "issues",
    "TKT-1",
    "manifest.json",
  );
  assert.equal(fs.existsSync(manifestPath), true, "manifest.json written");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  assert.equal(manifest.status, "awaiting-approval");
  assert.equal(manifest.phase, "awaiting-approval");
  assert.equal(manifest.linearTicketId, "TKT-1");

  // lock released
  const lockPath = path.join(workdir, ".symphony", "issues", "TKT-1", ".lock");
  assert.equal(fs.existsSync(lockPath), false, "lock released after planning");
});

test("processTicket: per-ticket budget exhausted mid-spawn -> cancel + Blocked (AC4)", async (t) => {
  const workdir = freshTmpWorkdir(t);
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: [workdir] });

  const ticket = {
    id: "TKT-2",
    title: "T2",
    description: "",
    project: { name: path.basename(workdir) },
  };

  let tickCount = 0;
  const linear = defaultLinearMock({
    poll: async () => [ticket],
  });
  const budget = defaultBudgetMock({
    // After the first heartbeat tick, budget is exhausted for this ticket.
    isTicketExhausted: () => {
      tickCount += 1;
      return tickCount >= 1;
    },
  });
  const git = defaultGitMock();
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter({
    // Stay running so heartbeat sees the budget flip.
    statusSeq: ["running", "running", "running"],
  });

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.processNextTicket();
  // The orchestrator throws inside processTicket, processNextTicket converts
  // that into { error: ... }.
  assert.ok(
    result.error,
    "expected error result, got: " + JSON.stringify(result),
  );
  assert.equal(adapter._handle.cancelCount >= 1, true, "cancel was called");

  // Comment includes 'exceeded budget'
  const budgetComment = linear._calls.comment.find((c) =>
    /exceeded budget/.test(c[1]),
  );
  assert.ok(budgetComment, "expected an 'exceeded budget' comment");

  // Transition to Blocked
  const transitionStatuses = linear._calls.transition.map((c) => c[1]);
  assert.ok(
    transitionStatuses.includes("Blocked"),
    "transitions should include Blocked",
  );
});

test("onApproval happy path: ensureBranch + spawn + openPR (AC2)", async (t) => {
  const workdir = freshTmpWorkdir(t);
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: [workdir] });

  // Pre-write the plan.md (planning phase already finished in a previous run)
  const stateDir = path.join(workdir, ".symphony", "issues", "TKT-3");
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(path.join(stateDir, "plan.md"), "# Approved Plan\nDetails.");

  const ticket = {
    id: "TKT-3",
    title: "Add bar",
    description: "Body",
    project: { name: path.basename(workdir) },
  };

  const linear = defaultLinearMock({
    getTicket: async () => ticket,
  });
  const budget = defaultBudgetMock();
  const git = defaultGitMock({
    filesChangedSince: () => ["src/bar.ts"],
    hasUncommittedChanges: () => false,
  });
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter({
    statusSeq: ["exited"],
  });

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.onApproval("TKT-3");
  assert.deepEqual(result, { prUrl: "https://github.com/x/y/pull/1" });

  // ensureBranch called with symphony/<id>
  assert.equal(git._calls.ensureBranch.length, 1);
  assert.deepEqual(git._calls.ensureBranch[0], [workdir, "symphony/TKT-3"]);

  // adapter.spawn called once for the executor
  assert.equal(adapter._calls.spawn.length, 1);
  assert.match(
    adapter._calls.spawn[0].systemPromptFile,
    /symphony-execute\.md$/,
  );
  assert.equal(adapter._calls.spawn[0].prompt, "/autopilot resume");

  // openPR called with label and Closes <id> in body
  assert.equal(git._calls.openPR.length, 1);
  const prCall = git._calls.openPR[0][1];
  assert.equal(prCall.label, "symphony:verified-rich");
  assert.match(prCall.body, /Closes TKT-3/);
  assert.match(prCall.title, /^Symphony: /);
  assert.equal(prCall.base, "main");

  // approved-plan.md written
  assert.equal(
    fs.existsSync(path.join(stateDir, "approved-plan.md")),
    true,
    "approved-plan.md copied",
  );

  // manifest reflects in-review
  const manifest = JSON.parse(
    fs.readFileSync(path.join(stateDir, "manifest.json"), "utf8"),
  );
  assert.equal(manifest.status, "completed");
  assert.equal(manifest.phase, "in-review");
});

test("onApproval: verification fails -> Blocked, no PR", async (t) => {
  const workdir = freshTmpWorkdir(t);
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: [workdir] });

  const stateDir = path.join(workdir, ".symphony", "issues", "TKT-4");
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(path.join(stateDir, "plan.md"), "plan");

  const ticket = {
    id: "TKT-4",
    title: "T4",
    description: "",
    project: { name: path.basename(workdir) },
  };

  const linear = defaultLinearMock({ getTicket: async () => ticket });
  const budget = defaultBudgetMock();
  const git = defaultGitMock({
    filesChangedSince: () => ["src/x.ts"],
    hasUncommittedChanges: () => false,
  });
  const verifier = defaultVerifierMock({
    run: async () => ({ passed: false, layers: { tsc: { passed: false } } }),
  });
  const adapter = makeFakeAdapter({ statusSeq: ["exited"] });

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  const result = await orch.onApproval("TKT-4");
  assert.equal(result.error, "verification failed");
  assert.equal(
    git._calls.openPR.length,
    0,
    "no PR opened on verification fail",
  );
  const transitionStatuses = linear._calls.transition.map((c) => c[1]);
  assert.ok(transitionStatuses.includes("Blocked"));
});

test("onRejection: comments + transitions to rejected", async (t) => {
  const workdir = freshTmpWorkdir(t);
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: [workdir] });

  const linear = defaultLinearMock();
  const budget = defaultBudgetMock();
  const git = defaultGitMock();
  const verifier = defaultVerifierMock();
  const adapter = makeFakeAdapter();

  injectAll({ linear, budget, git, verifier, adapter });
  const orch = loadOrchestrator();

  await orch.onRejection("TKT-9", "needs more detail");

  assert.equal(linear._calls.comment.length, 1);
  assert.match(linear._calls.comment[0][1], /Plan rejected: needs more detail/);
  const transitionStatuses = linear._calls.transition.map((c) => c[1]);
  assert.ok(transitionStatuses.includes("Plan Rejected"));
});

test("module exports the four documented functions", async (t) => {
  t.after(() => {
    restoreConfig();
    clearCache();
  });
  writeConfig({ port: 7890, directories: ["/tmp/proj"] });

  // Use real modules via clearCache only (no inject) — just verify shape.
  clearCache();
  const orch = require(ORCH_PATH);
  assert.equal(typeof orch.processNextTicket, "function");
  assert.equal(typeof orch.processTicket, "function");
  assert.equal(typeof orch.onApproval, "function");
  assert.equal(typeof orch.onRejection, "function");
});

// =====================================================================
// acquireLockWithRetry — added in lock-contention robustness fix
// =====================================================================

// Reuses fs / path / os / test / assert from top of this file.
const assertStrict = assert;

test("acquireLockWithRetry: returns true when lock is free", async () => {
  const orch = require("../src/symphony/orchestrator");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "orch-lock-1-"));
  const ok = await orch._internals.acquireLockWithRetry(tmp, {
    maxWaitMs: 1000,
    backoffMs: 50,
  });
  assertStrict.equal(ok, true);
  assertStrict.ok(fs.existsSync(path.join(tmp, ".lock")));
  orch._internals.releaseLock(tmp);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test("acquireLockWithRetry: waits then succeeds when lock released mid-flight", async () => {
  const orch = require("../src/symphony/orchestrator");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "orch-lock-2-"));
  // Pre-create the lock
  fs.writeFileSync(path.join(tmp, ".lock"), "holder");
  // Release after 300ms
  setTimeout(() => orch._internals.releaseLock(tmp), 300);
  const start = Date.now();
  const ok = await orch._internals.acquireLockWithRetry(tmp, {
    maxWaitMs: 5000,
    backoffMs: 100,
  });
  const waited = Date.now() - start;
  assertStrict.equal(ok, true);
  assertStrict.ok(
    waited >= 200 && waited < 2000,
    `waited=${waited}ms outside expected 200-2000`,
  );
  orch._internals.releaseLock(tmp);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test("acquireLockWithRetry: returns false on timeout", async () => {
  const orch = require("../src/symphony/orchestrator");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "orch-lock-3-"));
  fs.writeFileSync(path.join(tmp, ".lock"), "holder");
  const start = Date.now();
  const ok = await orch._internals.acquireLockWithRetry(tmp, {
    maxWaitMs: 500,
    backoffMs: 100,
  });
  const waited = Date.now() - start;
  assertStrict.equal(ok, false);
  assertStrict.ok(waited >= 400, `waited=${waited}ms expected >=400`);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test("acquireLockWithRetry: reclaims stale lock (>staleMs old)", async () => {
  const orch = require("../src/symphony/orchestrator");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "orch-lock-4-"));
  const lockPath = path.join(tmp, ".lock");
  fs.writeFileSync(lockPath, "stale-holder");
  // Backdate lock mtime by 1 hour
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
  fs.utimesSync(lockPath, oneHourAgo, oneHourAgo);
  const ok = await orch._internals.acquireLockWithRetry(tmp, {
    maxWaitMs: 1000,
    backoffMs: 50,
    staleMs: 30 * 60 * 1000, // 30 min
  });
  assertStrict.equal(ok, true, "should have reclaimed stale lock");
  orch._internals.releaseLock(tmp);
  fs.rmSync(tmp, { recursive: true, force: true });
});
