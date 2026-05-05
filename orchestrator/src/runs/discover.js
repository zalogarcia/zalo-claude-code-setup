"use strict";

const fs = require("fs");
const path = require("path");

/**
 * Safely list directory entries; returns [] on error (broken symlink, EACCES, ENOENT, ENOTDIR).
 * @param {string} dir
 * @returns {string[]}
 */
function safeReaddir(dir) {
  try {
    return fs.readdirSync(dir);
  } catch (_err) {
    return [];
  }
}

/**
 * Returns true if path exists AND is a directory. Defensive against broken symlinks.
 * @param {string} p
 * @returns {boolean}
 */
function isDir(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch (_err) {
    return false;
  }
}

/**
 * Walk each scanRoot two levels deep (scanRoot/* and scanRoot/*\/*).
 * For each candidate dir, check fs.existsSync(path.join(candidate, marker)).
 * Returns absolute paths of candidate dirs that contain the marker.
 *
 * @param {string[]} scanRoots - array of absolute paths to scan
 * @param {string} marker - the marker filename or subdir to look for inside each candidate
 * @returns {string[]} absolute paths of candidate dirs containing the marker
 */
function discoverByMarker(scanRoots, marker) {
  if (!Array.isArray(scanRoots)) return [];
  const found = [];
  const seen = new Set();

  for (const root of scanRoots) {
    if (typeof root !== "string" || !root) continue;
    if (!isDir(root)) continue;

    // Level 1: root/*
    const level1 = safeReaddir(root);
    for (const name1 of level1) {
      const candidate1 = path.join(root, name1);
      if (!isDir(candidate1)) continue;

      if (fs.existsSync(path.join(candidate1, marker))) {
        if (!seen.has(candidate1)) {
          seen.add(candidate1);
          found.push(candidate1);
        }
      }

      // Level 2: root/*\/*
      const level2 = safeReaddir(candidate1);
      for (const name2 of level2) {
        const candidate2 = path.join(candidate1, name2);
        if (!isDir(candidate2)) continue;

        if (fs.existsSync(path.join(candidate2, marker))) {
          if (!seen.has(candidate2)) {
            seen.add(candidate2);
            found.push(candidate2);
          }
        }
      }
    }
  }

  return found;
}

/**
 * Generalized discovery. Scans for .autoloop, .autopilot, and .symphony/issues/<id>/ markers.
 * Returns Array<{dir: string, runType: 'autoloop'|'autopilot'|'symphony', stateDir: string}>.
 *
 * For .autoloop / .autopilot:
 *   - dir = candidate workdir
 *   - stateDir = path.join(dir, '.autoloop' | '.autopilot')
 *
 * For .symphony, walks <candidate>/.symphony/issues/<*>/ and returns one entry per issue:
 *   - dir = candidate (the workdir)
 *   - stateDir = the issue subdir (e.g. /workdir/.symphony/issues/PROJ-123)
 *
 * @param {string[]} scanRoots
 * @returns {Array<{dir: string, runType: 'autoloop'|'autopilot'|'symphony', stateDir: string}>}
 */
function discoverRuns(scanRoots) {
  const out = [];

  // .autoloop
  for (const dir of discoverByMarker(scanRoots, ".autoloop")) {
    out.push({
      dir,
      runType: "autoloop",
      stateDir: path.join(dir, ".autoloop"),
    });
  }

  // .autopilot
  for (const dir of discoverByMarker(scanRoots, ".autopilot")) {
    out.push({
      dir,
      runType: "autopilot",
      stateDir: path.join(dir, ".autopilot"),
    });
  }

  // .symphony/issues — candidate has a .symphony/issues/ dir; enumerate ticket subdirs.
  const symphonyMarker = path.join(".symphony", "issues");
  for (const dir of discoverByMarker(scanRoots, symphonyMarker)) {
    const issuesDir = path.join(dir, ".symphony", "issues");
    const issueNames = safeReaddir(issuesDir);
    for (const issueName of issueNames) {
      const issueDir = path.join(issuesDir, issueName);
      if (!isDir(issueDir)) continue;
      out.push({
        dir,
        runType: "symphony",
        stateDir: issueDir,
      });
    }
  }

  return out;
}

/**
 * Given an existing project dir (workdir), check which marker exists.
 * Used by server.js to populate runType on legacy config.directories[] entries.
 * Priority: .autoloop > .autopilot > .symphony (returns the FIRST found).
 *
 * @param {string} dir
 * @returns {'autoloop'|'autopilot'|'symphony'|null}
 */
function runTypeForDir(dir) {
  if (typeof dir !== "string" || !dir) return null;

  if (fs.existsSync(path.join(dir, ".autoloop"))) return "autoloop";
  if (fs.existsSync(path.join(dir, ".autopilot"))) return "autopilot";

  const issuesDir = path.join(dir, ".symphony", "issues");
  if (isDir(issuesDir)) {
    // .symphony marker is only meaningful if there's at least one issue subdir
    const entries = safeReaddir(issuesDir);
    for (const name of entries) {
      if (isDir(path.join(issuesDir, name))) return "symphony";
    }
  }

  return null;
}

module.exports = { discoverByMarker, discoverRuns, runTypeForDir };
