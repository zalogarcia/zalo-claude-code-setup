"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const HOME_DIR = () => os.homedir();
const SYMPHONY_DIR = () => path.join(HOME_DIR(), ".symphony");
const STATE_FILE = () => path.join(SYMPHONY_DIR(), "budget.json");
const PIDS_FILE = () => path.join(SYMPHONY_DIR(), "registered-pids.log");
const STOP_FILE = () => path.join(SYMPHONY_DIR(), "STOP");

const CONFIG_PATH = path.join(__dirname, "..", "..", "config.json");

const DEFAULT_CONFIG = {
  dailyBudgetUsd: 20,
  perTicketBudgetUsd: 10,
};

function ensureDir() {
  fs.mkdirSync(SYMPHONY_DIR(), { recursive: true });
}

function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, "utf8");
      const parsed = JSON.parse(raw);
      const sym = (parsed && parsed.symphony) || {};
      return {
        symphony: {
          dailyBudgetUsd:
            typeof sym.dailyBudgetUsd === "number"
              ? sym.dailyBudgetUsd
              : DEFAULT_CONFIG.dailyBudgetUsd,
          perTicketBudgetUsd:
            typeof sym.perTicketBudgetUsd === "number"
              ? sym.perTicketBudgetUsd
              : DEFAULT_CONFIG.perTicketBudgetUsd,
        },
      };
    }
  } catch (err) {
    console.error("[budget] failed to read config.json:", err.message);
  }
  return { symphony: { ...DEFAULT_CONFIG } };
}

function readState() {
  ensureDir();
  const file = STATE_FILE();
  if (!fs.existsSync(file)) {
    return { dailyTotal: 0, perTicket: {}, lastResetDate: todayUtc() };
  }
  try {
    const raw = fs.readFileSync(file, "utf8");
    const parsed = JSON.parse(raw);
    return {
      dailyTotal: typeof parsed.dailyTotal === "number" ? parsed.dailyTotal : 0,
      perTicket:
        parsed.perTicket && typeof parsed.perTicket === "object"
          ? parsed.perTicket
          : {},
      lastResetDate:
        typeof parsed.lastResetDate === "string"
          ? parsed.lastResetDate
          : todayUtc(),
    };
  } catch (err) {
    console.error("[budget] state file unreadable, resetting:", err.message);
    return { dailyTotal: 0, perTicket: {}, lastResetDate: todayUtc() };
  }
}

function writeStateAtomic(state) {
  ensureDir();
  const file = STATE_FILE();
  const tmp = file + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2));
  fs.renameSync(tmp, file);
}

function applyDailyReset(state) {
  const today = todayUtc();
  if (state.lastResetDate !== today) {
    state.dailyTotal = 0;
    state.perTicket = {};
    state.lastResetDate = today;
    return true;
  }
  return false;
}

function resetDailyIfNeeded() {
  const state = readState();
  if (applyDailyReset(state)) {
    writeStateAtomic(state);
  }
}

function record(usd, ticketId) {
  ensureDir();
  if (typeof usd !== "number" || !isFinite(usd)) {
    throw new TypeError("record: usd must be a finite number");
  }
  if (!ticketId || typeof ticketId !== "string") {
    throw new TypeError("record: ticketId must be a non-empty string");
  }
  const state = readState();
  applyDailyReset(state);
  state.dailyTotal = (state.dailyTotal || 0) + usd;
  state.perTicket[ticketId] = (state.perTicket[ticketId] || 0) + usd;
  writeStateAtomic(state);
}

function state() {
  const s = readState();
  applyDailyReset(s);
  return {
    dailyTotal: s.dailyTotal,
    perTicket: { ...s.perTicket },
    lastResetDate: s.lastResetDate,
  };
}

function isExhausted() {
  resetDailyIfNeeded();
  const cfg = loadConfig();
  const s = readState();
  return (s.dailyTotal || 0) > cfg.symphony.dailyBudgetUsd;
}

function isTicketExhausted(ticketId) {
  resetDailyIfNeeded();
  const cfg = loadConfig();
  const s = readState();
  return (s.perTicket[ticketId] || 0) > cfg.symphony.perTicketBudgetUsd;
}

function isStopRequested() {
  try {
    return fs.existsSync(STOP_FILE());
  } catch (err) {
    console.error("[budget] isStopRequested check failed:", err.message);
    return false;
  }
}

function registerPid(pid) {
  ensureDir();
  if (!Number.isInteger(pid) || pid <= 0) {
    throw new TypeError("registerPid: pid must be a positive integer");
  }
  fs.appendFileSync(PIDS_FILE(), `${pid}\n`);
}

function unregisterPid(pid) {
  ensureDir();
  if (!Number.isInteger(pid) || pid <= 0) {
    throw new TypeError("unregisterPid: pid must be a positive integer");
  }
  const file = PIDS_FILE();
  if (!fs.existsSync(file)) return;
  let raw;
  try {
    raw = fs.readFileSync(file, "utf8");
  } catch (err) {
    console.error("[budget] unregisterPid read failed:", err.message);
    return;
  }
  const lines = raw.split("\n").filter((l) => l.trim() !== "");
  const target = String(pid);
  const remaining = lines.filter((l) => l.trim() !== target);
  const tmp = file + ".tmp";
  fs.writeFileSync(tmp, remaining.length ? remaining.join("\n") + "\n" : "");
  fs.renameSync(tmp, file);
}

function readRegisteredPids() {
  const file = PIDS_FILE();
  if (!fs.existsSync(file)) return [];
  try {
    const raw = fs.readFileSync(file, "utf8");
    const out = [];
    for (const line of raw.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      const n = Number(t);
      if (Number.isInteger(n) && n > 0) out.push(n);
    }
    return out;
  } catch (err) {
    console.error("[budget] readRegisteredPids failed:", err.message);
    return [];
  }
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function killAll() {
  ensureDir();
  const pids = readRegisteredPids();
  let killed = 0;
  let sigkilled = 0;

  for (const pid of pids) {
    try {
      process.kill(pid, "SIGTERM");
      killed += 1;
    } catch (err) {
      // ESRCH = no such process; ignore. Other errors swallowed too.
    }
  }

  await sleep(5000);

  for (const pid of pids) {
    if (isAlive(pid)) {
      try {
        process.kill(pid, "SIGKILL");
        sigkilled += 1;
      } catch {
        // swallow
      }
    }
  }

  // Truncate the log file
  try {
    fs.writeFileSync(PIDS_FILE(), "");
  } catch (err) {
    console.error("[budget] killAll truncate failed:", err.message);
  }

  return { killed, sigkilled };
}

module.exports = {
  record,
  isExhausted,
  isTicketExhausted,
  killAll,
  resetDailyIfNeeded,
  isStopRequested,
  registerPid,
  unregisterPid,
  state,
};
