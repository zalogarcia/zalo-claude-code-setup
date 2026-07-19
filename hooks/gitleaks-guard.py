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
import re
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

# Destructive-git guard (weekly audit 2026-07-19, P6): one subagent's mass
# revert on the shared working tree wiped 11 sibling agents' uncommitted work
# (~2M+ redo tokens). git-safety.md requires explicit user approval for these
# ops — prose the subagent had never read. This hook fires in subagent
# contexts too, so the rule is now enforced at the tool layer.
# Override: the user-approved re-run carries a literal `# user-approved`
# comment in the command (kept dumb by design).
_DESTRUCTIVE_STASH_SUBS = {"push", "pop", "drop", "clear", "apply"}


def _first_positional(args):
    for a in args:
        if not a.startswith("-"):
            return a
    return None


def _strip_heredoc_bodies(cmd: str) -> str:
    """Drop heredoc body lines so text INSIDE a commit message (e.g. a
    changelog line reading 'git reset --hard now requires approval') is never
    parsed as a command (QA 2026-07-19: heredoc commits documenting the guard
    were false-blocked). Fail-open by design: a bogus << match skips lines
    until its tag, which can only under-block, never over-block."""
    out = []
    lines = cmd.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.search(r"<<-?\s*(['\"]?)(\w+)\1", line)
        if m:
            tag = m.group(2)
            i += 1
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
        i += 1
    return "\n".join(out)


def destructive_git_op(cmd: str):
    """Return a short description of the first destructive git operation in
    cmd, or None. Same tokenization as parses_to_git_subcommand; parse
    uncertainty returns None (fail open — the permission prompt still exists)."""
    cmd = _strip_heredoc_bodies(cmd)
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
                j += 2
                continue
            if t.startswith("-"):
                j += 1
                continue
            break
        if j >= len(tokens):
            continue
        sub = tokens[j]
        args = tokens[j + 1:]
        if sub == "reset" and "--hard" in args:
            return "git reset --hard"
        if sub == "checkout" and "." in args:
            return "git checkout ."
        if sub == "restore" and "." in args:
            # `git restore --staged .` only unstages (index, recoverable) —
            # allow unless --worktree re-adds the working-tree target.
            if "--staged" in args and "--worktree" not in args:
                continue
            return "git restore ."
        if sub == "clean" and any(
            (a.startswith("-") and not a.startswith("--") and "f" in a)
            or a == "--force"
            for a in args
        ):
            return "git clean -f"
        if sub == "stash":
            stash_sub = _first_positional(args)
            if stash_sub is None or stash_sub in _DESTRUCTIVE_STASH_SUBS:
                return f"git stash {stash_sub or 'push'}"
    return None


def parses_to_git_subcommand(cmd: str, sub: str) -> bool:
    # Heredoc bodies are data, not commands: without stripping, a doc line
    # starting `git push ...` inside `cat <<EOF > notes.md` misdetects as a
    # push and triggers a pointless (or false-blocking) scan.
    cmd = _strip_heredoc_bodies(cmd)
    for sep in ("&&", "||", ";", "|"):
        cmd = cmd.replace(sep, "\n")
    for line in cmd.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            tokens = shlex.split(line, comments=False, posix=True)
        except ValueError:
            # Unbalanced quotes — e.g. line 1 of the CANONICAL heredoc commit,
            # `git commit -m "$(cat <<'EOF'` — must fail TOWARD scanning, not
            # away from it (QA 2026-07-19: shlex ValueError → continue meant
            # the commit-time secret scan never ran on commit-with-heredoc;
            # a worst case is a harmless extra scan). destructive_git_op keeps
            # the strict continue: for a BLOCKER, fail-open is the safe side.
            tokens = line.split()
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

    if "# user-approved" not in cmd:
        destructive = destructive_git_op(cmd)
        if destructive:
            sys.stderr.write(
                f"BLOCKED (git-guard): '{destructive}' discards uncommitted work — "
                "explicit user approval required per ~/.claude/rules/git-safety.md. "
                "If you are a subagent: git is READ-ONLY for you; report the need "
                "to the orchestrator instead of running this. If the user already "
                "approved this exact operation in this session, re-run it with the "
                "comment `# user-approved` appended to the command.\n"
            )
            sys.exit(2)

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
