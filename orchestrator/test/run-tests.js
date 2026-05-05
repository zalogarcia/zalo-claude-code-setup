#!/usr/bin/env node
"use strict";

/**
 * Zero-dep test runner.
 *
 * Walks a directory tree, finds *.test.js files, and runs them under
 * `node --test`. Exits with the child's exit code so this is composable
 * with CI / npm scripts.
 *
 * Usage:
 *   node test/run-tests.js                # defaults to <orchestrator>/test/
 *   node test/run-tests.js path/to/dir
 *   node test/run-tests.js --help
 */

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

function printHelp() {
  process.stdout.write(
    [
      "Usage: node test/run-tests.js [dir]",
      "",
      "Finds *.test.js files under [dir] (default: <orchestrator-root>/test/)",
      "and runs them via `node --test`.",
      "",
      "Options:",
      "  --help, -h    Show this help and exit.",
      "",
    ].join("\n"),
  );
}

function findTestFiles(root) {
  /** @type {string[]} */
  const out = [];
  const stack = [root];
  while (stack.length) {
    const cur = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch (err) {
      console.error(`[run-tests] cannot read ${cur}: ${err.message}`);
      continue;
    }
    for (const ent of entries) {
      const full = path.join(cur, ent.name);
      if (ent.isDirectory()) {
        if (ent.name === "node_modules" || ent.name.startsWith(".")) continue;
        stack.push(full);
      } else if (ent.isFile() && ent.name.endsWith(".test.js")) {
        out.push(full);
      }
    }
  }
  out.sort();
  return out;
}

function main() {
  const arg = process.argv[2];
  if (arg === "--help" || arg === "-h") {
    printHelp();
    process.exit(0);
  }

  const defaultDir = path.join(__dirname);
  const dir = arg ? path.resolve(arg) : defaultDir;

  if (!fs.existsSync(dir)) {
    console.error(`[run-tests] directory not found: ${dir}`);
    process.exit(2);
  }

  const files = findTestFiles(dir);
  if (files.length === 0) {
    console.error(`[run-tests] no *.test.js files found in ${dir}`);
    process.exit(0);
  }

  const child = spawn(process.execPath, ["--test", ...files], {
    stdio: "inherit",
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      console.error(`[run-tests] child exited via signal ${signal}`);
      process.exit(1);
    }
    process.exit(code == null ? 1 : code);
  });

  child.on("error", (err) => {
    console.error(`[run-tests] failed to spawn node: ${err.message}`);
    process.exit(1);
  });
}

main();
