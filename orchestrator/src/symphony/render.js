"use strict";

/**
 * Server-side data-shaping helpers for Symphony dashboard endpoints.
 *
 * Pure data shaping over the filesystem — no HTTP, no Linear writes.
 * Defensive throughout: every file read is wrapped so a missing file
 * returns null instead of throwing.
 *
 * Exports:
 *   - symphonyRuns(config)            -> Promise<Run[]>
 *   - ticketAggregate(config, ticketId) -> Promise<Aggregate>
 *   - budgetSnapshot(config)          -> { dailyUsd, spentToday, remaining, perTicket }
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const { readManifest } = require("../runs/manifest");
const budget = require("./budget");
const linear = require("./linear");

const DEFAULT_DAILY_BUDGET_USD = 20;

/** Safe directory listing — returns [] on any error. */
function safeReaddir(dir) {
  try {
    return fs.readdirSync(dir);
  } catch (_err) {
    return [];
  }
}

/** Returns true if path exists AND is a directory. */
function isDir(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch (_err) {
    return false;
  }
}

/** Read a text file; return null on any error. */
function safeReadText(filePath) {
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch (_err) {
    return null;
  }
}

/** Read a JSON file; return null on any error (missing file, parse error). */
function safeReadJson(filePath) {
  try {
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw);
  } catch (_err) {
    return null;
  }
}

/** Stable short hash for synthesizing run ids when manifest is missing. */
function shortHash(input) {
  return crypto.createHash("sha1").update(input).digest("hex").slice(0, 12);
}

/**
 * Synthesize a minimal Run shape for an issue dir lacking a manifest.
 *
 * @param {string} workdir
 * @param {string} issueDir
 * @returns {object}
 */
function inferRun(workdir, issueDir) {
  const ticketId = path.basename(issueDir);
  return {
    id: shortHash(issueDir),
    type: "symphony",
    stateDir: issueDir,
    workdir,
    status: "idle",
    linearTicketId: ticketId,
  };
}

/**
 * Collect all Symphony runs across configured workdirs.
 *
 * Scans `<workdir>/.symphony/issues/<ticketId>/` for each workdir in
 * `config.directories`. For each issue dir, prefers the persisted
 * manifest; falls back to a minimal inferred Run when the manifest
 * is missing or unreadable.
 *
 * Result is sorted by `startedAt` desc; entries without a startedAt
 * (or with an unparseable value) sort last.
 *
 * @param {{directories?: string[]}} config
 * @returns {Promise<object[]>}
 */
async function symphonyRuns(config) {
  const directories = Array.isArray(config && config.directories)
    ? config.directories
    : [];

  const runs = [];
  for (const workdir of directories) {
    if (typeof workdir !== "string" || !workdir) continue;
    const issuesDir = path.join(workdir, ".symphony", "issues");
    if (!isDir(issuesDir)) continue;

    const issueNames = safeReaddir(issuesDir);
    for (const name of issueNames) {
      const issueDir = path.join(issuesDir, name);
      if (!isDir(issueDir)) continue;

      const manifest = readManifest(issueDir);
      const run = manifest ? manifest : inferRun(workdir, issueDir);
      // Ensure stateDir/workdir are populated even when manifest omits them.
      if (!run.stateDir) run.stateDir = issueDir;
      if (!run.workdir) run.workdir = workdir;
      if (!run.linearTicketId) run.linearTicketId = path.basename(issueDir);
      runs.push(run);
    }
  }

  runs.sort((a, b) => {
    const ta = Date.parse(a && a.startedAt);
    const tb = Date.parse(b && b.startedAt);
    const aValid = !Number.isNaN(ta);
    const bValid = !Number.isNaN(tb);
    if (aValid && bValid) return tb - ta;
    if (aValid) return -1;
    if (bValid) return 1;
    return 0;
  });

  return runs;
}

/**
 * Build the aggregate payload for `/api/symphony/ticket/:id`.
 *
 * Locates the ticket among Symphony runs, then reads `plan.md`,
 * `approved-plan.md`, `verification.json`, and the manifest. Pulls
 * the per-ticket budget spend. Tries to fetch the live Linear issue;
 * on any failure (missing API key, network), `ticket` is null and
 * `ticketError` carries the error message.
 *
 * @param {{directories?: string[]}} config
 * @param {string} ticketId
 * @returns {Promise<object>}
 */
async function ticketAggregate(config, ticketId) {
  const runs = await symphonyRuns(config);
  const match = runs.find((r) => r && r.linearTicketId === ticketId);

  const stateDir = match ? match.stateDir : null;
  const workdir = match ? match.workdir : null;
  const manifest = match || null;

  let plan = null;
  let approvedPlan = null;
  let verification = null;
  if (stateDir) {
    plan = safeReadText(path.join(stateDir, "plan.md"));
    approvedPlan = safeReadText(path.join(stateDir, "approved-plan.md"));
    verification = safeReadJson(path.join(stateDir, "verification.json"));
  }

  const status =
    (manifest && (manifest.phase || manifest.status)) ||
    (verification && verification.passed === true ? "verified" : null) ||
    (approvedPlan ? "executing" : null) ||
    (plan ? "awaiting-approval" : "idle");

  let ticketSpend = 0;
  try {
    const s = budget.state();
    if (s && s.perTicket && typeof s.perTicket[ticketId] === "number") {
      ticketSpend = s.perTicket[ticketId];
    }
  } catch (_err) {
    ticketSpend = 0;
  }

  let ticket = null;
  let ticketError = null;
  try {
    ticket = await linear.getTicket(ticketId);
  } catch (err) {
    ticket = null;
    ticketError = err && err.message ? err.message : String(err);
  }

  const result = {
    ticket,
    plan,
    approvedPlan,
    status,
    verification,
    manifest,
    stateDir,
    workdir,
    budget: { ticketSpend },
  };
  if (ticketError) result.ticketError = ticketError;
  return result;
}

/**
 * Read the daily budget cap from `config.symphony.dailyBudgetUsd`,
 * defaulting to 20. Defensive — falls back on any structural issue.
 *
 * @param {object} config
 * @returns {number}
 */
function resolveDailyBudgetUsd(config) {
  const sym = config && config.symphony;
  if (sym && typeof sym.dailyBudgetUsd === "number") {
    return sym.dailyBudgetUsd;
  }
  return DEFAULT_DAILY_BUDGET_USD;
}

/**
 * Snapshot of today's Symphony budget — daily cap, spend so far,
 * remaining headroom, and the per-ticket breakdown.
 *
 * @param {object} config
 * @returns {{dailyUsd: number, spentToday: number, remaining: number, perTicket: object}}
 */
function budgetSnapshot(config) {
  const dailyUsd = resolveDailyBudgetUsd(config);
  let dailyTotal = 0;
  let perTicket = {};
  try {
    const s = budget.state();
    dailyTotal = typeof s.dailyTotal === "number" ? s.dailyTotal : 0;
    perTicket =
      s.perTicket && typeof s.perTicket === "object" ? s.perTicket : {};
  } catch (_err) {
    dailyTotal = 0;
    perTicket = {};
  }
  return {
    dailyUsd,
    spentToday: dailyTotal,
    remaining: dailyUsd - dailyTotal,
    perTicket,
  };
}

module.exports = {
  symphonyRuns,
  ticketAggregate,
  budgetSnapshot,
};
