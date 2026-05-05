"use strict";

/**
 * Harness adapter registry.
 *
 * Loads each adapter at module-require time. If an adapter file is missing or
 * throws on require (e.g. a syntax error in `claude-code.js`), THIS module will
 * throw too — which is the desired behavior. Per PLAN.md, the orchestrator
 * commits all adapter files in the same batch, so a missing adapter at runtime
 * indicates a packaging bug, not an expected state. Failing loudly here is
 * preferable to silently returning a stub.
 *
 * @typedef {import('./types').HarnessAdapter} HarnessAdapter
 */

const claudeCode = require("./claude-code"); // wu-4 creates this in the same batch
const codex = require("./codex");

/** @type {{ [id: string]: HarnessAdapter }} */
const adapters = {
  "claude-code": claudeCode,
  codex: codex,
};

/**
 * Resolve a harness adapter by id.
 *
 * @param {string} id - one of 'claude-code' | 'codex'
 * @returns {HarnessAdapter}
 * @throws {Error} if the id is not registered
 */
function pickAdapter(id) {
  const adapter = adapters[id];
  if (!adapter) {
    throw new Error("Unknown adapter: " + id);
  }
  return adapter;
}

module.exports = { pickAdapter, adapters };
