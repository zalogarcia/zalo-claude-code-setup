"use strict";

/**
 * Symphony verifier — sequential gates run after a Stage-2 implementation
 * spawn returns. Each layer reports `{ran, passed?, details?}` and the final
 * `passed` flag is the AND of all layers (a `{ran: false}` layer counts as
 * pass-through).
 *
 * Layers (in order):
 *   1. tsc      — npx --no-install tsc --noEmit
 *   2. tests    — npm test  (when package.json scripts.test exists)
 *   3. lint     — npx --no-install eslint . (when eslint config detected)
 *   4. qa       — claude -p qa-agent dispatch (skipped if any of {tsc,tests,lint} failed)
 *   5. backend  — supabase db lint  (only when migrations changed and config.toml exists)
 *   6. visual   — pixelmatch baseline diff (only when frontend files changed and baselines exist)
 *
 * The verifier is orchestrator-level — it spawns its own `claude -p` for the
 * qa layer rather than going through the harness adapter (see plan.md Alt 4).
 *
 * Exports:
 *   run({stateDir, workdir, filesChanged}) => Promise<{passed, layers}>
 *
 * Side-effect: writes `<stateDir>/verification.json` (atomic).
 *
 * Test hook: SYMPHONY_VERIFIER_SKIP_QA=1 in env skips the qa layer entirely
 * (qa layer reports `{ran: false, reason: 'skipped via SYMPHONY_VERIFIER_SKIP_QA'}`).
 */

const fs = require("fs");
const path = require("path");
const { spawnSync, spawn } = require("child_process");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function safeExists(p) {
  try {
    return fs.existsSync(p);
  } catch (_) {
    return false;
  }
}

function safeReadJson(p) {
  try {
    const raw = fs.readFileSync(p, "utf8");
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}

function listEslintConfigs(workdir) {
  // .eslintrc, .eslintrc.json, .eslintrc.js, .eslintrc.cjs, .eslintrc.yml, .eslintrc.yaml,
  // eslint.config.js, eslint.config.mjs, eslint.config.cjs
  const candidates = [
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.yml",
    ".eslintrc.yaml",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
  ];
  for (const c of candidates) {
    if (safeExists(path.join(workdir, c))) return true;
  }
  return false;
}

function runCmd(cmd, args, opts) {
  // Wraps spawnSync to never throw and always return a normalized object.
  let result;
  try {
    result = spawnSync(cmd, args, {
      cwd: opts && opts.cwd,
      encoding: "utf8",
      env: opts && opts.env ? opts.env : process.env,
      timeout: opts && opts.timeout,
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch (err) {
    return { exitCode: -1, stdout: "", stderr: String(err && err.message) };
  }
  if (result.error) {
    return {
      exitCode: -1,
      stdout: result.stdout || "",
      stderr:
        (result.stderr || "") +
        "\nspawn error: " +
        String(result.error.message),
    };
  }
  const exitCode =
    typeof result.status === "number"
      ? result.status
      : result.signal
        ? 128
        : -1;
  return {
    exitCode,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
  };
}

function trimDetails(stdout, stderr, max) {
  const limit = typeof max === "number" ? max : 4000;
  const combined = ((stderr || "") + "\n" + (stdout || "")).trim();
  if (combined.length <= limit) return combined;
  return combined.slice(0, limit) + "\n[... truncated]";
}

function hasFrontendFile(filesChanged) {
  if (!Array.isArray(filesChanged)) return false;
  const re = /\.(tsx|jsx|html|css)$/i;
  return filesChanged.some((f) => typeof f === "string" && re.test(f));
}

function hasMigration(filesChanged) {
  if (!Array.isArray(filesChanged)) return false;
  return filesChanged.some(
    (f) =>
      typeof f === "string" &&
      /(^|\/)supabase\/migrations\/[^/]+\.sql$/i.test(f),
  );
}

function listBaselines(workdir) {
  const dir = path.join(workdir, ".symphony", "baselines");
  if (!safeExists(dir)) return [];
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.toLowerCase().endsWith(".png"))
      .map((f) => f);
  } catch (_) {
    return [];
  }
}

function atomicWriteJson(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = file + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2));
  fs.renameSync(tmp, file);
}

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------

function layerTsc(workdir) {
  const tsconfig = path.join(workdir, "tsconfig.json");
  if (!safeExists(tsconfig)) return { ran: false };
  const r = runCmd("npx", ["--no-install", "tsc", "--noEmit"], {
    cwd: workdir,
    timeout: 120000,
  });
  if (r.exitCode === 0) return { ran: true, passed: true };
  return {
    ran: true,
    passed: false,
    details: trimDetails(r.stdout, r.stderr),
  };
}

function layerTests(workdir) {
  const pkgPath = path.join(workdir, "package.json");
  if (!safeExists(pkgPath)) return { ran: false };
  const pkg = safeReadJson(pkgPath);
  if (!pkg || !pkg.scripts || typeof pkg.scripts.test !== "string") {
    return { ran: false };
  }
  // Skip the placeholder test script that npm init writes by default.
  const trimmed = pkg.scripts.test.trim();
  if (trimmed === "" || /^echo .*Error: no test specified/i.test(trimmed)) {
    return { ran: false };
  }
  const r = runCmd("npm", ["test", "--prefix", workdir], {
    cwd: workdir,
    timeout: 600000,
  });
  if (r.exitCode === 0) return { ran: true, passed: true };
  return {
    ran: true,
    passed: false,
    details: trimDetails(r.stdout, r.stderr),
  };
}

function layerLint(workdir) {
  const pkg = safeReadJson(path.join(workdir, "package.json"));
  const hasPkgConfig = !!(pkg && pkg.eslintConfig);
  const hasFile = listEslintConfigs(workdir);
  if (!hasFile && !hasPkgConfig) return { ran: false };
  const r = runCmd("npx", ["--no-install", "eslint", "."], {
    cwd: workdir,
    timeout: 180000,
  });
  if (r.exitCode === 0) return { ran: true, passed: true };
  return {
    ran: true,
    passed: false,
    details: trimDetails(r.stdout, r.stderr),
  };
}

function layerQa({ stateDir, workdir, filesChanged, coreLayersPassed }) {
  if (process.env.SYMPHONY_VERIFIER_SKIP_QA === "1") {
    return {
      ran: false,
      reason: "skipped via SYMPHONY_VERIFIER_SKIP_QA",
    };
  }
  if (!coreLayersPassed) {
    return { ran: false, reason: "previous layers failed" };
  }

  // Adapter capability gate. Require at runtime so a broken adapter
  // doesn't prevent the verifier module from loading at all.
  let caps = null;
  try {
    const { pickAdapter } = require("../harness");
    const adapter = pickAdapter("claude-code");
    caps = adapter && adapter.capabilities;
  } catch (err) {
    return {
      ran: false,
      reason: "adapter unavailable: " + String(err && err.message),
    };
  }
  if (!caps || caps.subagents !== true) {
    return { ran: false, reason: "adapter does not support subagents" };
  }

  const logFile = path.join(stateDir, "qa-agent.log");
  try {
    fs.mkdirSync(stateDir, { recursive: true });
  } catch (_) {
    /* dir creation best-effort */
  }

  const args = [
    "--print",
    "--output-format",
    "stream-json",
    "--dangerously-skip-permissions",
    "--max-turns",
    "15",
  ];
  const filesList = Array.isArray(filesChanged) ? filesChanged.join(", ") : "";
  const prompt =
    "Audit these files for real bugs (skip style): " +
    filesList +
    ". Use severity rubric (CRITICAL/HIGH/MEDIUM/LOW). Emit ## VERIFICATION PASSED or ## ISSUES FOUND.";
  args.push(prompt);

  let logFd;
  try {
    logFd = fs.openSync(logFile, "a");
  } catch (err) {
    return {
      ran: true,
      passed: false,
      details: "could not open qa-agent.log: " + String(err && err.message),
    };
  }

  let exitCode;
  try {
    const child = spawn("claude", args, {
      cwd: workdir,
      stdio: ["ignore", logFd, logFd],
    });
    // Synchronously wait for exit by using a busy-wait via spawnSync semantics.
    // We need an async-style wait — but since `run` is async, we model this with
    // a Promise and resolve based on child events.
    return new Promise((resolve) => {
      let settled = false;
      child.on("error", (err) => {
        if (settled) return;
        settled = true;
        try {
          fs.closeSync(logFd);
        } catch (_) {}
        resolve({
          ran: true,
          passed: false,
          details: "qa-agent spawn error: " + String(err && err.message),
        });
      });
      child.on("exit", (code) => {
        if (settled) return;
        settled = true;
        exitCode = typeof code === "number" ? code : -1;
        try {
          fs.closeSync(logFd);
        } catch (_) {}
        resolve(parseQaLog(logFile, exitCode));
      });
    });
  } catch (err) {
    try {
      fs.closeSync(logFd);
    } catch (_) {}
    return {
      ran: true,
      passed: false,
      details: "qa-agent could not be spawned: " + String(err && err.message),
    };
  }
}

function parseQaLog(logFile, exitCode) {
  let log = "";
  try {
    log = fs.readFileSync(logFile, "utf8");
  } catch (_) {
    log = "";
  }
  // The stream-json log embeds plain text content; we look for H2 markers
  // anywhere in the captured bytes (multi-line).
  const passedRe = /^## VERIFICATION PASSED\s*$/m;
  const issuesRe = /^## ISSUES FOUND\s*$/m;
  if (passedRe.test(log)) {
    return { ran: true, passed: true };
  }
  if (issuesRe.test(log)) {
    const idx = log.search(issuesRe);
    const after = idx >= 0 ? log.slice(idx) : "";
    return {
      ran: true,
      passed: false,
      details: trimDetails(after, "", 4000),
    };
  }
  return {
    ran: true,
    passed: false,
    details: "no marker emitted (exitCode=" + String(exitCode) + ")",
  };
}

function layerBackend(workdir, filesChanged) {
  if (!hasMigration(filesChanged)) return { ran: false };
  const cfg = path.join(workdir, "supabase", "config.toml");
  if (!safeExists(cfg)) return { ran: false };
  const r = runCmd("supabase", ["db", "lint"], {
    cwd: workdir,
    timeout: 120000,
  });
  if (r.exitCode === 0) return { ran: true, passed: true };
  return {
    ran: true,
    passed: false,
    details: trimDetails(r.stdout, r.stderr),
  };
}

function layerVisual(stateDir, workdir, filesChanged) {
  if (!hasFrontendFile(filesChanged)) return { ran: false };
  const baselines = listBaselines(workdir);
  if (baselines.length === 0) {
    return { ran: false, reason: "no baseline or screenshot pairs" };
  }

  let pixelmatch, PNG;
  try {
    pixelmatch = require("pixelmatch");
  } catch (_) {
    return { ran: false, reason: "pixelmatch or pngjs not installed" };
  }
  try {
    PNG = require("pngjs").PNG;
  } catch (_) {
    return { ran: false, reason: "pixelmatch or pngjs not installed" };
  }

  // Some bundlers expose pixelmatch as { default: fn }. Normalize.
  if (
    pixelmatch &&
    typeof pixelmatch !== "function" &&
    typeof pixelmatch.default === "function"
  ) {
    pixelmatch = pixelmatch.default;
  }

  const screenshotsDir = path.join(stateDir, "screenshots");
  let comparedPairs = 0;
  let worstRatio = 0;
  let worstName = null;

  for (const baseName of baselines) {
    const basePath = path.join(workdir, ".symphony", "baselines", baseName);
    const shotPath = path.join(screenshotsDir, baseName);
    if (!safeExists(shotPath)) continue;

    let basePng, shotPng;
    try {
      basePng = PNG.sync.read(fs.readFileSync(basePath));
      shotPng = PNG.sync.read(fs.readFileSync(shotPath));
    } catch (err) {
      return {
        ran: true,
        passed: false,
        details:
          "failed to parse PNGs for " +
          baseName +
          ": " +
          String(err && err.message),
      };
    }

    if (basePng.width !== shotPng.width || basePng.height !== shotPng.height) {
      // Dimension mismatch is a hard fail for that pair.
      return {
        ran: true,
        passed: false,
        details:
          "dimension mismatch for " +
          baseName +
          " (baseline " +
          basePng.width +
          "x" +
          basePng.height +
          " vs shot " +
          shotPng.width +
          "x" +
          shotPng.height +
          ")",
      };
    }

    const total = basePng.width * basePng.height;
    let diffPixels = 0;
    try {
      diffPixels = pixelmatch(
        basePng.data,
        shotPng.data,
        null,
        basePng.width,
        basePng.height,
        { threshold: 0.1 },
      );
    } catch (err) {
      return {
        ran: true,
        passed: false,
        details:
          "pixelmatch error for " +
          baseName +
          ": " +
          String(err && err.message),
      };
    }

    comparedPairs += 1;
    const ratio = total > 0 ? diffPixels / total : 0;
    if (ratio > worstRatio) {
      worstRatio = ratio;
      worstName = baseName;
    }
  }

  if (comparedPairs === 0) {
    return { ran: false, reason: "no baseline or screenshot pairs" };
  }

  if (worstRatio < 0.005) {
    return {
      ran: true,
      passed: true,
      details:
        "compared " +
        comparedPairs +
        " pair(s); worst diff " +
        (worstRatio * 100).toFixed(4) +
        "%",
    };
  }
  return {
    ran: true,
    passed: false,
    details:
      "diff exceeded 0.5% threshold on " +
      String(worstName) +
      " (" +
      (worstRatio * 100).toFixed(4) +
      "%)",
  };
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function run({ stateDir, workdir, filesChanged }) {
  if (typeof stateDir !== "string" || stateDir === "") {
    throw new TypeError("verifier.run: stateDir must be a non-empty string");
  }
  if (typeof workdir !== "string" || workdir === "") {
    throw new TypeError("verifier.run: workdir must be a non-empty string");
  }
  const files = Array.isArray(filesChanged) ? filesChanged.slice() : [];

  // Layer 1-3: independent core layers.
  let tsc, tests, lint;
  try {
    tsc = layerTsc(workdir);
  } catch (err) {
    tsc = {
      ran: true,
      passed: false,
      details: "tsc layer threw: " + String(err && err.message),
    };
  }
  try {
    tests = layerTests(workdir);
  } catch (err) {
    tests = {
      ran: true,
      passed: false,
      details: "tests layer threw: " + String(err && err.message),
    };
  }
  try {
    lint = layerLint(workdir);
  } catch (err) {
    lint = {
      ran: true,
      passed: false,
      details: "lint layer threw: " + String(err && err.message),
    };
  }

  const coreLayersPassed =
    (tsc.ran === false || tsc.passed === true) &&
    (tests.ran === false || tests.passed === true) &&
    (lint.ran === false || lint.passed === true);

  // Layer 4: qa (depends on core).
  let qa;
  try {
    qa = await layerQa({
      stateDir,
      workdir,
      filesChanged: files,
      coreLayersPassed,
    });
  } catch (err) {
    qa = {
      ran: true,
      passed: false,
      details: "qa layer threw: " + String(err && err.message),
    };
  }

  // Layer 5: backend (only when core passed).
  let backend;
  if (!coreLayersPassed) {
    backend = { ran: false, reason: "previous layers failed" };
  } else {
    try {
      backend = layerBackend(workdir, files);
    } catch (err) {
      backend = {
        ran: true,
        passed: false,
        details: "backend layer threw: " + String(err && err.message),
      };
    }
  }

  // Layer 6: visual (only when core passed).
  let visual;
  if (!coreLayersPassed) {
    visual = { ran: false, reason: "previous layers failed" };
  } else {
    try {
      visual = layerVisual(stateDir, workdir, files);
    } catch (err) {
      visual = {
        ran: true,
        passed: false,
        details: "visual layer threw: " + String(err && err.message),
      };
    }
  }

  const layers = { tsc, tests, lint, qa, backend, visual };
  const passed = Object.values(layers).every(
    (l) => l && (l.ran === false || l.passed === true),
  );

  const result = { passed, layers };

  // Persist verification.json atomically.
  try {
    atomicWriteJson(path.join(stateDir, "verification.json"), result);
  } catch (err) {
    // Surface the write failure but don't lose the verification result —
    // attach it to the returned object via a non-enumerable channel.
    result.persistError = String(err && err.message);
  }

  return result;
}

module.exports = { run };
