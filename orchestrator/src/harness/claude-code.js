const fs = require("fs");
const path = require("path");
const { spawn: cpSpawn } = require("child_process");

/**
 * @typedef {import('./types').HarnessAdapter} HarnessAdapter
 * @typedef {import('./types').RunIntent} RunIntent
 * @typedef {import('./types').RunHandle} RunHandle
 * @typedef {import('./types').RunResult} RunResult
 */

/** @type {HarnessAdapter} */
const adapter = {
  id: "claude-code",
  tier: 1,
  capabilities: {
    subagents: true,
    streamJsonEvents: true,
    appendSystemPrompt: true,
    budgetCap: true,
  },

  /**
   * Spawns a real `claude -p` invocation in detached, unattended mode and
   * heartbeat-registers the PID for budget.killAll().
   * @param {RunIntent} intent
   * @returns {Promise<RunHandle>}
   */
  async spawn(intent) {
    if (
      !intent ||
      typeof intent.stateDir !== "string" ||
      typeof intent.workdir !== "string"
    ) {
      throw new Error(
        "claude-code adapter: intent must include workdir and stateDir",
      );
    }
    const adapterDir = path.join(intent.stateDir, "claude-code");
    fs.mkdirSync(adapterDir, { recursive: true });

    const agentLog = path.join(adapterDir, "agent.log");
    const pidFile = path.join(adapterDir, "agent.pid");

    // Real claude -p invocation
    const args = [
      "--print",
      "--output-format",
      "stream-json",
      "--dangerously-skip-permissions",
    ];
    if (intent.systemPromptFile) {
      args.push("--append-system-prompt-file", intent.systemPromptFile);
    }
    // The prompt itself is the LAST positional argument
    args.push(intent.prompt);

    const logFd = fs.openSync(agentLog, "a");
    const child = cpSpawn("claude", args, {
      detached: true,
      stdio: ["ignore", logFd, logFd],
      cwd: intent.workdir,
      env: {
        ...process.env,
        CLAUDE_CODE_UNATTENDED_RETRY: "1",
      },
    });
    fs.closeSync(logFd);
    child.unref();

    // Heartbeat-register PID for budget.killAll() — best-effort, no hard dep on budget.js
    try {
      const os = require("os");
      fs.mkdirSync(path.join(os.homedir(), ".symphony"), { recursive: true });
      fs.appendFileSync(
        path.join(os.homedir(), ".symphony", "registered-pids.log"),
        String(child.pid) + "\n",
      );
    } catch (_) {
      /* best-effort */
    }

    fs.writeFileSync(pidFile, String(child.pid));

    return {
      pid: child.pid,
      pgid: -child.pid, // process group id for kill -pgid
      agentLog,
      start: new Date(),
      async cancel() {
        try {
          process.kill(-child.pid, "SIGTERM");
        } catch (_) {
          /* already gone */
        }
        // Give 5s, then SIGKILL
        await new Promise((r) => setTimeout(r, 5000));
        try {
          process.kill(-child.pid, "SIGKILL");
        } catch (_) {
          /* already gone */
        }
      },
    };
  },

  /**
   * @param {RunHandle} handle
   * @returns {Promise<'running' | 'exited' | 'crashed'>}
   */
  async status(handle) {
    try {
      process.kill(handle.pid, 0); // signal 0 = existence check, doesn't actually signal
      return "running";
    } catch (e) {
      // ESRCH = no such process; ESRCH means it exited cleanly or crashed.
      // We can't distinguish without the exit-code file.
      return "exited";
    }
  },

  /**
   * @param {RunHandle} handle
   * @returns {Promise<RunResult>}
   */
  async collect(handle) {
    const adapterDir = path.dirname(handle.agentLog);
    const exitFile = path.join(adapterDir, "exit-code");
    let exitCode = -1;
    try {
      exitCode = parseInt(fs.readFileSync(exitFile, "utf8").trim(), 10);
      if (Number.isNaN(exitCode)) exitCode = -1;
    } catch (_) {
      /* no exit file written by stream-json mode — derive from process state instead */
    }

    // Parse H2 markers from log. stream-json output has lines like {"type":"text","content":"..."}.
    // We grep for ## MARKER_NAME in raw text content.
    const markers = [];
    try {
      const log = fs.readFileSync(handle.agentLog, "utf8");
      const re = /^## ([A-Z][A-Z _]+)$/gm;
      let m;
      while ((m = re.exec(log))) {
        markers.push(m[1].trim());
      }
    } catch (_) {
      /* no log */
    }

    const reason =
      exitCode === 0 ? "clean" : exitCode === -1 ? "crash" : "crash";

    return {
      exitCode,
      reason,
      filesChanged: [], // orchestrator computes via git diff
      markers,
    };
  },

  /**
   * Tier 1 contract requires this to exist; Stage 2 spawns separate
   * `claude -p` invocations directly (see verifier.js for the canonical example).
   */
  async dispatchSubagent(name, prompt, opts) {
    throw new Error(
      `NotImplemented: claude-code dispatchSubagent (Stage 2 spawns separate claude -p invocations directly; ` +
        `verifier.js is the canonical example). Caller wanted: ${name}`,
    );
  },
};

module.exports = adapter;
