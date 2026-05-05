"use strict";

/**
 * Codex Tier-2 adapter — STUB for Stage 0+1.
 *
 * Implements the structural shape of HarnessAdapter so the registry can resolve it,
 * but every lifecycle method throws NotImplemented. This intentionally fails loud
 * (per the orchestrator's "clean failure preferable to silent stubs" stance) when
 * any caller tries to actually run something through it. Stage 2+ will replace
 * the throwing methods with real `child_process.spawn` calls into Codex.
 *
 * Capabilities reflect Codex's real surface:
 *   - subagents: false           — Tier 2 has no native subagent dispatch
 *   - streamJsonEvents: false    — output is plain text, not structured events
 *   - appendSystemPrompt: true   — supports a system-prompt file flag
 *   - budgetCap: false           — no first-class USD budget enforcement
 *
 * Tier 2 omits `dispatchSubagent` entirely (HarnessAdapter has it as optional).
 *
 * @type {import('./types').HarnessAdapter}
 */
const codexAdapter = {
  id: "codex",
  tier: 2,
  capabilities: {
    subagents: false,
    streamJsonEvents: false,
    appendSystemPrompt: true,
    budgetCap: false,
  },

  /**
   * @param {import('./types').RunIntent} _intent
   * @returns {Promise<import('./types').RunHandle>}
   */
  spawn(_intent) {
    throw new Error("NotImplemented: codex adapter is a stub for Stage 0+1");
  },

  /**
   * @param {import('./types').RunHandle} _handle
   * @returns {Promise<'running'|'exited'|'crashed'>}
   */
  status(_handle) {
    throw new Error("NotImplemented: codex adapter status");
  },

  /**
   * @param {import('./types').RunHandle} _handle
   * @returns {Promise<import('./types').RunResult>}
   */
  collect(_handle) {
    throw new Error("NotImplemented: codex adapter collect");
  },
};

module.exports = codexAdapter;
