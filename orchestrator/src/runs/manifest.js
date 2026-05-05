"use strict";

/**
 * Run manifest helpers — atomic write + safe read for `<stateDir>/manifest.json`.
 *
 * Pure CommonJS module. No top-level side effects.
 *
 * @typedef {import('../harness/types').Run} Run
 */

const fs = require("fs");
const path = require("path");

/**
 * Atomically write a Run manifest to `<stateDir>/manifest.json`.
 *
 * Strategy: ensure the directory exists, write JSON to `manifest.json.tmp`,
 * then `fs.renameSync` to `manifest.json`. Rename within the same filesystem
 * is atomic on POSIX, so readers never see a torn file.
 *
 * Mutates `run.manifestVersion` to `1` if it is missing/zero/falsy.
 *
 * @param {string} stateDir
 * @param {Run} run
 * @returns {void}
 */
function writeManifest(stateDir, run) {
  if (!run.manifestVersion) {
    run.manifestVersion = 1;
  }
  fs.mkdirSync(stateDir, { recursive: true });
  const finalPath = path.join(stateDir, "manifest.json");
  const tmpPath = finalPath + ".tmp";
  const json = JSON.stringify(run, null, 2);
  fs.writeFileSync(tmpPath, json, "utf8");
  fs.renameSync(tmpPath, finalPath);
}

/**
 * Read and parse `<stateDir>/manifest.json`.
 *
 * Returns `null` on any failure (missing file, parse error, I/O error).
 * Never throws.
 *
 * @param {string} stateDir
 * @returns {Run | null}
 */
function readManifest(stateDir) {
  try {
    const filePath = path.join(stateDir, "manifest.json");
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw);
  } catch (_err) {
    return null;
  }
}

module.exports = { writeManifest, readManifest };
