const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execSync, spawn } = require("child_process");

const { discoverRuns, runTypeForDir } = require("./src/runs/discover");
const { loadRun } = require("./src/runs/model");

const CONFIG_PATH = path.join(__dirname, "config.json");
const DASHBOARD_PATH = path.join(__dirname, "dashboard.html");
const PID_PATH = path.join(__dirname, "server.pid");

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  } catch {
    return { port: 7890, directories: [], scanPaths: [] };
  }
}

function saveConfig(config) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
}

// Auto-discover run-bearing directories (.autoloop / .autopilot / .symphony) under scanPaths.
// Generalized via src/runs/discover.js. Replaces the legacy discoverAutoloops().
function discoverRunsConfig() {
  const config = loadConfig();
  const scanRoots = config.scanPaths || [];
  if (scanRoots.length === 0) return;

  // discoverRuns returns Array<{dir, runType, stateDir}>. We only care about `dir` for config.directories.
  const discovered = discoverRuns(scanRoots);
  const dismissed = new Set(config.dismissedDirectories || []);
  const existing = new Set(config.directories || []);
  let changed = false;

  for (const { dir } of discovered) {
    if (dismissed.has(dir)) continue;
    if (!existing.has(dir)) {
      existing.add(dir);
      changed = true;
      console.log(`Auto-discovered: ${dir}`);
    }
  }

  if (changed) {
    config.directories = Array.from(existing);
    saveConfig(config);
  }
}

function stripAnsi(str) {
  return str.replace(/\x1b\[[0-9;]*m/g, "");
}

function readFileSafe(filePath) {
  try {
    return fs.readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
}

function isPidAlive(pid) {
  try {
    process.kill(Number(pid), 0);
    return true;
  } catch {
    return false;
  }
}

function extractTitle(briefingContent) {
  if (!briefingContent) return null;
  // Match first heading: "# Autoloop Briefing — Title" or "# Autotest Briefing — Title"
  const match = briefingContent.match(
    /^#\s+(?:Auto(?:loop|test)\s+Briefing\s*[—–-]\s*)?(.+)/m,
  );
  return match ? match[1].trim() : null;
}

function detectLoopType(briefingContent, dir) {
  // Check briefing heading first
  if (briefingContent) {
    if (/^#\s+Autotest\b/im.test(briefingContent)) return "autotest";
    if (/^#\s+Autoloop\b/im.test(briefingContent)) return "autoloop";
    // Check for testing-specific keywords in briefing
    if (
      /\b(playwright|test cases|manual test|credentials|login)\b/i.test(
        briefingContent.slice(0, 500),
      )
    )
      return "autotest";
  }
  // Check folder name as fallback
  if (/autotest/i.test(path.basename(dir))) return "autotest";
  return "autoloop";
}

function getLoopState(dir) {
  const autoloopDir = path.join(dir, ".autoloop");
  const folderName = path.basename(dir);

  if (!fs.existsSync(autoloopDir)) {
    return { name: folderName, dir, runType: "autoloop", initialized: false };
  }

  // Phase
  const phase =
    (readFileSafe(path.join(autoloopDir, "phase.txt")) || "").trim() ||
    "unknown";

  // State JSON
  let state = null;
  try {
    state = JSON.parse(
      readFileSafe(path.join(autoloopDir, "state.json")) || "{}",
    );
  } catch {
    state = {};
  }

  // PID alive check
  const pidStr = (
    readFileSafe(path.join(autoloopDir, "harness.pid")) || ""
  ).trim();
  const alive = pidStr ? isPidAlive(pidStr) : false;

  // Status
  let status = "stopped";
  if (phase === "complete") status = "completed";
  else if (alive) status = "running";

  // Briefing
  const briefing = readFileSafe(path.join(autoloopDir, "briefing.md"));

  // Report
  const report = readFileSafe(path.join(autoloopDir, "report.md"));

  // Results
  const resultsTsv = readFileSafe(path.join(autoloopDir, "results.tsv"));
  let results = [];
  if (resultsTsv) {
    const lines = resultsTsv.trim().split("\n");
    if (lines.length > 1) {
      const headers = lines[0].split("\t");
      results = lines.slice(1).map((line) => {
        const vals = line.split("\t");
        const obj = {};
        headers.forEach((h, i) => (obj[h.trim()] = (vals[i] || "").trim()));
        return obj;
      });
    }
  }

  // Duration
  let duration = null;
  let startTime = state.start_time || null;
  if (startTime) {
    const startMs = new Date(startTime).getTime();
    if (!isNaN(startMs)) {
      duration = Math.round((Date.now() - startMs) / 60000);
    }
  }

  const title = extractTitle(briefing);
  const loopType = detectLoopType(briefing, dir);

  return {
    name: folderName,
    title,
    runType: "autoloop",
    loopType,
    dir,
    initialized: true,
    phase,
    status,
    pid: pidStr || null,
    alive,
    startTime,
    duration,
    retryCount: state.retry_count || 0,
    experiments: results.length,
    results,
    briefing,
    report,
  };
}

// Minimal Run shape for non-autoloop dirs. The full Run model lives in src/runs/model.js
// but for Stage 0+1 the API only needs the legacy-compatible LoopState shape with runType set.
function getMinimalRunState(dir, runType) {
  const name = path.basename(dir);
  let branch = null;
  try {
    branch = execSync(`git -C "${dir}" rev-parse --abbrev-ref HEAD`, {
      timeout: 3000,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch (_) {
    /* not a git repo */
  }
  return {
    name,
    title: null,
    runType,
    loopType: null, // legacy compat field — UI may read it
    dir,
    initialized: true,
    phase: null,
    status: "idle",
    pid: null,
    alive: false,
    startTime: null,
    duration: null,
    retryCount: 0,
    experiments: 0,
    results: [],
    briefing: null,
    report: null,
    branch,
  };
}

function getLoopLog(dir, lines = 200) {
  const logPath = path.join(dir, ".autoloop", "harness.log");
  const content = readFileSafe(logPath);
  if (!content) return [];
  const allLines = stripAnsi(content).split("\n");
  return allLines.slice(-lines);
}

function getLoopGit(dir) {
  try {
    const output = execSync("git log --oneline -20", {
      cwd: dir,
      timeout: 5000,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    });
    return output.trim().split("\n").filter(Boolean);
  } catch {
    return [];
  }
}

function getLoopBranch(dir) {
  try {
    return execSync("git branch --show-current", {
      cwd: dir,
      timeout: 3000,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    }).trim();
  } catch {
    return null;
  }
}

async function handleApi(req, res) {
  const config = loadConfig();
  const url = new URL(req.url, `http://localhost:${config.port}`);
  const pathname = url.pathname;

  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "*");

  // GET /api/loops
  if (pathname === "/api/loops") {
    const dirs = config.directories || [];
    const loops = dirs.map((dir, idx) => {
      const runType = runTypeForDir(dir);
      let entry;
      if (runType === "autoloop") {
        entry = getLoopState(dir);
        entry.branch = getLoopBranch(dir);
        entry.runType = "autoloop";
      } else if (runType === "autopilot" || runType === "symphony") {
        entry = getMinimalRunState(dir, runType);
      } else {
        // Unknown / no marker — still surface so user can dismiss
        entry = getMinimalRunState(dir, "unknown");
      }
      entry.idx = idx;
      return entry;
    });
    res.end(JSON.stringify(loops));
    return;
  }

  // GET /api/loop/:index/log
  const logMatch = pathname.match(/^\/api\/loop\/(\d+)\/log$/);
  if (logMatch) {
    const idx = Number(logMatch[1]);
    const dir = config.directories[idx];
    if (!dir) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }
    const lines = Number(url.searchParams.get("lines") || 200);
    res.end(JSON.stringify(getLoopLog(dir, lines)));
    return;
  }

  // GET /api/loop/:index/git
  const gitMatch = pathname.match(/^\/api\/loop\/(\d+)\/git$/);
  if (gitMatch) {
    const idx = Number(gitMatch[1]);
    const dir = config.directories[idx];
    if (!dir) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }
    res.end(JSON.stringify(getLoopGit(dir)));
    return;
  }

  // POST /api/loop/:index/stop
  const stopMatch = pathname.match(/^\/api\/loop\/(\d+)\/stop$/);
  if (stopMatch && req.method === "POST") {
    const idx = Number(stopMatch[1]);
    const dir = config.directories[idx];
    if (!dir) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }
    if (runTypeForDir(dir) !== "autoloop") {
      res.statusCode = 400;
      res.end(
        JSON.stringify({
          ok: false,
          error: "Endpoint only supports autoloop runs",
        }),
      );
      return;
    }
    const autoloopDir = path.join(dir, ".autoloop");
    const pidStr = (
      readFileSafe(path.join(autoloopDir, "harness.pid")) || ""
    ).trim();
    if (!pidStr || !isPidAlive(pidStr)) {
      res.end(JSON.stringify({ ok: false, error: "Not running" }));
      return;
    }
    try {
      process.kill(Number(pidStr), "SIGTERM");
      res.end(JSON.stringify({ ok: true, killed: pidStr }));
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  // POST /api/loop/:index/reset (start from scratch — keeps briefing, wipes everything else)
  const resetMatch = pathname.match(/^\/api\/loop\/(\d+)\/reset$/);
  if (resetMatch && req.method === "POST") {
    const idx = Number(resetMatch[1]);
    const dir = config.directories[idx];
    if (!dir) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }
    if (runTypeForDir(dir) !== "autoloop") {
      res.statusCode = 400;
      res.end(
        JSON.stringify({
          ok: false,
          error: "Endpoint only supports autoloop runs",
        }),
      );
      return;
    }
    const autoloopDir = path.join(dir, ".autoloop");
    if (!fs.existsSync(autoloopDir)) {
      res.end(JSON.stringify({ ok: false, error: "No .autoloop directory" }));
      return;
    }
    // Stop running harness first
    const pidStr = (
      readFileSafe(path.join(autoloopDir, "harness.pid")) || ""
    ).trim();
    if (pidStr && isPidAlive(pidStr)) {
      try {
        process.kill(Number(pidStr), "SIGTERM");
      } catch {}
      // Wait for process to actually die
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 100));
        if (!isPidAlive(pidStr)) break;
      }
    }
    // Wipe all state EXCEPT briefing.md
    const keepFiles = new Set(["briefing.md", ".gitignore"]);
    try {
      const files = fs.readdirSync(autoloopDir);
      for (const f of files) {
        if (!keepFiles.has(f)) {
          const fp = path.join(autoloopDir, f);
          try {
            fs.rmSync(fp, { recursive: true, force: true });
          } catch {}
        }
      }
      // Reset phase to briefing so agent starts from recon
      fs.writeFileSync(path.join(autoloopDir, "phase.txt"), "briefing");
      // Launch harness fresh
      const harnessPath = path.join(
        process.env.HOME,
        ".claude/commands/autoloop-harness.sh",
      );
      if (fs.existsSync(harnessPath)) {
        const child = spawn("bash", [harnessPath, dir, "--skip-briefing"], {
          cwd: dir,
          detached: true,
          stdio: ["ignore", "ignore", "ignore"],
        });
        child.unref();
        res.end(JSON.stringify({ ok: true, pid: child.pid }));
      } else {
        res.end(
          JSON.stringify({
            ok: true,
            message: "State cleared but harness not found to relaunch",
          }),
        );
      }
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  // POST /api/loop/:index/restart
  const restartMatch = pathname.match(/^\/api\/loop\/(\d+)\/restart$/);
  if (restartMatch && req.method === "POST") {
    const idx = Number(restartMatch[1]);
    const dir = config.directories[idx];
    if (!dir) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }
    if (runTypeForDir(dir) !== "autoloop") {
      res.statusCode = 400;
      res.end(
        JSON.stringify({
          ok: false,
          error: "Endpoint only supports autoloop runs",
        }),
      );
      return;
    }
    const autoloopDir = path.join(dir, ".autoloop");
    if (!fs.existsSync(autoloopDir)) {
      res.end(JSON.stringify({ ok: false, error: "No .autoloop directory" }));
      return;
    }
    // Check if briefing exists (required for --skip-briefing)
    if (!fs.existsSync(path.join(autoloopDir, "briefing.md"))) {
      res.end(
        JSON.stringify({
          ok: false,
          error: "No briefing.md found. Run the harness interactively first.",
        }),
      );
      return;
    }
    // Check if already running
    const pidStr = (
      readFileSafe(path.join(autoloopDir, "harness.pid")) || ""
    ).trim();
    if (pidStr && isPidAlive(pidStr)) {
      res.end(
        JSON.stringify({
          ok: false,
          error: "Already running (PID " + pidStr + ")",
        }),
      );
      return;
    }
    // Launch harness in background
    const harnessPath = path.join(
      process.env.HOME,
      ".claude/commands/autoloop-harness.sh",
    );
    if (!fs.existsSync(harnessPath)) {
      res.end(JSON.stringify({ ok: false, error: "Harness script not found" }));
      return;
    }
    try {
      // Reset state.json so harness starts fresh (new timer, retry_count=0)
      const stateFile = path.join(autoloopDir, "state.json");
      if (fs.existsSync(stateFile)) {
        try {
          const oldState = JSON.parse(fs.readFileSync(stateFile, "utf8"));
          oldState.status = "running";
          oldState.retry_count = 0;
          oldState.start_time = new Date().toISOString();
          fs.writeFileSync(stateFile, JSON.stringify(oldState, null, 4));
        } catch {}
      }
      const child = spawn("bash", [harnessPath, dir, "--skip-briefing"], {
        cwd: dir,
        detached: true,
        stdio: ["ignore", "ignore", "ignore"],
      });
      child.unref();
      res.end(JSON.stringify({ ok: true, pid: child.pid }));
    } catch (e) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  // GET /api/loop/:index/agent-log
  const agentLogMatch = pathname.match(/^\/api\/loop\/(\d+)\/agent-log$/);
  if (agentLogMatch) {
    const idx = Number(agentLogMatch[1]);
    const dir = config.directories[idx];
    if (!dir) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }
    const maxEvents = Number(url.searchParams.get("lines") || 200);
    const agentLogPath = path.join(dir, ".autoloop", "agent.log");
    const content = readFileSafe(agentLogPath);
    if (!content) {
      res.end(JSON.stringify({ format: "empty", events: [] }));
      return;
    }
    const rawLines = stripAnsi(content).split("\n").filter(Boolean);
    // Try to detect stream-json format (lines are JSON objects)
    const firstLine = rawLines[0] || "";
    const isStreamJson = firstLine.startsWith("{");
    if (isStreamJson) {
      const events = [];
      for (const line of rawLines.slice(-maxEvents)) {
        try {
          events.push(JSON.parse(line));
        } catch {
          // Non-JSON line (e.g., stderr), keep as raw text
          events.push({ type: "raw", text: line });
        }
      }
      res.end(JSON.stringify({ format: "stream-json", events }));
    } else {
      // Legacy plain text format
      res.end(
        JSON.stringify({ format: "text", events: rawLines.slice(-maxEvents) }),
      );
    }
    return;
  }

  // POST /api/config/add
  if (pathname === "/api/config/add" && req.method === "POST") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        const { directory } = JSON.parse(body);
        const resolved = path.resolve(directory);
        const freshConfig = loadConfig();
        // Clear from dismissed list if re-adding
        if (freshConfig.dismissedDirectories) {
          freshConfig.dismissedDirectories =
            freshConfig.dismissedDirectories.filter((d) => d !== resolved);
        }
        if (!freshConfig.directories.includes(resolved)) {
          freshConfig.directories.push(resolved);
        }
        saveConfig(freshConfig);
        res.end(
          JSON.stringify({ ok: true, directories: freshConfig.directories }),
        );
      } catch {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: "Invalid JSON" }));
      }
    });
    return;
  }

  // POST /api/config/remove
  if (pathname === "/api/config/remove" && req.method === "POST") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        const { directory } = JSON.parse(body);
        const resolved = path.resolve(directory);
        const freshConfig = loadConfig();
        freshConfig.directories = freshConfig.directories.filter(
          (d) => d !== resolved,
        );
        // Add to dismissed list so auto-discovery doesn't re-add it
        if (!freshConfig.dismissedDirectories)
          freshConfig.dismissedDirectories = [];
        if (!freshConfig.dismissedDirectories.includes(resolved)) {
          freshConfig.dismissedDirectories.push(resolved);
        }
        saveConfig(freshConfig);
        res.end(
          JSON.stringify({ ok: true, directories: freshConfig.directories }),
        );
      } catch {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: "Invalid JSON" }));
      }
    });
    return;
  }

  // POST /api/symphony/poll — manually trigger orchestrator.processNextTicket()
  if (pathname === "/api/symphony/poll" && req.method === "POST") {
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    (async () => {
      try {
        const orchestrator = require("./src/symphony/orchestrator");
        const result = await orchestrator.processNextTicket();
        res.statusCode = 200;
        res.end(JSON.stringify({ ok: true, result }));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    })();
    return;
  }

  // POST /api/symphony/kill — touch STOP flag + SIGTERM all registered PIDs
  if (pathname === "/api/symphony/kill" && req.method === "POST") {
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    (async () => {
      try {
        const symDir = path.join(os.homedir(), ".symphony");
        fs.mkdirSync(symDir, { recursive: true });
        fs.writeFileSync(path.join(symDir, "STOP"), String(Date.now()));
        const budget = require("./src/symphony/budget");
        const killResult = await budget.killAll();
        res.statusCode = 200;
        res.end(JSON.stringify({ ok: true, stopFlag: true, ...killResult }));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    })();
    return;
  }

  // GET /api/symphony/runs — Run[] filtered to runType==='symphony'
  if (pathname === "/api/symphony/runs" && req.method === "GET") {
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    (async () => {
      try {
        const render = require("./src/symphony/render");
        const runs = await render.symphonyRuns(loadConfig());
        res.statusCode = 200;
        res.end(JSON.stringify(runs));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    })();
    return;
  }

  // GET /api/symphony/ticket/:id — aggregated ticket info
  const ticketMatch = pathname.match(/^\/api\/symphony\/ticket\/([^\/]+)$/);
  if (ticketMatch && req.method === "GET") {
    const id = decodeURIComponent(ticketMatch[1]);
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    (async () => {
      try {
        const render = require("./src/symphony/render");
        const agg = await render.ticketAggregate(loadConfig(), id);
        res.statusCode = 200;
        res.end(JSON.stringify(agg));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    })();
    return;
  }

  // GET /api/symphony/budget — budget snapshot
  if (pathname === "/api/symphony/budget" && req.method === "GET") {
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    (async () => {
      try {
        const render = require("./src/symphony/render");
        const snap = render.budgetSnapshot(loadConfig());
        res.statusCode = 200;
        res.end(JSON.stringify(snap));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    })();
    return;
  }

  // POST /api/symphony/approve/:id — fire-and-forget orchestrator.onApproval
  const approveMatch = pathname.match(/^\/api\/symphony\/approve\/([^\/]+)$/);
  if (approveMatch && req.method === "POST") {
    const id = decodeURIComponent(approveMatch[1]);
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    // Fire-and-forget, but report acceptance
    res.statusCode = 202;
    res.end(JSON.stringify({ ok: true, accepted: true, ticketId: id }));
    // Run in background; errors logged but not surfaced to client (the Linear ticket gets the error comment)
    (async () => {
      try {
        const orchestrator = require("./src/symphony/orchestrator");
        await orchestrator.onApproval(id);
      } catch (e) {
        console.error("[symphony approve]", id, e.message);
      }
    })();
    return;
  }

  // POST /api/symphony/reject/:id — body: {reason}
  const rejectMatch = pathname.match(/^\/api\/symphony\/reject\/([^\/]+)$/);
  if (rejectMatch && req.method === "POST") {
    const id = decodeURIComponent(rejectMatch[1]);
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", async () => {
      try {
        const { reason } = body ? JSON.parse(body) : {};
        const orchestrator = require("./src/symphony/orchestrator");
        await orchestrator.onRejection(id, reason);
        res.statusCode = 200;
        res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // POST /api/symphony/edit-and-approve/:id — body: {plan}; writes approved-plan.md and triggers onApproval
  const editMatch = pathname.match(
    /^\/api\/symphony\/edit-and-approve\/([^\/]+)$/,
  );
  if (editMatch && req.method === "POST") {
    const id = decodeURIComponent(editMatch[1]);
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      (async () => {
        try {
          const { plan } = JSON.parse(body || "{}");
          if (!plan || typeof plan !== "string") {
            res.statusCode = 400;
            return res.end(JSON.stringify({ error: "missing plan field" }));
          }
          // Find stateDir via render
          const render = require("./src/symphony/render");
          const agg = await render.ticketAggregate(loadConfig(), id);
          if (!agg.stateDir) {
            res.statusCode = 404;
            return res.end(
              JSON.stringify({ error: "ticket stateDir not found" }),
            );
          }
          fs.writeFileSync(path.join(agg.stateDir, "approved-plan.md"), plan);
          res.statusCode = 202;
          res.end(JSON.stringify({ ok: true, accepted: true, ticketId: id }));
          // Background execute
          const orchestrator = require("./src/symphony/orchestrator");
          orchestrator
            .onApproval(id)
            .catch((e) =>
              console.error("[symphony edit-and-approve]", id, e.message),
            );
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: e.message }));
        }
      })();
    });
    return;
  }

  res.statusCode = 404;
  res.end(JSON.stringify({ error: "Not found" }));
}

const server = http.createServer(async (req, res) => {
  const config = loadConfig();
  const url = new URL(req.url, `http://localhost:${config.port}`);

  // API routes
  if (url.pathname.startsWith("/api/")) {
    await handleApi(req, res);
    return;
  }

  // Serve dashboard
  if (url.pathname === "/" || url.pathname === "/index.html") {
    try {
      const html = fs.readFileSync(DASHBOARD_PATH, "utf8");
      res.setHeader("Content-Type", "text/html");
      res.end(html);
    } catch {
      res.statusCode = 500;
      res.end("Dashboard file not found");
    }
    return;
  }

  res.statusCode = 404;
  res.end("Not found");
});

// Auto-discover on startup and every 30 seconds
discoverRunsConfig();
setInterval(discoverRunsConfig, 30000);

const config = loadConfig();
const PORT = config.port || 7890;

server.listen(PORT, () => {
  fs.writeFileSync(PID_PATH, String(process.pid));
  console.log(`Autoloop Dashboard running at http://localhost:${PORT}`);
});

process.on("SIGTERM", () => {
  try {
    fs.unlinkSync(PID_PATH);
  } catch {}
  process.exit(0);
});
process.on("SIGINT", () => {
  try {
    fs.unlinkSync(PID_PATH);
  } catch {}
  process.exit(0);
});
