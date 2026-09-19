#!/usr/bin/env python3
"""Test suite for npm-install-guard.py.

Run: python3 ~/.claude/hooks/npm-install-guard.test.py

If you change the guard, this must stay green. The guard is deny-by-default on
a security boundary, so both directions matter: a false allow silently reopens
the hole, a false block strands every agent that legitimately runs `npm ci`.

No network: `age_days` is stubbed per-case.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "npm-install-guard.py")
spec = importlib.util.spec_from_file_location("npm_install_guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

PASS, FAIL = 0, 0
FAILURES = []


def run(command, cwd=".", tool="Bash", age=(400.0, "1.0.0"), raw=None):
    """Invoke the guard's main() with a synthetic payload. Returns exit code."""
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command}, "cwd": cwd}
    )
    old_stdin, old_stderr, old_age = sys.stdin, sys.stderr, guard.age_days
    sys.stdin = io.StringIO(payload)
    sys.stderr = io.StringIO()
    guard.age_days = lambda name, version: age
    try:
        return guard.main()
    finally:
        sys.stdin, sys.stderr, guard.age_days = old_stdin, old_stderr, old_age


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
    else:
        FAIL += 1
        verb = {0: "ALLOW", 2: "BLOCK"}
        FAILURES.append(f"  {label}\n    wanted {verb.get(want)}, got {verb.get(got)}")


# --- fixtures ---------------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="npm-guard-test-")

# repo WITH a lockfile and one declared dep
locked = os.path.join(tmp, "locked")
os.makedirs(locked)
with open(os.path.join(locked, "package.json"), "w") as fh:
    json.dump({"dependencies": {"zod": "^3.0.0"}, "devDependencies": {"vitest": "^1"}}, fh)
open(os.path.join(locked, "package-lock.json"), "w").write("{}")

# repo WITHOUT a lockfile
fresh = os.path.join(tmp, "fresh")
os.makedirs(fresh)
with open(os.path.join(fresh, "package.json"), "w") as fh:
    json.dump({"dependencies": {"zod": "^3.0.0"}}, fh)

# a directory with no package.json at all
bare = os.path.join(tmp, "bare")
os.makedirs(bare)

OLD = (400.0, "3.22.4")  # comfortably past the cooldown
NEW = (0.4, "6.0.0")  # the keyv-6.0.0 shape: hours old

# --- allow: non-install commands --------------------------------------------
check("npm ci", run("npm ci", locked), 0)
check("npm ci --omit=dev", run("npm ci --omit=dev", locked), 0)
check("npm run build", run("npm run build", locked), 0)
check("npm test", run("npm test", locked), 0)
check("npm rebuild sharp", run("npm rebuild sharp", locked), 0)
check("npm ls keyv", run("npm ls keyv", locked), 0)
check("npm view keyv time", run("npm view keyv time", locked), 0)
check("npm uninstall zod", run("npm uninstall zod", locked), 0)
check("npx tsx (documented gap)", run("npx tsx script.ts", locked), 0)
check("unrelated command", run("git status", locked), 0)

# --- allow: safe installs ---------------------------------------------------
check("bare install, no lockfile", run("npm install", fresh), 0)
check("bare install, no package.json", run("npm install", bare), 0)
check("existing dep, past cooldown", run("npm install zod", locked, age=OLD), 0)
check("existing devDep, past cooldown", run("npm install vitest", locked, age=OLD), 0)
check("raise the cooldown floor", run("npm config set min-release-age 14", locked), 0)

# --- block: lockfile discipline ---------------------------------------------
check("bare install WITH lockfile", run("npm install", locked), 2)
check("bare `npm i` WITH lockfile", run("npm i", locked), 2)

# --- block: new dependency --------------------------------------------------
check("new dep", run("npm install left-pad", locked, age=OLD), 2)
check("new scoped dep", run("npm install @scope/thing", locked, age=OLD), 2)
check("new dep, no package.json", run("npm install left-pad", bare, age=OLD), 2)

# --- block: cooldown --------------------------------------------------------
check("existing dep, TOO FRESH", run("npm install zod", locked, age=NEW), 2)
check("existing dep, pinned fresh version", run("npm install zod@3.99.0", locked, age=NEW), 2)
check("registry lookup failed -> fail closed", run("npm install zod", locked, age=(None, None)), 2)

# --- block: privilege / weakening -------------------------------------------
check("global install", run("npm install -g npm@latest", locked), 2)
check("global install --global", run("npm install --global foo", locked), 2)
check("--ignore-scripts=false", run("npm install zod --ignore-scripts=false", locked, age=OLD), 2)
check("--min-release-age=0", run("npm install zod --min-release-age=0", locked, age=OLD), 2)
check("lower the cooldown floor", run("npm config set min-release-age 0", locked), 2)

# --- block: evasion shapes --------------------------------------------------
check("chained with &&", run("cd /tmp && npm install left-pad", locked, age=OLD), 2)
check("chained with ;", run("echo hi ; npm install left-pad", locked, age=OLD), 2)
check("bash -c wrapper", run('bash -c "npm install left-pad"', locked, age=OLD), 2)
check("sh -c wrapper", run("sh -c 'npm install left-pad'", locked, age=OLD), 2)
check("env-var prefix", run("CI=1 npm install left-pad", locked, age=OLD), 2)

# --- block: other package managers ------------------------------------------
check("yarn add", run("yarn add left-pad", locked, age=OLD), 2)
check("pnpm add", run("pnpm add left-pad", locked, age=OLD), 2)
check("bun add", run("bun add left-pad", locked, age=OLD), 2)

# --- allow: never block on junk ---------------------------------------------
check("non-Bash tool", run("npm install left-pad", locked, tool="Edit"), 0)
check("malformed payload", run(None, raw="not json at all"), 0)
check("empty command", run("", locked), 0)
check("unbalanced quotes", run('npm install "unclosed', locked, age=OLD), 2)

# --- regression: MENTIONING an install is not PERFORMING one -----------------
# All four of these hit the guard for real on 2026-08-05. The first one blocked
# an innocent CI audit: the raw-text splitter cut inside the quoted grep
# pattern and read the fragment `npm i " $wf` as installing a package named `"`.
# A guard that cries wolf trains agents to route around it, so these are as
# load-bearing as the blocks below.
check(
    "grep pattern containing an install command",
    run(r'grep -h "npm install\|npm i " file.yml', locked, age=OLD),
    0,
)
check("grep -rn for npm install", run('grep -rn "npm install" .', locked, age=OLD), 0)
check("echo mentioning npm install", run('echo "run npm install first"', locked, age=OLD), 0)
check(
    "heredoc body mentioning npm install",
    run("cat > /tmp/brief.md <<'EOF'\nnpm install left-pad\nEOF", locked, age=OLD),
    0,
)
check(
    "heredoc body, real install after terminator",
    run(
        "cat > /tmp/brief.md <<'EOF'\nsome docs\nEOF\nnpm install left-pad",
        locked,
        age=OLD,
    ),
    2,
)

# --- regression: separators that must still split ----------------------------
# shlex treats "\n" as ordinary whitespace, so a multi-line script would
# otherwise collapse into one segment beginning `echo` and sail straight past.
check("newline-separated install", run("echo hi\nnpm install left-pad", locked, age=OLD), 2)
check("semicolon, no spaces", run("echo hi;npm install left-pad", locked, age=OLD), 2)
check("&& with no spaces", run("cd /tmp&&npm install left-pad", locked, age=OLD), 2)
check(
    "install on a later line of a script",
    run("set -e\ncd /tmp\nnpm install left-pad\necho done", locked, age=OLD),
    2,
)

# --- report -----------------------------------------------------------------
total = PASS + FAIL
print(f"npm-install-guard: {PASS}/{total} passed")
if FAILURES:
    print("\nFAILURES:")
    print("\n".join(FAILURES))
sys.exit(1 if FAIL else 0)
