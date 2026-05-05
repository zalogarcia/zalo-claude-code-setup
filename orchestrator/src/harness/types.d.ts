// orchestrator/src/harness/types.d.ts
//
// Declaration-only types for the HarnessAdapter seam and the Run data model.
// Consumed by JSDoc `@typedef {import('./types').HarnessAdapter}` references in JS files.
// No runtime emit — this file is never required at runtime.

// -----------------------------------------------------------------------------
// HarnessAdapter interface (the seam)
// -----------------------------------------------------------------------------

export type RunIntent = {
  type: "symphony" | "autopilot" | "autoloop";
  workdir: string; // absolute path
  stateDir: string; // .symphony/issues/<id>, .autopilot, .autoloop
  prompt: string; // seed prompt or approved plan
  systemPromptFile?: string; // skill/instructions file
  budgetUsd?: number;
  timeoutSec?: number;
  model?: string;
  scope?: string[]; // files/dirs in scope (Tier 2 hint)
};

export type RunHandle = {
  pid: number;
  pgid?: number;
  agentLog: string; // path to streaming output
  start: Date;
  cancel(): Promise<void>;
};

export type RunResult = {
  exitCode: number;
  reason: "clean" | "crash" | "stall" | "timeout" | "budget" | "cancelled";
  filesChanged: string[]; // from git diff
  costUsd?: number;
  markers: string[]; // H2 markers found in output
};

export interface HarnessAdapter {
  readonly id: "claude-code" | "codex" | "aider" | string;
  readonly tier: 1 | 2;

  readonly capabilities: {
    subagents: boolean;
    streamJsonEvents: boolean;
    appendSystemPrompt: boolean;
    budgetCap: boolean;
  };

  spawn(intent: RunIntent): Promise<RunHandle>;
  status(handle: RunHandle): Promise<"running" | "exited" | "crashed">;
  collect(handle: RunHandle): Promise<RunResult>;

  // Tier 1 only — Tier 2 throws NotSupported
  dispatchSubagent?(
    name: string,
    prompt: string,
    opts?: object,
  ): Promise<RunResult>;
}

// -----------------------------------------------------------------------------
// The Run data model
// -----------------------------------------------------------------------------

export type RunType = "autoloop" | "autopilot" | "symphony";

export type Run = {
  id: string; // hash of stateDir
  type: RunType;
  harness: "claude-code" | "codex" | "unknown";
  workdir: string;
  stateDir: string;
  status: "idle" | "running" | "awaiting-approval" | "completed" | "failed";
  phase: string | null; // current phase from phase.txt
  manifestVersion: number;
  startedAt?: string;
  pid?: number;
  // Symphony-specific (null/undefined for other types)
  linearTicketId?: string;
  linearStatus?: string;
};
