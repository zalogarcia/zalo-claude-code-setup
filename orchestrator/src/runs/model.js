"use strict";

/**
 * Run data model loader.
 *
 * Pure CommonJS module. No top-level side effects.
 *
 * @typedef {import('../harness/types').Run} Run
 * @typedef {import('../harness/types').RunType} RunType
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const { readManifest } = require("./manifest");

/**
 * Compute a stable 12-char hex id from an absolute stateDir path.
 *
 * @param {string} stateDir
 * @returns {string}
 */
function computeId(stateDir) {
  return crypto.createHash("sha1").update(stateDir).digest("hex").slice(0, 12);
}

/**
 * Infer the runType from a stateDir path.
 *
 * Rules:
 *   basename `.autoloop`                     -> 'autoloop'
 *   basename `.autopilot`                    -> 'autopilot'
 *   path contains `/.symphony/issues/`       -> 'symphony'
 *   else                                     -> 'unknown'
 *
 * @param {string} stateDir
 * @returns {RunType | 'unknown'}
 */
function inferRunType(stateDir) {
  const base = path.basename(stateDir);
  if (base === ".autoloop") return "autoloop";
  if (base === ".autopilot") return "autopilot";
  // Symphony state dirs live at <workdir>/.symphony/issues/<id>/
  // Normalize separator for cross-platform safety.
  const normalized = stateDir.split(path.sep).join("/");
  if (normalized.indexOf("/.symphony/issues/") !== -1) return "symphony";
  return "unknown";
}

/**
 * Load a Run from a stateDir.
 *
 * 1. If `<stateDir>/manifest.json` exists and parses, return the deserialized Run
 *    (with `id`, `stateDir`, and `workdir` filled in from arguments if absent).
 * 2. Otherwise, return a minimal Run inferred from the marker basename.
 *
 * @param {string} stateDir - absolute path to the state dir (e.g. /repo/.autopilot)
 * @param {string} workdir  - absolute path to the project root containing the marker
 * @returns {Run}
 */
function loadRun(stateDir, workdir) {
  const manifest = readManifest(stateDir);
  if (manifest) {
    // Trust manifest fields, but ensure id/stateDir/workdir are populated.
    if (!manifest.id) manifest.id = computeId(stateDir);
    if (!manifest.stateDir) manifest.stateDir = stateDir;
    if (!manifest.workdir) manifest.workdir = workdir;
    return manifest;
  }

  /** @type {Run} */
  const run = {
    id: computeId(stateDir),
    type: inferRunType(stateDir),
    harness: "unknown",
    workdir: workdir,
    stateDir: stateDir,
    status: "idle",
    phase: null,
    manifestVersion: 0,
  };
  return run;
}

module.exports = { loadRun };
