r"""
PreToolUse hook: guard cross-session tmux control (deny-by-default).

Sessions message each other via `tmux send-keys` (see CLAUDE.md "Inter-Session
Messaging"). Every session runs --dangerously-skip-permissions, so an injected
instruction read from a web page, repo file, or PR body would otherwise execute
machine-wide. This hook blocks tmux verbs that can interrupt, kill, or inject
into ANOTHER session.

Design (v2, after an audit walked past v1 with `tmux kill-ses`):
  - ALLOW-LIST of read-only/self-scoped verbs; everything else that names a
    target other than your own session is DENIED.
  - Subcommands are normalized through tmux's own alias table AND unambiguous
    prefix expansion (`kill-ses` -> `kill-session`, `killp` -> `kill-pane`).
  - Targets parsed in every spelling: `-t X`, `-tX`, `-t=X`, `sess:win.pane`.
  - `\;` command sequences and shell operators split into segments; every
    segment is checked. Nested `bash -c "..."` strings are scanned recursively.
  - Unparseable tmux invocations fail CLOSED.
  - Killing a session is allowed only when that session is NOT running claude
    (so a headless helper can clean up a scratch session it made) — never
    `kill-server`, which would take everything down.
  - There is deliberately NO in-band escape hatch: any token the assistant can
    type is a token injected text can tell it to type. To force a blocked
    action, the owner runs it in their own terminal.

LIMITS (documented honestly): static string analysis cannot see through
variable indirection (`T=tmux; $T ...`), base64/eval obfuscation, or a script
written to disk and executed. This is a guardrail against the realistic
injection path — plain instructions embedded in fetched content — not a sandbox.
"""
import json
import os
import re
import shlex
import subprocess
import sys

TMUX_BIN = None

# tmux's own aliases (tmux 3.x) for verbs we care about, plus safe ones.
ALIASES = {
    "ls": "list-sessions", "lsw": "list-windows", "lsp": "list-panes",
    "lsc": "list-clients", "lscm": "list-commands", "lsk": "list-keys",
    "lsb": "list-buffers", "capturep": "capture-pane", "display": "display-message",
    "displayp": "display-panes", "show": "show-options", "showw": "show-window-options",
    "showenv": "show-environment", "has": "has-session", "new": "new-session",
    "neww": "new-window", "splitw": "split-window", "killp": "kill-pane",
    "killw": "kill-window", "respawnp": "respawn-pane", "respawnw": "respawn-window",
    "send": "send-keys", "setw": "set-window-option", "set": "set-option",
    "attach": "attach-session", "detach": "detach-client", "swapp": "swap-pane",
    "movew": "move-window", "renamew": "rename-window", "rename": "rename-session",
    "pasteb": "paste-buffer", "loadb": "load-buffer", "saveb": "save-buffer",
    "setb": "set-buffer", "run": "run-shell", "if": "if-shell", "bind": "bind-key",
    "source": "source-file", "start": "start-server", "kill-ses": "kill-session",
}

# Verbs that never touch another session's execution — always allowed.
SAFE_VERBS = {
    "list-sessions", "list-windows", "list-panes", "list-clients", "list-commands",
    "list-keys", "list-buffers", "capture-pane", "display-message", "display-panes",
    "show-options", "show-window-options", "show-environment", "show-messages",
    "has-session", "new-session", "start-server", "attach-session", "detach-client",
    "save-buffer", "wait-for", "server-info", "info", "clock-mode", "copy-mode",
    "select-pane", "select-window", "next-window", "previous-window", "last-window",
    "resize-pane", "rename-window", "set-window-option", "choose-tree",
}

# Full canonical verb list for prefix expansion (superset of the two above).
ALL_VERBS = SAFE_VERBS | set(ALIASES.values()) | {
    "kill-session", "kill-server", "kill-pane", "kill-window", "respawn-pane",
    "respawn-window", "send-keys", "paste-buffer", "load-buffer", "set-buffer",
    "pipe-pane", "new-window", "split-window", "set-option", "rename-session",
    "run-shell", "if-shell", "bind-key", "source-file", "swap-pane", "move-window",
    "switch-client", "confirm-before", "command-prompt",
}

SAFE_KEYS = {"enter", "return", "space", "tab", "up", "down", "left", "right", "bspace"}
SHELL_SEPARATORS = {"&&", "||", ";", "|", "&", "\n"}


def tmux_bin() -> str:
    global TMUX_BIN
    if TMUX_BIN is None:
        for cand in ("/usr/local/bin/tmux", "/opt/homebrew/bin/tmux"):
            if os.path.exists(cand):
                TMUX_BIN = cand
                break
        else:
            TMUX_BIN = "tmux"
    return TMUX_BIN


def own_session() -> str:
    if not os.environ.get("TMUX"):
        return ""
    try:
        out = subprocess.run([tmux_bin(), "display-message", "-p", "#S"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def session_runs_claude(name: str) -> bool:
    """True if any pane in `name` is running claude — those are never killable."""
    try:
        out = subprocess.run(
            [tmux_bin(), "list-panes", "-t", name, "-F", "#{pane_current_command}"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return True  # can't tell -> treat as protected (fail closed)
        return any("claude" in ln or "node" in ln for ln in out.stdout.lower().splitlines())
    except Exception:
        return True


def normalize_verb(word: str) -> str:
    w = word.lower()
    if w in ALIASES:
        return ALIASES[w]
    if w in ALL_VERBS:
        return w
    matches = {v for v in ALL_VERBS if v.startswith(w)}
    matches |= {ALIASES[a] for a in ALIASES if a.startswith(w)}
    if len(matches) == 1:
        return matches.pop()
    return w  # ambiguous or unknown — caller fails closed


def target_of(tokens):
    """Extract the -t target in any spelling; returns session name or ''."""
    for i, t in enumerate(tokens):
        val = None
        if t == "-t" and i + 1 < len(tokens):
            val = tokens[i + 1]
        elif t.startswith("-t=") and len(t) > 3:
            val = t[3:]
        elif t.startswith("-t") and len(t) > 2 and not t.startswith("-t-"):
            val = t[2:]
        if val:
            return val.lstrip("=").split(":")[0].split(".")[0]
    return ""


def deny(reason: str) -> None:
    sys.stderr.write(
        f"tmux-peer-guard: BLOCKED — {reason}\n"
        "Cross-session tmux control is restricted: another session may be doing real work, "
        "and instructions to run these commands can be injected via content a session reads.\n"
        "If Zalo genuinely wants this, he runs it in his own terminal. There is no in-band override.\n"
    )
    sys.exit(2)


def check_tmux_segment(tokens, mine: str) -> None:
    """tokens = argv of one tmux invocation (binary already stripped)."""
    # Skip tmux global options (-L socket, -S path, -f file, -2, -u, -C …)
    i = 0
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] in ("-L", "-S", "-f", "-c"):
            i += 2
        else:
            i += 1
    if i >= len(tokens):
        return  # `tmux` alone / `tmux -V`
    # A tmux command sequence: split remaining on ';' tokens, check each part.
    parts, cur = [], []
    for tok in tokens[i:]:
        if tok == ";" or tok == "\\;":
            if cur:
                parts.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        parts.append(cur)

    for part in parts:
        verb = normalize_verb(part[0])
        rest = part[1:]
        target = target_of(rest)
        same_session = bool(target) and target == mine

        if verb == "kill-server":
            deny("`tmux kill-server` tears down every session on the machine")

        if verb in SAFE_VERBS:
            continue

        if verb == "send-keys":
            if not target or same_session:
                continue
            if "-l" in rest:
                continue  # literal text: the sanctioned peer-message path
            keys = [t for t in rest if not t.startswith("-") and t != target]
            if all(k.lower() in SAFE_KEYS for k in keys):
                continue
            deny(f"`send-keys` of control keys {keys} to another session ('{target}')")

        if verb in {"kill-session", "kill-pane", "kill-window", "respawn-pane", "respawn-window"}:
            if not target:
                deny(f"`tmux {verb}` with no -t target acts on the CURRENT session "
                     "(this exact mistake destroyed a live Claude session during an audit)")
            if same_session:
                continue
            if session_runs_claude(target):
                deny(f"`tmux {verb}` targeting '{target}', which is running a Claude session")
            continue  # scratch session — cleanup allowed

        if verb in {"paste-buffer", "pipe-pane", "new-window", "split-window", "set-option",
                    "set-window-option", "rename-session", "swap-pane", "move-window",
                    "switch-client", "run-shell", "if-shell", "bind-key", "source-file",
                    "command-prompt", "confirm-before"}:
            if target and not same_session:
                deny(f"`tmux {verb}` targeting another session ('{target}') can inject or "
                     "alter execution there")
            continue

        if verb not in ALL_VERBS and target and not same_session:
            deny(f"unrecognized tmux verb '{part[0]}' targeting another session ('{target}') "
                 "— refusing rather than guessing")


# `tmux` as an actual command word: start of string or after a separator/wrapper,
# NOT inside quoted prose (a commit message that mentions tmux isn't a tmux call).
TMUX_INVOCATION = re.compile(r"(?:^|[;&|(`]|\$\(|\bsudo\b|\benv\b|\bnohup\b|\bcommand\b|\bxargs\b)\s*"
                             r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:\S*/)?tmux\b")


def scan(command: str, mine: str, depth: int = 0) -> None:
    if depth > 3 or "tmux" not in command:
        return
    try:
        tokens = shlex.split(command, comments=False)
    except ValueError:
        # Unparseable quoting. Only refuse if tmux actually appears in command
        # position — otherwise it's prose (commit messages, echoed text).
        if TMUX_INVOCATION.search(command):
            deny("tmux command with unbalanced quoting — refusing to guess its meaning")
        return

    # After shlex, tmux's own `\;` separator is indistinguishable from a shell
    # `;`. So once a segment is a tmux invocation, following segments are ALSO
    # checked as tmux subcommands (fail closed: a real shell command like
    # `echo hi` has no tmux verb and no target, so it passes harmlessly).
    segment, prev_tmux = [], False
    for tok in tokens:
        if tok in SHELL_SEPARATORS:
            if segment:
                prev_tmux = consider(segment, mine, depth, prev_tmux)
            segment = []
            continue
        segment.append(tok)
    if segment:
        consider(segment, mine, depth, prev_tmux)


def consider(segment, mine: str, depth: int, prev_tmux: bool = False) -> bool:
    """Check one shell segment. Returns True if it was a tmux invocation."""
    # strip env assignments and wrapper commands (env, sudo, nohup, command, xargs…)
    idx = 0
    while idx < len(segment) and (
        re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", segment[idx])
        or os.path.basename(segment[idx]) in {"env", "sudo", "nohup", "command", "xargs", "time", "caffeinate"}
    ):
        idx += 1
    if idx >= len(segment):
        return prev_tmux
    head = os.path.basename(segment[idx])

    if head == "tmux":
        check_tmux_segment(segment[idx + 1:], mine)
        return True

    if prev_tmux:
        check_tmux_segment(segment[idx:], mine)  # continuation of a `\;` sequence

    # nested shell: bash -c "...", sh -c '...', eval '...'
    for tok in segment[idx + 1:]:
        if "tmux" in tok:
            scan(tok, mine, depth + 1)
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if "tmux" not in cmd:
        sys.exit(0)
    scan(cmd, own_session())
    sys.exit(0)


if __name__ == "__main__":
    main()
