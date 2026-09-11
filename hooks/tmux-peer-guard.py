r"""
PreToolUse hook: guard cross-session tmux control (deny-by-default).

Sessions message each other via `tmux send-keys` (see CLAUDE.md "Inter-Session
Messaging"). Every session runs --dangerously-skip-permissions, so an injected
instruction read from a web page, repo file, or PR body would otherwise execute
machine-wide. This hook blocks tmux verbs that can interrupt, kill, or inject
into ANOTHER session.

Design (v3, after a behaviour suite found 4 holes + 1 false block in v2):
  - ALLOW-LIST of read-only/self-scoped verbs; everything else that names a
    target other than your own session is DENIED.
  - Subcommands are normalized through tmux's own alias table AND unambiguous
    prefix expansion (`kill-ses` -> `kill-session`, `killp` -> `kill-pane`).
  - Targets parsed in every spelling: `-t X`, `-tX`, `-t=X`, `sess:win.pane`.
  - `\;` command sequences and shell operators split into segments; every
    segment is checked. Nested `bash -c "..."` strings are scanned recursively.
  - Unparseable tmux invocations fail CLOSED.
  - Killing or respawning ANY session but your own is denied outright, as is
    `kill-server`.
  - There is deliberately NO in-band escape hatch: any token the assistant can
    type is a token injected text can tell it to type. To force a blocked
    action, the owner runs it in their own terminal.

v3 changes (2026-07-25) — both directions, each pinned by /tmp/guard_suite.py:
  - TOKENIZER: v2 used bare `shlex.split`, which leaves `;` glued to the
    preceding word (`hi;`, `Enter;`). Two consequences, one dangerous:
    `echo hi; tmux send-keys -t peer C-c` was ALLOWED (the segment splitter
    never saw a separator, so the C-c was never checked), while the sanctioned
    `send-keys -t peer Enter; sleep 8; capture-pane` was BLOCKED (the whole
    tail was read as one key list). Now tokenized with punctuation_chars=True,
    which splits operators correctly and still respects quoting.
  - KILLS: v2 permitted killing a peer session whose panes weren't "running
    claude", via session_runs_claude(). On this machine
    `#{pane_current_command}` returns a version string, not a process name, so
    that check found nothing to protect and EVERY session was killable
    (kill-session / kill-ses / killp / respawn-pane all passed). The detector
    was load-bearing and provably unreliable, so it is gone: cross-session
    kill/respawn is now unconditionally denied. Cost: a headless helper can no
    longer clean up a scratch session it created — it must be torn down from
    the owner's terminal.

LIMITS (documented honestly): static string analysis cannot see through
variable indirection (`T=tmux; $T ...`), base64/eval obfuscation, or a script
written to disk and executed. This is a guardrail against the realistic
injection path — plain instructions embedded in fetched content — not a sandbox.

v4 (2026-09-11): the ONE sanctioned refresh path, and two laundering shapes.
  - Zalo authorized self service refresh of specific sessions (Telegram,
    2026-09-11: "find a way so you can always refresh that so it doesn't need
    me") after the codex-bare Computer Use app session got stuck twice in one
    morning and only an owner could start a fresh thread or relaunch it. The
    allowlist lives in ~/.claude/config/peer-refresh-allow.json and the only
    script allowed to act on it is ~/.claude/scripts/peer-refresh.sh, which
    reads the same file. This hook now judges that script's invocations:
      ALLOWED  ~/.claude/scripts/peer-refresh.sh <allowlisted session> [flags]
               as the command head of a shell segment (env assignments and the
               usual wrappers such as nohup or caffeinate in front are fine).
      DENIED   the script aimed at any session not in the allowlist; the script
               inside a bash -c / sh -c / eval string; the script run through an
               interpreter (`bash peer-refresh.sh ...`); any other path whose
               basename is peer-refresh.sh; an unparseable command line that
               names it. A bare kill-session on an allowlisted session stays
               DENIED: the script is the path, not the verb.
    The allowlist file is read at a fixed path with no env override, so there
    is still no in-band knob: adding a session is an owner edit in the owner's
    terminal. A mention of the script with no session argument (git add, cat,
    chmod, bash -n) is not an invocation and passes.
  - Subshells and brace groups now split segments: `( tmux kill-session -t x )`,
    `y=$( tmux kill-session -t x )` and `{ tmux kill-session -t x; }` were all
    ALLOWED by v3 because `(`, `)`, `{` and `}` were not separators, so the
    whole group was read as one segment whose head was the paren. Found while
    adding the refresh cases; three tests pin it.
  - QA pass on the same day (qa-agent over the v4 diff) found four more, all
    pinned by tests now:
      * making `(` a separator turned `python3 -c "os.system('tmux kill ...')"`
        from denied into allowed (the quoted command became a segment HEAD and
        heads were never rescanned): quoted blobs in head position are rescanned.
      * `send-keys -l /clear`, `-l /new`, `-l '!cmd'` to a peer were always
        allowed (any `-l` counted as the sanctioned message path): the `-l`
        branch now applies peer-ask.sh's own refusals (a literal starting with
        "/" or "!", or carrying a raw control byte, is denied).
      * a `$( )` inside a quoted argument of a sanctioned head (`--reason`, a
        `-l` message, a `-F` format) was never rescanned: it is now.
      * any unrecognised word in front of tmux laundered it (`exec tmux`,
        `timeout 30 tmux`, `then tmux`, `find -exec tmux`, `xargs -I@ tmux`,
        `sudo -u zalo tmux`): at top level, `tmux` anywhere in a segment is
        checked. Inside quoted blobs the head-only rule stays, so prose that
        mentions a kill mid sentence (a commit message, a peer message) passes.
    Still not seen (static limits): backtick substitution inside quotes, which
    shlex does not split, and anything behind a variable or an eval'd file.
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
# Parens and braces are separators too (v4): a subshell or brace group is just
# commands, and reading `( tmux kill-session -t x )` as one segment headed by
# "(" let the kill through.
SHELL_SEPARATORS = {"&&", "||", ";", "|", "&", "\n", "(", ")", "{", "}"}

# The one sanctioned refresh path (v4). Fixed paths, no env override on purpose.
HOME_DIR = os.path.expanduser("~")
PEER_REFRESH_SCRIPT = os.path.join(HOME_DIR, ".claude", "scripts", "peer-refresh.sh")
PEER_REFRESH_ALLOW = os.path.join(HOME_DIR, ".claude", "config", "peer-refresh-allow.json")
PEER_REFRESH_NAME = "peer-refresh.sh"
INTERPRETERS = {"bash", "sh", "zsh", "dash", "ksh"}
WRAPPERS = {"env", "sudo", "nohup", "command", "xargs", "time", "caffeinate"}


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


def tokenize(command: str):
    """Split a shell command, keeping operators as their OWN tokens.

    Plain shlex.split glues `;` to the preceding word (`hi;`, `Enter;`), which
    hid a whole command from the segment splitter in v2. punctuation_chars
    tokenizes ; & | ( ) < > properly while still honouring quotes.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


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


def refresh_allowlist() -> set:
    """Sessions peer-refresh.sh may act on. Missing or malformed file = none."""
    try:
        with open(PEER_REFRESH_ALLOW) as fh:
            data = json.load(fh)
        sessions = data.get("sessions") or []
        return {s for s in sessions if isinstance(s, str) and s}
    except Exception:
        return set()


def expand_head(tok: str) -> str:
    """`~/x`, `$HOME/x` and `${HOME}/x` spell the same path as /Users/zalo/x."""
    if tok.startswith("~/"):
        return HOME_DIR + tok[1:]
    for pre in ("${HOME}/", "$HOME/"):
        if tok.startswith(pre):
            return HOME_DIR + "/" + tok[len(pre):]
    return tok


def check_refresh_segment(head_tok: str, rest, depth: int) -> None:
    """A shell segment whose head is (some path to) peer-refresh.sh.

    The session is the first argument, always (the script refuses anything
    else). No session argument = not an invocation (cat, git add, chmod,
    bash -n): pass. With a session argument the ONLY allowed shape is the
    canonical script path at depth 0 aimed at an allowlisted session.
    """
    session = rest[0] if rest and not rest[0].startswith("-") else ""
    if not session:
        return
    if depth > 0:
        deny(f"peer-refresh.sh aimed at '{session}' inside a nested shell string "
             "(bash -c, sh -c, eval, an interpreter head, a heredoc); run it directly as the command")
    if expand_head(head_tok) != PEER_REFRESH_SCRIPT:
        deny(f"'{head_tok}' is not the sanctioned refresh script "
             f"({PEER_REFRESH_SCRIPT}); only that path may refresh a session")
    allow = refresh_allowlist()
    if session not in allow:
        deny(f"peer-refresh.sh aimed at '{session}', which is not in "
             f"{PEER_REFRESH_ALLOW} (allowlisted: {sorted(allow) or 'none'}); "
             "adding a session there is an owner edit made in the owner's own terminal")
    # allowlisted session, canonical path, top level: the one sanctioned shape


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
                # Literal text: the sanctioned peer-message path, with the same
                # two refusals peer-ask.sh applies (v4). A literal that starts
                # with "/" is a slash command (/clear, /exit, /new) and one that
                # starts with "!" is a shell escape, both executed by the peer;
                # a raw control byte typed literally is a control key.
                literals = [t for t in rest if not t.startswith("-") and t != target]
                for lit in literals:
                    if lit.startswith("/") or lit.startswith("!"):
                        deny(f"`send-keys -l` of a slash command or shell escape "
                             f"('{lit[:20]}') to another session ('{target}'); only "
                             "~/.claude/scripts/peer-refresh.sh may start a fresh thread there")
                    if any(ord(c) < 32 or c == "\x7f" for c in lit):
                        deny(f"`send-keys -l` of raw control bytes to another session ('{target}')")
                continue
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
            # v2 asked "is that session running claude?" and skipped the kill if
            # not. The probe it relied on is unreliable here (see module header),
            # so every peer was killable. No exceptions now.
            deny(f"`tmux {verb}` targeting another session ('{target}') — a peer may be "
                 "mid-task, and only the owner can tear one down")

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
TMUX_INVOCATION = re.compile(r"(?:^|[;&|(`{]|\$\(|\bsudo\b|\benv\b|\bnohup\b|\bcommand\b|\bxargs\b)\s*"
                             r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:\S*/)?tmux\b")
# Same shape for the refresh script, followed by an argument (a bare mention
# with nothing after it is prose or a file operand, not an invocation).
REFRESH_INVOCATION = re.compile(r"(?:^|[;&|(`{]|\$\(|\bsudo\b|\benv\b|\bnohup\b|\bcommand\b|\bxargs\b|\bcaffeinate\b)\s*"
                                r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:\S*/)?peer-refresh\.sh\s+\S")


def relevant(command: str) -> bool:
    return "tmux" in command or PEER_REFRESH_NAME in command


def scan(command: str, mine: str, depth: int = 0) -> None:
    if depth > 3 or not relevant(command):
        return
    try:
        tokens = tokenize(command)
    except ValueError:
        # Unparseable quoting. Only refuse if tmux (or the refresh script with
        # an argument) actually appears in command position; otherwise it's
        # prose (commit messages, echoed text).
        if TMUX_INVOCATION.search(command):
            deny("tmux command with unbalanced quoting — refusing to guess its meaning")
        if REFRESH_INVOCATION.search(command):
            deny("peer-refresh.sh invocation with unbalanced quoting; refusing to guess its target")
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
        or os.path.basename(segment[idx]) in WRAPPERS
    ):
        idx += 1
    if idx >= len(segment):
        return prev_tmux
    head = os.path.basename(segment[idx])

    def rescan_nested(start: int):
        # nested shell strings: bash -c "...", sh -c '...', eval '...', a $( )
        # inside a quoted argument, python -c "os.system('...')". The head
        # token itself is rescanned when it is a quoted blob (contains
        # whitespace): with "(" a separator, `os.system('tmux ...')` leaves the
        # quoted command as the HEAD of its own segment (v4 QA finding).
        for j in range(start, len(segment)):
            tok = segment[j]
            if relevant(tok) and (j != idx or any(c.isspace() for c in tok)):
                scan(tok, mine, depth + 1)

    if head == "tmux":
        check_tmux_segment(segment[idx + 1:], mine)
        rescan_nested(idx + 1)  # a $( ) hidden in a -l message or a -F format
        return True

    if head == PEER_REFRESH_NAME:
        check_refresh_segment(segment[idx], segment[idx + 1:], depth)
        rescan_nested(idx + 1)  # a $( ) hidden in --reason
        return False

    if head in INTERPRETERS:
        # `bash /path/peer-refresh.sh <session>`: the interpreter is the head,
        # so the script is not "the command"; deny when a session follows it.
        for j in range(idx + 1, len(segment)):
            if os.path.basename(segment[j]) == PEER_REFRESH_NAME:
                check_refresh_segment(segment[j], segment[j + 1:], depth + 1)

    if depth == 0:
        # A top-level segment is a real command line, so `tmux` anywhere in it
        # is an invocation: `exec tmux ...`, `timeout 30 tmux ...`, `then tmux
        # ...`, `find -exec tmux ...`, `xargs -I@ tmux ...` (v3 only looked at
        # the head, so any unrecognised word in front laundered a kill). Inside
        # quoted blobs (depth > 0) the head-only rule stays, so prose that
        # mentions a kill mid sentence is not flagged. Not applied to
        # peer-refresh.sh: a file operand after it (git add, cp, diff) is not
        # a session, and the script refuses a non allowlisted session itself.
        for j in range(idx + 1, len(segment)):
            if os.path.basename(segment[j]) == "tmux":
                check_tmux_segment(segment[j + 1:], mine)
                break

    if prev_tmux:
        check_tmux_segment(segment[idx:], mine)  # continuation of a `\;` sequence

    rescan_nested(idx)
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not relevant(cmd):
        sys.exit(0)
    scan(cmd, own_session())
    sys.exit(0)


if __name__ == "__main__":
    main()
