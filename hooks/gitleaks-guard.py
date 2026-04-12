#!/usr/bin/env python3
"""
PreToolUse hook: block `git commit` / `git push` if gitleaks finds secrets.

Runs only on Bash tool calls that invoke git commit or git push.
- commit: scans staged changes (`gitleaks git --staged`).
- push: scans unpushed commits against upstream (`gitleaks git --log-opts`).
Fails open if gitleaks is not installed.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys


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
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "git" or tok.endswith("/git"):
                j = i + 1
                while j < len(tokens) and tokens[j].startswith("-"):
                    j += 1
                if j < len(tokens) and tokens[j] == sub:
                    return True
            i += 1
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
    r = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(0)

    if is_commit:
        result = subprocess.run(
            ["gitleaks", "git", "--staged", "--redact", "-v"],
            cwd=cwd, capture_output=True, text=True,
        )
    else:
        upstream = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "@{u}"],
            capture_output=True, text=True,
        )
        if upstream.returncode == 0 and upstream.stdout.strip():
            log_range = f"{upstream.stdout.strip()}..HEAD"
            result = subprocess.run(
                ["gitleaks", "git", "--redact", "-v", "--log-opts", log_range],
                cwd=cwd, capture_output=True, text=True,
            )
        else:
            result = subprocess.run(
                ["gitleaks", "git", "--redact", "-v"],
                cwd=cwd, capture_output=True, text=True,
            )

    if result.returncode != 0:
        sys.stderr.write("gitleaks-guard: SECRETS DETECTED — blocking git operation\n")
        if result.stdout:
            sys.stderr.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        sys.stderr.write(
            "\nFix the leak (scrub the value, unstage the file, or add an "
            "inline `gitleaks:allow` comment), then retry.\n"
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
