"use strict";

/**
 * Symphony orchestrator — per-ticket flow.
 *
 * Stage 2 implementation. Reads tickets from Linear, spawns the planning
 * adapter, comments the plan, waits for human approval, and on approval
 * spawns the executor + verifier and opens a PR.
 *
 * Exports:
 *   - processNextTicket()        — entry called by POST /api/symphony/poll
 *   - processTicket(ticket)      — process a single ticket through planning
 *   - onApproval(ticketId)       — execute + verify + open PR after human approval
 *   - onRejection(ticketId, why) — comment + transition to a "rejected" state
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");

const ORCHESTRATOR_ROOT = path.resolve(__dirname, "..", "..");
const CONFIG_PATH = path.join(ORCHESTRATOR_ROOT, "config.json");

// Config defaults. Overridden by config.json keys when present.
const DEFAULTS = {
  linear: {
    planLabel: "claude:plan-me",
    planningStatus: "Symphony Planning",
    awaitingApprovalStatus: "Awaiting Plan Approval",
    blockedStatus: "Blocked",
    inReviewStatus: "In Review",
    rejectedStatus: "Plan Rejected",
  },
  symphony: {
    prTier1Label: "symphony:verified-rich",
    prBaseBranch: "main",
    planBudgetUsd: 2,
    executeBudgetUsd: 8,
  },
};

// ---------- helpers ----------

function loadConfig() {
  try {
    const raw = fs.readFileSync(CONFIG_PATH, "utf8");
    const parsed = JSON.parse(raw);
    return parsed || {};
  } catch (_err) {
    return {};
  }
}

function getLinearCfg() {
  const cfg = loadConfig();
  const lin = (cfg && cfg.linear) || {};
  return {
    planLabel: lin.planLabel || DEFAULTS.linear.planLabel,
    planningStatus: lin.planningStatus || DEFAULTS.linear.planningStatus,
    awaitingApprovalStatus:
      lin.awaitingApprovalStatus || DEFAULTS.linear.awaitingApprovalStatus,
    blockedStatus: lin.blockedStatus || DEFAULTS.linear.blockedStatus,
    inReviewStatus: lin.inReviewStatus || DEFAULTS.linear.inReviewStatus,
    rejectedStatus: lin.rejectedStatus || DEFAULTS.linear.rejectedStatus,
  };
}

function getSymphonyCfg() {
  const cfg = loadConfig();
  const sym = (cfg && cfg.symphony) || {};
  return {
    prTier1Label: sym.prTier1Label || DEFAULTS.symphony.prTier1Label,
    prBaseBranch: sym.prBaseBranch || DEFAULTS.symphony.prBaseBranch,
    planBudgetUsd:
      typeof sym.planBudgetUsd === "number"
        ? sym.planBudgetUsd
        : DEFAULTS.symphony.planBudgetUsd,
    executeBudgetUsd:
      typeof sym.executeBudgetUsd === "number"
        ? sym.executeBudgetUsd
        : DEFAULTS.symphony.executeBudgetUsd,
  };
}

function heartbeatMs() {
  const v = parseInt(process.env.SYMPHONY_HEARTBEAT_MS || "", 10);
  if (Number.isFinite(v) && v > 0) return v;
  return 5000;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shortHash(input) {
  return crypto
    .createHash("sha1")
    .update(String(input))
    .digest("hex")
    .slice(0, 12);
}

/**
 * Resolve which configured project directory to use for a given ticket.
 *
 * Stage 2 simplest viable resolution:
 *   - If `directories` has exactly one entry → use it.
 *   - Else, match `ticket.project.name` against the basename of each entry;
 *     fall back to the first entry on no match.
 *   - Empty array → throw.
 */
function resolveWorkdir(ticket) {
  const cfg = loadConfig();
  const dirs = Array.isArray(cfg.directories) ? cfg.directories : [];
  if (dirs.length === 0) {
    throw new Error("No project directories configured in config.json");
  }
  if (dirs.length === 1) return dirs[0];
  const projectName =
    ticket && ticket.project && typeof ticket.project.name === "string"
      ? ticket.project.name
      : "";
  if (projectName) {
    for (const d of dirs) {
      if (path.basename(d) === projectName) return d;
    }
  }
  return dirs[0];
}

function ticketStateDir(workdir, ticketId) {
  return path.join(workdir, ".symphony", "issues", ticketId);
}

function tryAcquireLock(stateDir) {
  fs.mkdirSync(stateDir, { recursive: true });
  const lockPath = path.join(stateDir, ".lock");
  try {
    const fd = fs.openSync(lockPath, "wx");
    fs.closeSync(fd);
    return true;
  } catch (err) {
    if (err && err.code === "EEXIST") return false;
    throw err;
  }
}

function releaseLock(stateDir) {
  try {
    fs.unlinkSync(path.join(stateDir, ".lock"));
  } catch (_err) {
    /* lock already released or never existed */
  }
}

function lockExists(stateDir) {
  try {
    return fs.existsSync(path.join(stateDir, ".lock"));
  } catch (_err) {
    return false;
  }
}

// ---------- core flows ----------

/**
 * Heartbeat-poll the adapter handle until it exits or a kill condition trips.
 *
 * Returns an object describing the loop's outcome:
 *   { exited: true }                                 — adapter said 'exited'
 *   { exited: false, reason: 'stop-requested' }      — STOP file appeared
 *   { exited: false, reason: 'budget-exhausted' }    — per-ticket budget exhausted
 */
async function heartbeatUntilExit(adapter, handle, budget, ticketId) {
  const interval = heartbeatMs();
  // Loop bound is virtually unlimited; the adapter or budget halts us.
  // Tests use a small interval and stub status() to flip to 'exited' quickly.
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const status = await adapter.status(handle);
    if (status === "exited" || status === "crashed") {
      return { exited: true };
    }
    if (budget.isStopRequested && budget.isStopRequested()) {
      try {
        await handle.cancel();
      } catch (_err) {
        /* best-effort */
      }
      return { exited: false, reason: "stop-requested" };
    }
    if (
      budget.isTicketExhausted &&
      ticketId &&
      budget.isTicketExhausted(ticketId)
    ) {
      try {
        await handle.cancel();
      } catch (_err) {
        /* best-effort */
      }
      return { exited: false, reason: "budget-exhausted" };
    }
    await sleep(interval);
  }
}

async function processNextTicket() {
  const linear = require("./linear");
  const budget = require("./budget");

  budget.resetDailyIfNeeded();

  if (budget.isStopRequested()) {
    return { skipped: "stop-requested" };
  }
  if (budget.isExhausted()) {
    return { skipped: "budget-exhausted" };
  }

  const linCfg = getLinearCfg();
  let tickets;
  try {
    tickets = await linear.poll(linCfg.planLabel);
  } catch (err) {
    if (err && /LINEAR_API_KEY/.test(err.message)) {
      return { skipped: "missing-linear-key" };
    }
    return { error: (err && err.message) || String(err) };
  }

  if (!Array.isArray(tickets) || tickets.length === 0) {
    return { skipped: "no-eligible-tickets" };
  }

  // Pick the first ticket without an existing lock.
  let chosen = null;
  let chosenWorkdir = null;
  for (const ticket of tickets) {
    let wd;
    try {
      wd = resolveWorkdir(ticket);
    } catch (err) {
      return { error: (err && err.message) || String(err) };
    }
    const sd = ticketStateDir(wd, ticket.id);
    if (!lockExists(sd)) {
      chosen = ticket;
      chosenWorkdir = wd;
      break;
    }
  }

  if (!chosen) {
    return { skipped: "no-eligible-tickets" };
  }

  try {
    await processTicket(chosen, { workdir: chosenWorkdir });
  } catch (err) {
    return { error: (err && err.message) || String(err) };
  }
  return { processed: chosen.id };
}

async function processTicket(ticket, opts) {
  if (!ticket || !ticket.id) {
    throw new Error("processTicket: ticket.id is required");
  }
  const linear = require("./linear");
  const budget = require("./budget");
  const { pickAdapter } = require("../harness");
  const manifest = require("../runs/manifest");

  const workdir = (opts && opts.workdir) || resolveWorkdir(ticket);
  const stateDir = ticketStateDir(workdir, ticket.id);

  // Acquire lock.
  if (!tryAcquireLock(stateDir)) {
    throw new Error("locked");
  }

  let lockHeld = true;
  try {
    const linCfg = getLinearCfg();
    const symCfg = getSymphonyCfg();

    manifest.writeManifest(stateDir, {
      id: shortHash(stateDir),
      type: "symphony",
      harness: "claude-code",
      workdir,
      stateDir,
      status: "running",
      phase: "planning",
      linearTicketId: ticket.id,
      manifestVersion: 1,
      startedAt: new Date().toISOString(),
    });

    await linear.transition(ticket.id, linCfg.planningStatus);

    const intent = {
      type: "symphony",
      workdir,
      stateDir,
      prompt: (ticket.title || "") + "\n\n" + (ticket.description || ""),
      systemPromptFile: path.join(
        os.homedir(),
        ".claude",
        "commands",
        "symphony-plan.md",
      ),
      budgetUsd: symCfg.planBudgetUsd,
    };

    const adapter = pickAdapter("claude-code");
    const handle = await adapter.spawn(intent);

    const outcome = await heartbeatUntilExit(
      adapter,
      handle,
      budget,
      ticket.id,
    );

    if (!outcome.exited) {
      if (outcome.reason === "stop-requested") {
        await linear.comment(ticket.id, "Stop requested — Symphony halted");
        releaseLock(stateDir);
        lockHeld = false;
        throw new Error("Stop requested");
      }
      if (outcome.reason === "budget-exhausted") {
        await linear.comment(
          ticket.id,
          "exceeded budget — needs decomposition",
        );
        try {
          await linear.transition(ticket.id, linCfg.blockedStatus);
        } catch (err) {
          process.stderr.write(
            "[orchestrator] transition to Blocked failed: " +
              ((err && err.message) || String(err)) +
              "\n",
          );
        }
        releaseLock(stateDir);
        lockHeld = false;
        throw new Error("budget-exhausted");
      }
    }

    await adapter.collect(handle);

    const planPath = path.join(stateDir, "plan.md");
    let plan;
    try {
      plan = fs.readFileSync(planPath, "utf8");
    } catch (_err) {
      throw new Error("Planner did not write plan.md");
    }

    await linear.commentPlan(ticket.id, plan);
    await linear.transition(ticket.id, linCfg.awaitingApprovalStatus);

    manifest.writeManifest(stateDir, {
      id: shortHash(stateDir),
      type: "symphony",
      harness: "claude-code",
      workdir,
      stateDir,
      status: "awaiting-approval",
      phase: "awaiting-approval",
      linearTicketId: ticket.id,
      manifestVersion: 1,
      startedAt: new Date().toISOString(),
    });
  } finally {
    if (lockHeld) releaseLock(stateDir);
  }
}

async function onApproval(ticketId) {
  if (!ticketId) {
    return { error: "ticketId is required" };
  }

  const linear = require("./linear");
  const budget = require("./budget");
  const git = require("./git");
  const verifier = require("./verifier");
  const { pickAdapter } = require("../harness");
  const manifest = require("../runs/manifest");

  const linCfg = getLinearCfg();
  const symCfg = getSymphonyCfg();

  // Look up the ticket so we can resolve workdir + use its title in the PR.
  let ticket;
  try {
    ticket = await linear.getTicket(ticketId);
  } catch (err) {
    if (err && /LINEAR_API_KEY/.test(err.message)) {
      return { error: "missing-linear-key" };
    }
    return { error: (err && err.message) || String(err) };
  }
  if (!ticket) {
    return { error: "ticket-not-found" };
  }

  let workdir;
  try {
    workdir = resolveWorkdir(ticket);
  } catch (err) {
    return { error: (err && err.message) || String(err) };
  }
  const stateDir = ticketStateDir(workdir, ticketId);

  if (!tryAcquireLock(stateDir)) {
    return { error: "locked" };
  }

  let lockHeld = true;
  try {
    const planPath = path.join(stateDir, "plan.md");
    if (!fs.existsSync(planPath)) {
      return { error: "no plan" };
    }
    const approvedPath = path.join(stateDir, "approved-plan.md");
    fs.copyFileSync(planPath, approvedPath);

    const branch = "symphony/" + ticketId;
    git.ensureBranch(workdir, branch);

    const adapter = pickAdapter("claude-code");
    const intent = {
      type: "symphony",
      workdir,
      stateDir,
      prompt: "/autopilot resume",
      systemPromptFile: path.join(
        os.homedir(),
        ".claude",
        "commands",
        "symphony-execute.md",
      ),
      budgetUsd: symCfg.executeBudgetUsd,
    };

    const handle = await adapter.spawn(intent);
    const outcome = await heartbeatUntilExit(adapter, handle, budget, ticketId);

    if (!outcome.exited) {
      if (outcome.reason === "stop-requested") {
        await linear.comment(ticketId, "Stop requested — Symphony halted");
        return { error: "stop-requested" };
      }
      if (outcome.reason === "budget-exhausted") {
        await linear.comment(ticketId, "exceeded budget — needs decomposition");
        try {
          await linear.transition(ticketId, linCfg.blockedStatus);
        } catch (err) {
          process.stderr.write(
            "[orchestrator] transition to Blocked failed: " +
              ((err && err.message) || String(err)) +
              "\n",
          );
        }
        return { error: "budget-exhausted" };
      }
    }

    await adapter.collect(handle);

    const filesChanged = git.filesChangedSince(workdir, symCfg.prBaseBranch);
    if (!Array.isArray(filesChanged) || filesChanged.length === 0) {
      await linear.comment(ticketId, "Executor produced no changes");
      try {
        await linear.transition(ticketId, linCfg.blockedStatus);
      } catch (err) {
        process.stderr.write(
          "[orchestrator] transition to Blocked failed: " +
            ((err && err.message) || String(err)) +
            "\n",
        );
      }
      return { error: "no changes" };
    }

    if (git.hasUncommittedChanges(workdir)) {
      await linear.comment(
        ticketId,
        "Executor left uncommitted changes; refusing to open PR",
      );
      try {
        await linear.transition(ticketId, linCfg.blockedStatus);
      } catch (err) {
        process.stderr.write(
          "[orchestrator] transition to Blocked failed: " +
            ((err && err.message) || String(err)) +
            "\n",
        );
      }
      return { error: "uncommitted changes" };
    }

    const verification = await verifier.run({
      stateDir,
      workdir,
      filesChanged,
    });
    if (!verification || !verification.passed) {
      const layers =
        verification && verification.layers
          ? JSON.stringify(verification.layers)
          : "{}";
      await linear.comment(ticketId, "Verification failed: layers=" + layers);
      try {
        await linear.transition(ticketId, linCfg.blockedStatus);
      } catch (err) {
        process.stderr.write(
          "[orchestrator] transition to Blocked failed: " +
            ((err && err.message) || String(err)) +
            "\n",
        );
      }
      return { error: "verification failed" };
    }

    let planBody = "";
    try {
      planBody = fs.readFileSync(approvedPath, "utf8");
    } catch (_err) {
      planBody = "";
    }

    const prResult = await git.openPR(workdir, {
      title: "Symphony: " + (ticket.title || ticketId),
      body: planBody + "\n\nCloses " + ticketId,
      label: symCfg.prTier1Label,
      base: symCfg.prBaseBranch,
    });

    await linear.comment(ticketId, "PR: " + prResult.url);
    await linear.transition(ticketId, linCfg.inReviewStatus);

    manifest.writeManifest(stateDir, {
      id: shortHash(stateDir),
      type: "symphony",
      harness: "claude-code",
      workdir,
      stateDir,
      status: "completed",
      phase: "in-review",
      linearTicketId: ticketId,
      manifestVersion: 1,
      startedAt: new Date().toISOString(),
    });

    return { prUrl: prResult.url };
  } finally {
    if (lockHeld) releaseLock(stateDir);
  }
}

async function onRejection(ticketId, reason) {
  const linear = require("./linear");
  if (!ticketId) return;
  const linCfg = getLinearCfg();
  try {
    await linear.comment(
      ticketId,
      "Plan rejected: " + (reason || "no reason given"),
    );
  } catch (err) {
    process.stderr.write(
      "[orchestrator] rejection comment failed: " +
        ((err && err.message) || String(err)) +
        "\n",
    );
  }
  try {
    await linear.transition(ticketId, linCfg.rejectedStatus);
  } catch (err) {
    process.stderr.write(
      "[orchestrator] rejection transition failed: " +
        ((err && err.message) || String(err)) +
        "\n",
    );
  }

  // Best-effort: if a state lock is hanging around for this ticket, drop it.
  try {
    const cfg = loadConfig();
    const dirs = Array.isArray(cfg.directories) ? cfg.directories : [];
    for (const d of dirs) {
      const sd = ticketStateDir(d, ticketId);
      releaseLock(sd);
    }
  } catch (_err) {
    /* best-effort */
  }
}

module.exports = {
  processNextTicket,
  processTicket,
  onApproval,
  onRejection,
  // exported for tests
  _internals: {
    resolveWorkdir,
    ticketStateDir,
    getLinearCfg,
    getSymphonyCfg,
  },
};
