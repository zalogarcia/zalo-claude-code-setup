"use strict";

const { execFileSync } = require("child_process");

/**
 * Git/PR helper module for the symphony orchestrator.
 *
 * Uses `execFileSync` (NOT `execSync`) — passes args as an array so there is no
 * shell interpolation. Always passes `cwd` and `encoding: 'utf8'`.
 */

function runGit(workdir, args, opts = {}) {
  return execFileSync("git", ["-C", workdir, ...args], {
    encoding: "utf8",
    ...opts,
  });
}

function ensureBranch(workdir, branchName) {
  if (typeof branchName !== "string" || branchName.length === 0) {
    throw new Error("ensureBranch: branchName must be a non-empty string");
  }
  let exists = false;
  try {
    execFileSync("git", ["-C", workdir, "rev-parse", "--verify", branchName], {
      encoding: "utf8",
      stdio: ["ignore", "ignore", "ignore"],
    });
    exists = true;
  } catch (_e) {
    exists = false;
  }
  if (exists) {
    runGit(workdir, ["checkout", branchName], {
      stdio: ["ignore", "ignore", "pipe"],
    });
  } else {
    runGit(workdir, ["checkout", "-b", branchName], {
      stdio: ["ignore", "ignore", "pipe"],
    });
  }
}

function validateAllowedPaths(allowedPaths) {
  if (!Array.isArray(allowedPaths) || allowedPaths.length === 0) {
    throw new Error(
      "commitAll: allowedPaths must be a non-empty array of explicit paths",
    );
  }
  const FORBIDDEN = new Set([".", "-A", "-a", "*"]);
  for (const p of allowedPaths) {
    if (typeof p !== "string" || p.length === 0) {
      throw new Error("commitAll: each path must be a non-empty string");
    }
    if (FORBIDDEN.has(p)) {
      throw new Error(
        `commitAll: forbidden path argument "${p}" (refusing wildcard / add-all)`,
      );
    }
    if (p.startsWith("-")) {
      throw new Error(
        `commitAll: path "${p}" starts with "-" (refusing flag-like argument)`,
      );
    }
    if (p.includes("..")) {
      throw new Error(
        `commitAll: path "${p}" contains ".." (refusing parent-traversal)`,
      );
    }
  }
}

function commitAll(workdir, message, allowedPaths) {
  validateAllowedPaths(allowedPaths);
  if (typeof message !== "string" || message.length === 0) {
    throw new Error("commitAll: message must be a non-empty string");
  }
  for (const p of allowedPaths) {
    runGit(workdir, ["add", p], { stdio: ["ignore", "ignore", "pipe"] });
  }
  runGit(workdir, ["-c", "commit.gpgsign=false", "commit", "-m", message], {
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function currentBranch(workdir) {
  const out = runGit(workdir, ["rev-parse", "--abbrev-ref", "HEAD"]);
  return out.trim();
}

function filesChangedSince(workdir, baseRef) {
  if (typeof baseRef !== "string" || baseRef.length === 0) {
    throw new Error("filesChangedSince: baseRef must be a non-empty string");
  }
  const out = runGit(workdir, ["diff", "--name-only", `${baseRef}..HEAD`]);
  return out.split("\n").filter((line) => line.length > 0);
}

function hasUncommittedChanges(workdir) {
  const out = runGit(workdir, ["status", "--porcelain"]);
  // Exclude Symphony's own state dir — `<workdir>/.symphony/issues/<id>/`
  // is operational metadata (manifest, plan, agent.log), not user code, and
  // it lives in the workdir by design (per-project per-ticket isolation).
  // Users who want it tracked can add it to .gitignore selectively.
  const lines = out
    .split("\n")
    .filter((l) => l.length > 0)
    .filter((l) => !/\s\.symphony(\/|$)/.test(l));
  return lines.length > 0;
}

async function openPR(workdir, { title, body, label, base = "main" } = {}) {
  if (typeof title !== "string" || title.length === 0) {
    throw new Error("openPR: title must be a non-empty string");
  }
  if (typeof body !== "string") {
    throw new Error("openPR: body must be a string");
  }
  if (typeof label !== "string" || label.length === 0) {
    throw new Error("openPR: label must be a non-empty string");
  }

  // Validate gh auth.
  try {
    execFileSync("gh", ["auth", "status"], {
      cwd: workdir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (_e) {
    throw new Error("gh CLI not authenticated");
  }

  const head = currentBranch(workdir);
  if (head === base) {
    throw new Error(
      `openPR: refusing to PR ${base} into itself — checkout the symphony branch first`,
    );
  }

  // Push the symphony branch to origin before opening the PR.
  // gh pr create requires the branch to exist on the remote.
  // We use --set-upstream so subsequent pushes from the same branch work.
  // Note: this is a write to the remote, but it's a NEW symphony/<id> branch,
  // never to main/master/dev (per ~/.claude/rules/git-safety.md).
  try {
    execFileSync(
      "git",
      ["-C", workdir, "push", "--set-upstream", "origin", head],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (e) {
    const stderr = (e.stderr || e.message || "").toString();
    throw new Error(`openPR: failed to push branch ${head}: ${stderr}`);
  }

  // Auto-create the PR label on the GitHub repo if missing.
  // gh pr create --label fails hard with "not found" if absent.
  // Idempotent: if it exists, gh exits non-zero with "already exists" — we swallow.
  try {
    const color = label.includes("shallow") ? "B0AEA5" : "D97757";
    const desc = label.includes("shallow")
      ? "Symphony Tier-2 auto-PR — shallow verification"
      : "Symphony Tier-1 auto-PR — full QA";
    execFileSync(
      "gh",
      ["label", "create", label, "--color", color, "--description", desc],
      { cwd: workdir, stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (_) {
    /* label exists — fine */
  }

  const stdout = execFileSync(
    "gh",
    [
      "pr",
      "create",
      "-t",
      title,
      "-F",
      "-",
      "-B",
      base,
      "-H",
      head,
      "-l",
      label,
    ],
    {
      cwd: workdir,
      input: body,
      encoding: "utf8",
    },
  );
  return { url: stdout.trim() };
}

module.exports = {
  ensureBranch,
  commitAll,
  currentBranch,
  filesChangedSince,
  openPR,
  hasUncommittedChanges,
};
