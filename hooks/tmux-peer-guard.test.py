"""Behaviour suite for tmux-peer-guard. Run: python3 ~/.claude/hooks/tmux-peer-guard.test.py

The refresh cases (v4) read the REAL allowlist at
~/.claude/config/peer-refresh-allow.json on purpose: there is no env override
in the hook, so the suite proves the file that is actually consulted.
"""
import json
import subprocess
import sys

HOOK = "/Users/zalo/.claude/hooks/tmux-peer-guard.py"
T = "tmux"  # kept out of literals so this file isn't itself flagged
R = "/Users/zalo/.claude/scripts/peer-refresh.sh"  # the one sanctioned refresh path

# (label, command, expected)  expected: "allow" | "deny"
CASES = [
    # --- sanctioned peer messaging: must ALLOW ---
    ("literal peer message", T + " send-keys -t zalo-ads -l 'hello peer'", "allow"),
    ("bare Enter (protocol step 2)", T + " send-keys -t zalo-ads Enter", "allow"),
    ("Enter + chained sleep/capture", T + " send-keys -t zalo-ads Enter; sleep 8; " + T + " capture-pane -t zalo-ads -p", "allow"),
    ("list sessions", T + " ls", "allow"),
    ("capture peer pane", T + " capture-pane -t zalo-ads -p -S -60", "allow"),
    ("self-targeted C-c", T + " send-keys -t SELF C-c", "allow"),

    # --- must DENY ---
    ("Ctrl-C to peer", T + " send-keys -t delta-agents C-c", "deny"),
    ("/clear to peer", T + " send-keys -t bare /clear Enter", "deny"),
    ("kill peer session", T + " kill-session -t operator-base", "deny"),
    ("kill via prefix alias", T + " kill-ses -t zalo-ads", "deny"),
    ("kill via killp alias", T + " killp -t zalo-ads", "deny"),
    ("attached-arg form", T + " send-keys -tbare C-c", "deny"),
    ("equals form", T + " send-keys -t=bare C-c", "deny"),
    ("bash -c wrapper", 'bash -c "' + T + ' send-keys -t bare C-c"', "deny"),
    ("after shell separator", "echo hi; " + T + " send-keys -t bare C-c", "deny"),
    ("after && separator", "true && " + T + " send-keys -t bare C-c", "deny"),
    ("kill-server", T + " kill-server", "deny"),
    ("tmux \\; sequence laundering", T + " send-keys -t bare -l text \\; send-keys -t bare C-c", "deny"),
    ("pipe-pane injection", T + " pipe-pane -t bare 'cat > /tmp/x'", "deny"),
    ("paste-buffer injection", T + " paste-buffer -t bare", "deny"),
    ("respawn peer pane", T + " respawn-pane -k -t bare", "deny"),
    ("kill with no target", T + " kill-session", "deny"),
    ("C-c chained after Enter", T + " send-keys -t bare Enter; " + T + " send-keys -t bare C-c", "deny"),

    # --- v4: subshell and brace-group laundering (were ALLOWED by v3) ---
    ("subshell laundering", "( " + T + " kill-session -t bare )", "deny"),
    ("command substitution laundering", "x=$( " + T + " kill-session -t bare )", "deny"),
    ("brace group laundering", "{ " + T + " kill-session -t bare; }", "deny"),

    # --- v4: the sanctioned refresh path (allowlist: codex-bare) ---
    ("refresh: allowlisted session via the script", R + " codex-bare", "allow"),
    ("refresh: allowlisted, flags and a quoted reason", R + " codex-bare --force-thread --reason 'outreach recon'", "allow"),
    ("refresh: tilde path", "~/.claude/scripts/peer-refresh.sh codex-bare --dry-run", "allow"),
    ("refresh: $HOME path", "$HOME/.claude/scripts/peer-refresh.sh codex-bare", "allow"),
    ("refresh: followed by an rc check", R + " codex-bare --force-thread; echo rc=$?", "allow"),
    ("refresh: nohup wrapper (stripped like for tmux)", "nohup " + R + " codex-bare", "allow"),
    ("refresh: subshell is still the script as head", "( " + R + " codex-bare )", "allow"),
    ("refresh: mentioned with no session (git add)", "git add scripts/peer-refresh.sh scripts/peer-refresh.test.sh", "allow"),
    ("refresh: cat the script", "cat " + R, "allow"),
    ("refresh: bash -n syntax check", "bash -n " + R, "allow"),
    ("refresh: chmod", "chmod +x " + R, "allow"),
    ("refresh: prose mention with unbalanced quote, no argument", "git commit -m \"docs: mention peer-refresh.sh\" it's", "allow"),

    # --- v4: everything else about refreshing stays DENIED ---
    ("refresh: non allowlisted session", R + " delta-agents", "deny"),
    ("refresh: non allowlisted with flags", R + " zalo-os --force-thread --reason 'x'", "deny"),
    ("refresh: bash -c wrapper", 'bash -c "' + R + ' codex-bare"', "deny"),
    ("refresh: interpreter as the head", "bash " + R + " codex-bare", "deny"),
    ("refresh: other path with the same basename", "/tmp/peer-refresh.sh codex-bare", "deny"),
    ("refresh: bare name resolved via PATH", "peer-refresh.sh codex-bare", "deny"),
    ("refresh: unbalanced quoting with a target", R + " codex-bare --reason \"it's", "deny"),
    ("bare kill on the allowlisted session", T + " kill-session -t codex-bare", "deny"),
    ("bare exact-match kill on the allowlisted session", T + " kill-session -t =codex-bare", "deny"),
    ("respawn on the allowlisted session", T + " respawn-pane -k -t codex-bare", "deny"),
    ("/new typed straight at the allowlisted peer", T + " send-keys -t codex-bare /new Enter", "deny"),

    # --- v4 QA pass: shapes the first cut of v4 let through ---
    ("python one-liner os.system kill (v4 regression)", "python3 -c \"import os; os.system('" + T + " kill-session -t zalo-os')\"", "deny"),
    ("node one-liner execSync C-c (v4 regression)", "node -e \"require('child_process').execSync('" + T + " send-keys -t zalo-os C-c')\"", "deny"),
    ("-l /clear then Enter to a peer", T + " send-keys -t zalo-os -l /clear; " + T + " send-keys -t zalo-os Enter", "deny"),
    ("-l /new typed at the allowlisted peer", T + " send-keys -t codex-bare -l -- /new", "deny"),
    ("-l shell escape to a peer", T + " send-keys -t zalo-os -l '!rm -rf /tmp/x'", "deny"),
    ("-l raw control byte to a peer", T + " send-keys -t zalo-os -l \"$(printf 'x')\x03\"", "deny"),
    ("$( ) hidden in --reason", R + " codex-bare --reason \"$(" + T + " kill-session -t zalo-os)\"", "deny"),
    ("$( ) hidden in a -l message", T + " send-keys -t zalo-os -l \"[from m] $(" + T + " kill-session -t delta-agents)\"", "deny"),
    ("exec in front of tmux", "exec " + T + " kill-session -t bare", "deny"),
    ("timeout in front of tmux", "timeout 30 " + T + " send-keys -t zalo-os C-c", "deny"),
    ("if/then body", "if true; then " + T + " kill-session -t bare; fi", "deny"),
    ("find -exec", "find /tmp -maxdepth 0 -exec " + T + " kill-session -t bare \\;", "deny"),
    ("xargs -I@", "echo bare | xargs -I@ " + T + " kill-session -t @", "deny"),
    ("sudo -u wrapper with an option", "sudo -u zalo " + T + " kill-session -t bare", "deny"),

    # --- v4 QA pass: sanctioned and harmless shapes that must stay allowed ---
    ("-l protocol message with a path inside", T + " send-keys -t zalo-os -l '[from m] check /tmp/x when you can'", "allow"),
    ("-l message mentioning a kill mid sentence", T + " send-keys -t zalo-os -l '[from m] fyi someone ran " + T + " kill-session -t bare earlier'", "allow"),
    ("commit message mentioning a kill", "git commit -m 'guard: handle " + T + " kill-session -t x laundering'", "allow"),
    ("who am I (TMUX guard then display-message)", "[ -n \"$TMUX\" ] && " + T + " display-message -p '#S'", "allow"),
    ("ls -F with a brace format", T + " ls -F '#{session_name} #{session_attached}'", "allow"),
    ("cat the tmux binary path", "cat /usr/local/bin/" + T, "allow"),
    ("grep for tmux in a file", "grep " + T + " /Users/zalo/.claude/CLAUDE.md", "allow"),
    ("subshell around a safe verb", "( " + T + " ls )", "allow"),
]


def run(cmd, own):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    env_cmd = ["python3", HOOK]
    p = subprocess.run(env_cmd, input=payload, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin", "TMUX": own} if own else
                           {"PATH": "/usr/bin:/bin:/usr/local/bin"})
    return "allow" if p.returncode == 0 else "deny"


def main():
    fails = 0
    for label, cmd, expected in CASES:
        # "self-targeted" cases can't be simulated headless (own_session()=="" ),
        # so a headless run treats every target as a peer. Skip that one case.
        if "SELF" in cmd:
            print(f"SKIP  | {label} (needs a real tmux session to simulate)")
            continue
        got = run(cmd, None)
        ok = got == expected
        if not ok:
            fails += 1
        print(f"{'PASS ' if ok else 'FAIL '}| expected {expected:5} got {got:5} | {label}")
    print(f"\n{len(CASES)-1-fails}/{len(CASES)-1} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
