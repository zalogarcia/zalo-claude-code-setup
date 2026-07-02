#!/usr/bin/env python3
"""
PreToolUse hook: block `git commit` / `git push` if gitleaks finds secrets.

Runs only on Bash tool calls that invoke git commit or git push.
- commit: scans the STAGED DIFF only (`gitleaks git --pre-commit --staged`).
- push: scans unpushed commits against upstream (`gitleaks git --log-opts`);
  without an upstream, only the most recent commits — never the full history.
Scans run from the repo root so the repo's `.gitleaksignore` (fingerprint
allowlist) is always found. Known false-positive SHAPES (voiceApiKeyRef test
fixtures, docs `Authorization: Bearer` examples in *.md) are allowlisted via
an embedded config extension, injected only when neither the repo nor the
environment pins its own gitleaks config.
Fails open: if gitleaks is missing, errors out, or exceeds the internal
scan timeout, the git operation is allowed with a warning.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys

# Hard cap per scan. The harness kills this hook at 30s; staying well under
# that keeps `git commit` from eating the Bash tool-call budget (the old
# "commit hangs but lands" failure mode).
SCAN_TIMEOUT_SECS = 10

# Push without an upstream used to scan the FULL repo history (the hang).
# Bound it to the most recent commits instead.
PUSH_FALLBACK_LOG_OPTS = "--max-count=50"

# Extends the default gitleaks config. Injected via GITLEAKS_CONFIG_TOML
# unless the repo has its own .gitleaks.toml or the env pins a config.
# - sbp_ rule: Supabase personal access tokens; the default `generic-api-key`
#   rule only catches them with keyword context + entropy, so bare tokens
#   slipped through.
# - allowlists: known false-positive shapes. Per-finding fingerprints belong
#   in the repo's .gitleaksignore, not here.
EMBEDDED_CONFIG = r"""
[extend]
useDefault = true

[[rules]]
id = "supabase-access-token-sbp"
description = "Supabase personal access token (sbp_ prefix)"
regex = '''sbp_[A-Za-z0-9]{40,}'''
keywords = ["sbp_"]

[[allowlists]]
description = "voiceApiKeyRef test fixtures (known false positive)"
regexTarget = "line"
regexes = ['''voiceApiKeyRef''']

[[allowlists]]
description = "docs Authorization: Bearer examples in markdown"
condition = "AND"
paths = ['''(?i)\.(md|mdx)$''']
regexTarget = "line"
regexes = ['''(?i)authorization:\s*bearer''']
"""


_GIT_VALUE_OPTS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix",
}


def parses_to_git_subcommand(cmd: str, sub: str) -> bool:
    for sep in ("&&", "||", ";", "|"):
        cmd = cmd.replace(sep, "\n")
    for line in cmd.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError:
            continue
        if not tokens:
            continue
        # Allow a leading `eval` / `exec` wrapper; otherwise only treat token 0
        # as the command position so pathspecs like `git log -- git commit` are
        # not misread.
        start = 0
        while start < len(tokens) and tokens[start] in ("eval", "exec"):
            start += 1
        if start >= len(tokens):
            continue
        cmd_tok = tokens[start]
        if cmd_tok != "git" and not cmd_tok.endswith("/git"):
            continue
        j = start + 1
        while j < len(tokens):
            t = tokens[j]
            if t in _GIT_VALUE_OPTS:
                j += 2  # skip flag and its separate value
                continue
            if t.startswith("-"):
                j += 1  # flag with no separate value (or --key=value form)
                continue
            break
        if j < len(tokens) and tokens[j] == sub:
            return True
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd:
        sys.exit(0)

    is_commit = parses_to_git_subcommand(cmd, "commit")
    is_push = parses_to_git_subcommand(cmd, "push")
    if not (is_commit or is_push):
        sys.exit(0)

    if not shutil.which("gitleaks"):
        sys.stderr.write("gitleaks-guard: gitleaks not installed; skipping scan\n")
        sys.exit(0)

    cwd = data.get("cwd") or os.getcwd()
    top = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if top.returncode != 0:
        sys.exit(0)
    repo_root = top.stdout.strip() or cwd

    env = os.environ.copy()
    if not (
        "GITLEAKS_CONFIG" in env
        or "GITLEAKS_CONFIG_TOML" in env
        or os.path.isfile(os.path.join(repo_root, ".gitleaks.toml"))
    ):
        env["GITLEAKS_CONFIG_TOML"] = EMBEDDED_CONFIG

    # Leaks exit with 99; any other nonzero exit is a scan error (fail open).
    base = ["gitleaks", "git", "--redact", "-v", "--exit-code", "99"]
    if is_commit:
        args = base + ["--pre-commit", "--staged"]
    else:
        upstream = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--abbrev-ref", "@{u}"],
            capture_output=True, text=True,
        )
        if upstream.returncode == 0 and upstream.stdout.strip():
            log_range = f"{upstream.stdout.strip()}..HEAD"
            args = base + ["--log-opts", log_range]
        else:
            args = base + ["--log-opts", PUSH_FALLBACK_LOG_OPTS]

    try:
        result = subprocess.run(
            args, cwd=repo_root, env=env, capture_output=True, text=True,
            timeout=SCAN_TIMEOUT_SECS,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"gitleaks-guard: scan exceeded {SCAN_TIMEOUT_SECS}s — "
            "allowing git operation WITHOUT a completed secret scan. "
            "Review the diff for secrets manually.\n"
        )
        sys.exit(0)

    if result.returncode == 99:
        sys.stderr.write("gitleaks-guard: SECRETS DETECTED — blocking git operation\n")
        if result.stdout:
            sys.stderr.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        sys.stderr.write(
            "\nFix the leak (scrub the value, unstage the file, add an "
            "inline `gitleaks:allow` comment, or add a fingerprint to the "
            "repo's .gitleaksignore), then retry.\n"
        )
        sys.exit(2)

    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        sys.stderr.write(
            f"gitleaks-guard: gitleaks errored (exit {result.returncode}); "
            "skipping scan\n"
        )
        for line in tail:
            sys.stderr.write(f"gitleaks-guard:   {line}\n")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
