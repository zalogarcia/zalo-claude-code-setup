"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const BUDGET_PATH = require.resolve("../src/symphony/budget.js");

function freshHome() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "symphony-budget-"));
  return dir;
}

function withFreshHome(t) {
  const prevHome = process.env.HOME;
  const tmp = freshHome();
  process.env.HOME = tmp;
  // budget.js uses os.homedir(); on POSIX, os.homedir() honors $HOME.
  delete require.cache[BUDGET_PATH];
  const budget = require(BUDGET_PATH);
  t.after(() => {
    process.env.HOME = prevHome;
    delete require.cache[BUDGET_PATH];
    try {
      fs.rmSync(tmp, { recursive: true, force: true });
    } catch {}
  });
  return { tmp, budget };
}

function readState(home) {
  const file = path.join(home, ".symphony", "budget.json");
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

test("atomic write + read roundtrip persists dailyTotal and perTicket", (t) => {
  const { tmp, budget } = withFreshHome(t);

  budget.record(5.0, "T-1");

  const file = path.join(tmp, ".symphony", "budget.json");
  assert.equal(fs.existsSync(file), true, "state file written");
  const persisted = readState(tmp);
  assert.equal(persisted.dailyTotal, 5);
  assert.equal(persisted.perTicket["T-1"], 5);
  assert.equal(typeof persisted.lastResetDate, "string");

  // .tmp file should NOT remain (rename completed)
  assert.equal(
    fs.existsSync(file + ".tmp"),
    false,
    "tmp file cleaned up by rename",
  );
});

test("resetDailyIfNeeded zeros state when lastResetDate is yesterday", (t) => {
  const { tmp, budget } = withFreshHome(t);

  budget.record(7.5, "T-2");
  let s = readState(tmp);
  assert.equal(s.dailyTotal, 7.5);

  // Tamper with lastResetDate to be yesterday.
  s.lastResetDate = "2000-01-01";
  fs.writeFileSync(
    path.join(tmp, ".symphony", "budget.json"),
    JSON.stringify(s, null, 2),
  );

  budget.resetDailyIfNeeded();

  const after = readState(tmp);
  assert.equal(after.dailyTotal, 0);
  assert.deepEqual(after.perTicket, {});
  assert.equal(after.lastResetDate, new Date().toISOString().slice(0, 10));
});

test("AC3: isExhausted returns true once dailyTotal exceeds $20", (t) => {
  const { budget } = withFreshHome(t);

  budget.record(20.005, "T-1");
  budget.record(0.01, "T-1");

  assert.equal(budget.isExhausted(), true);
});

test("isExhausted is false at or below $20", (t) => {
  const { budget } = withFreshHome(t);

  budget.record(10, "T-x");
  budget.record(10, "T-y");
  // dailyTotal = 20.0 — not strictly greater than 20
  assert.equal(budget.isExhausted(), false);
});

test("isTicketExhausted returns true once a ticket exceeds $10", (t) => {
  const { budget } = withFreshHome(t);

  budget.record(10.005, "T-1");
  budget.record(0.01, "T-1");

  assert.equal(budget.isTicketExhausted("T-1"), true);
  assert.equal(budget.isTicketExhausted("T-other"), false);
});

test("isStopRequested flips true when STOP file exists", (t) => {
  const { tmp, budget } = withFreshHome(t);

  assert.equal(budget.isStopRequested(), false);

  fs.mkdirSync(path.join(tmp, ".symphony"), { recursive: true });
  fs.writeFileSync(path.join(tmp, ".symphony", "STOP"), "");

  assert.equal(budget.isStopRequested(), true);
});

test("killAll SIGTERMs registered PIDs that handle the signal", async (t) => {
  const { budget } = withFreshHome(t);

  // Child handles SIGTERM by exiting cleanly.
  const child = spawn(
    process.execPath,
    [
      "-e",
      "process.on('SIGTERM', () => process.exit(0)); setInterval(() => {}, 1000);",
    ],
    { stdio: "ignore", detached: false },
  );

  const exited = new Promise((resolve) => child.on("exit", resolve));
  // Give child a moment to install the SIGTERM handler.
  await new Promise((r) => setTimeout(r, 200));

  budget.registerPid(child.pid);

  const result = await budget.killAll();
  assert.equal(result.killed >= 1, true, "at least one PID signaled");
  // Child caught SIGTERM cleanly, so SIGKILL not needed.
  assert.equal(result.sigkilled, 0);

  // Child should be gone.
  await exited;
  let alive = true;
  try {
    process.kill(child.pid, 0);
  } catch {
    alive = false;
  }
  assert.equal(alive, false, "child no longer running");
});

test("killAll SIGKILLs children that ignore SIGTERM", async (t) => {
  const { budget } = withFreshHome(t);

  // Child ignores SIGTERM entirely.
  const child = spawn(
    process.execPath,
    ["-e", "process.on('SIGTERM', () => {}); setInterval(() => {}, 1000);"],
    { stdio: "ignore", detached: false },
  );

  const exited = new Promise((resolve) => child.on("exit", resolve));
  await new Promise((r) => setTimeout(r, 200));

  budget.registerPid(child.pid);

  const result = await budget.killAll();
  assert.equal(result.sigkilled >= 1, true, "SIGKILL fired for ignoring child");

  // Give the kernel a beat to reap the killed process.
  await Promise.race([exited, new Promise((r) => setTimeout(r, 1000))]);

  let alive = true;
  try {
    process.kill(child.pid, 0);
  } catch {
    alive = false;
  }
  assert.equal(alive, false, "child reaped after SIGKILL");
});
