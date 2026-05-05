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
   * Stage 0+1 placeholder: spawns a no-op shell command that sleeps briefly,
   * writes an exit code file, and returns. Sufficient for adapter-shape verification.
   * Stage 2 will replace the spawned command with the real `claude -p` invocation.
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
    const exitFile = path.join(adapterDir, "exit-code");
    const pidFile = path.join(adapterDir, "agent.pid");

    // Placeholder no-op command. Stage 2 will replace with real claude -p invocation.
    const cmd = `echo "claude-code adapter spawn placeholder (stateDir=${intent.stateDir})" > "${agentLog}" 2>&1; sleep 1; echo 0 > "${exitFile}"`;
    const child = cpSpawn("bash", ["-c", cmd], {
      detached: true,
      stdio: "ignore",
      cwd: intent.workdir,
    });
    child.unref();

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
      /* no exit file */
    }

    const reason =
      exitCode === 0 ? "clean" : exitCode === -1 ? "crash" : "crash";

    return {
      exitCode,
      reason,
      filesChanged: [], // Stage 2: orchestrator computes via git diff
      markers: [], // Stage 2: parse agent.log for H2 markers
    };
  },

  /**
   * Tier 1 contract requires this to exist; Stage 0+1 wiring is deferred.
   */
  async dispatchSubagent(name, prompt, opts) {
    throw new Error("NotImplemented: claude-code dispatchSubagent (Stage 2)");
  },
};

module.exports = adapter;
