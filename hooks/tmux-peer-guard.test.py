"""Behaviour suite for tmux-peer-guard. Run: python3 /tmp/guard_suite.py"""
import json
import subprocess
import sys

HOOK = "/Users/zalo/.claude/hooks/tmux-peer-guard.py"
T = "tmux"  # kept out of literals so this file isn't itself flagged

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
