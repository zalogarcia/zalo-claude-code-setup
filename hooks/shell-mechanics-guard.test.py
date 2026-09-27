#!/usr/bin/env python3
"""Behaviour suite for shell-mechanics-guard.

Run: python3 ~/.claude/hooks/shell-mechanics-guard.test.py
Must be green before the hook is wired into ~/.claude/settings.json: this is a
PreToolUse Bash hook, and a broken one blocks every Bash call on the machine.

The suite tests the hook that sits NEXT TO it (so a worktree copy is tested in
the worktree, and the installed copy in ~/.claude/hooks), never a fixed path.
"""

import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "shell-mechanics-guard.py")
WARN, QUIET, BLOCK = "warn", "quiet", "block"

_spec = importlib.util.spec_from_file_location("shell_mechanics_guard", HOOK)
smg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smg)


def run_raw(command, state_dir, session="s1", payload=None, raw=None):
    """Run the hook as Claude Code does. Returns (returncode, context, stderr)."""
    if raw is None:
        pl = payload if payload is not None else {
            "session_id": session,
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": "/tmp",
        }
        raw = json.dumps(pl)
    p = subprocess.run(
        ["python3", HOOK],
        input=raw,
        capture_output=True,
        text=True,
        env=dict(os.environ, SHELL_MECH_STATE_DIR=state_dir),
    )
    ctx = None
    if p.stdout.strip():
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
    return p.returncode, ctx, p.stderr


def run(command, state_dir, session="s1", payload=None, raw=None):
    """Warn-path helper: the command must be allowed (exit 0)."""
    rc, ctx, err = run_raw(command, state_dir, session, payload, raw)
    assert rc == 0, f"hook must exit 0 here, got {rc}: {err}"
    return ctx


# (label, command, expect, marker-substring or None)
# End to end through the real hook process: exit code, stderr, stdout.
CASES = [
    # --- WARN: lost exit code -------------------------------------------------
    ("$? read after | tail",
     "npm run build 2>&1 | tail -40; echo EXIT=$?", WARN, "PIPESTATUS"),
    ("$? read after | grep in an && chain",
     "cargo test | grep -c FAILED && echo done; EXIT=$?", WARN, "PIPESTATUS"),
    # --- WARN: relative cd ----------------------------------------------------
    ("leading relative cd",
     "cd delta-agents && npm test", WARN, "relative"),
    ("leading cd ..",
     "cd ../packages && ls", WARN, "relative"),
    # --- BLOCK: PIPESTATUS moved from warn to block (always empty under zsh) --
    ("PIPESTATUS after an && chain is now a BLOCK",
     'npm run typecheck && npm run build; echo "EXIT=${PIPESTATUS[0]}"', BLOCK, "pipestatus"),
    ("PIPESTATUS with no && before it is now a BLOCK (empty under zsh either way)",
     "npm run build 2>&1 | tail -5; echo ${PIPESTATUS[0]}", BLOCK, "pipestatus"),
    # --- BLOCK: one end to end case per shape ---------------------------------
    ("echo === separator", "echo ===; ls /tmp", BLOCK, "'==='"),
    ("GNU timeout", "timeout 300 npm test", BLOCK, "alarm shift"),
    ("unquoted glob in --include=", "grep -rn foo --include=*.tsx /tmp", BLOCK, "--include='*.tsx'"),
    ("for over a scalar", 'F="a b"; for x in $F; do echo $x; done', BLOCK, "${=F}"),
    # --- QUIET: correct shapes ------------------------------------------------
    ("canonical capture shape",
     "npm run build > /tmp/b.log 2>&1; echo EXIT=$?; tail -40 /tmp/b.log", QUIET, None),
    ("absolute cd",
     "cd /Users/zalo/dev/delta-agents && npm test", QUIET, None),
    ("tilde cd",
     "cd ~/dev/zalo-os && ls", QUIET, None),
    ("variable cd",
     "cd $HOME/dev && ls", QUIET, None),
    ("command substitution cd",
     'cd "$(git rev-parse --show-toplevel)" && ls', QUIET, None),
    ("plain command",
     "ls -la /tmp", QUIET, None),
    ("$? straight after a non-piped command",
     "npm run build; echo EXIT=$?", QUIET, None),
    ("git -C absolute (the recommended alternative)",
     "git -C /Users/zalo/dev/zalo-os status", QUIET, None),
    ("$pipestatus (zsh) is the working form",
     "npm run build 2>&1 | tail -5; echo ${pipestatus[1]}", QUIET, None),
    # --- EXEMPTIONS -----------------------------------------------------------
    ("pipefail makes $?-after-pipe meaningful",
     "set -o pipefail; npm run build 2>&1 | tail -40; echo EXIT=$?", QUIET, None),
    ("$? inside a quoted string is not shell mechanics",
     "grep -n 'echo EXIT=$?' ~/.claude/QUIRKS.md", QUIET, None),
    ("a pipe inside a quoted pattern is not a pipeline",
     'rg "a \\| tail" /tmp/x.txt; echo hi', QUIET, None),
    ("cd - (return to previous dir) is not a relative path guess",
     "cd -", QUIET, None),
]

# (label, command, expected shape or None). Pure function, no process.
BLOCK_CASES = [
    # --- 1. equals expansion ---------------------------------------------------
    ("echo ===", "echo ===", "equals"),
    ('echo "x" ==== y', 'echo "x" ==== y', "equals"),
    ("separator between commands", 'ls /tmp; echo ""; echo ==; ls /', "equals"),
    ("[ a == b ] (zsh: = not found)", '[ "$a" == "$b" ] && echo same', "equals"),
    ("test a == b", 'test "$x" == y && echo t', "equals"),
    ("inside a command substitution", 'echo "$(echo ===)"', "equals"),
    ("word starting with == and text", "echo ==foo", "equals"),
    ("=~ outside [[ ]]", '[ "$x" =~ y ]', "equals"),
    ("equals after a separator line in a loop", "for f in a b; do echo =====; echo $f; done", "equals"),
    ("assignment value starting with ==", "SEP===; echo $SEP", "equals"),
    ("expr 1 == 1", "expr 1 == 1", "equals"),
    # --- 2. timeout ---------------------------------------------------------------
    ("timeout at start", "timeout 5 curl -s https://x", "timeout"),
    ("after &&", "cd /tmp && timeout 300 npm test", "timeout"),
    ("after ;", "ls; timeout 5 x", "timeout"),
    ("after ||", "x || timeout 5 y", "timeout"),
    ("after |", "echo a | timeout 5 cat", "timeout"),
    ("after (", "(timeout 5 x)", "timeout"),
    ("after $(", 'echo "$(timeout 5 x)"', "timeout"),
    ("after backtick", "echo `timeout 5 x`", "timeout"),
    ("after then", "if true; then timeout 5 x; fi", "timeout"),
    ("after if", "if timeout 5 x; then echo ok; fi", "timeout"),
    ("after do", "for i in 1 2; do timeout 5 x; done", "timeout"),
    ("after else", "if false; then :; else timeout 5 x; fi", "timeout"),
    ("after xargs with options", "ls | xargs -n 1 timeout 5 echo", "timeout"),
    ("after exec", "exec timeout 5 x", "timeout"),
    ("after env with an assignment", "env FOO=1 timeout 5 x", "timeout"),
    ("after nohup", "nohup timeout 60 x > /tmp/o.log 2>&1 &", "timeout"),
    ("after sudo", "sudo timeout 5 x", "timeout"),
    ("after time", "time timeout 5 x", "timeout"),
    ("after command", "command timeout 5 x", "timeout"),
    ("after an env prefix assignment", "FOO=1 timeout 5 x", "timeout"),
    ("gtimeout is absent too", "gtimeout 5 x", "timeout"),
    ("inside a function body", "f() { timeout 5 x; }; f", "timeout"),
    ("after a newline", "echo start\ntimeout 5 x", "timeout"),
    # --- 3. unquoted glob in --option=value ---------------------------------------
    ("--include=*.tsx", "grep -rn foo --include=*.tsx .", "glob_opt"),
    ("--exclude-dir=node_*", "grep -r x --exclude-dir=node_* .", "glob_opt"),
    ("--url=https://a?b", "curl -s --url=https://a?b", "glob_opt"),
    ("second of two --include", "grep -rn x --include='*.ts' --include=*.tsx src", "glob_opt"),
    ("inside $(...)", 'echo "$(grep -rl x --include=*.py .)"', "glob_opt"),
    # --- 4. PIPESTATUS -------------------------------------------------------------
    ("${PIPESTATUS[0]} unquoted", "npm run build | tail -5; echo ${PIPESTATUS[0]}", "pipestatus"),
    ("${PIPESTATUS[0]} in double quotes", 'x | y; echo "EXIT=${PIPESTATUS[0]}"', "pipestatus"),
    ("$PIPESTATUS bare", "x | y; echo $PIPESTATUS", "pipestatus"),
    ('bash -c "..." still expands it in zsh first', 'bash -c "x | y; echo ${PIPESTATUS[0]}"', "pipestatus"),
    (":-$? fallback still reads the FILTER's status", 'x | tail -5; echo "EXIT=${PIPESTATUS[0]:-$?}"', "pipestatus"),
    # --- 5. for over a scalar --------------------------------------------------------
    ("literal multi-word scalar", 'FILES="a.txt b.txt"; for f in $FILES; do echo $f; done', "for_scalar"),
    ("command substitution scalar", 'F=$(ls /tmp); for f in $F; do echo "$f"; done', "for_scalar"),
    ("export of a multi-word scalar", 'export L="x y"; for i in $L; do :; done', "for_scalar"),
    ("${VAR} braces, newline separated", "V='a b'\nfor x in ${V}; do echo $x; done", "for_scalar"),
    ("backtick scalar", "A=`ls`; for f in $A; do echo $f; done", "for_scalar"),
]

ALLOW_CASES = [
    # --- 1. equals near misses ---------------------------------------------------------
    ("single quoted ===", "echo '==='"),
    ("double quoted ===", 'echo "===" ; echo "== done =="'),
    ("escaped ===", "echo \\==="),
    ("[[ a == b ]]", '[[ "$a" == "$b" ]] && echo same'),
    ("[[ ]] with && inside", '[[ $a == b && $c == d ]] && echo both'),
    ("(( a == b ))", "(( 1 == 1 )) && echo arith"),
    ("$(( a == b ))", "echo $(( 1 == 1 ))"),
    ("pip pin", "pip install foo==1.2"),
    ("awk in quotes", "awk '$1 == 2' /tmp/x"),
    ("a==b mid word", "echo a==b"),
    ("cut -d=", "cut -d= -f2 /tmp/x"),
    ("bare = word", "tr = : < /tmp/x"),
    ("heredoc body", "cat <<EOF\n===\nEOF"),
    ("quoted heredoc body", "cat > /tmp/x.md <<'EOF'\n=== heading ===\nEOF\necho ok"),
    ("bash -c single quoted", "bash -c 'echo ==='"),
    ("comment", "ls # === separator ==="),
    ("zsh =(...) process substitution", "diff =(ls /tmp) =(ls /)"),
    ("=cmd that exists", "echo =ls"),
    ("jq filter", "jq '.a == 1' /tmp/x.json"),
    ("python -c in double quotes", 'python3 -c "print(1 == 1)"'),
    ("printf format in quotes", "printf '%s\\n' '=== x ==='"),
    ("assignment of a single =", "SEP==; echo $SEP"),
    ("while [[ == ]]", 'while [[ "$s" == run ]]; do s=done; done'),
    ("! [[ == ]]", '! [[ "$a" == b ]] && echo differ'),
    ("after && then [[ == ]]", 'ls && [[ "$a" == b ]]&&echo same'),
    ("commit message heredoc inside $(...)",
     'git commit -m "$(cat <<\'EOF\'\nfix: echo === and timeout 5 x and ${PIPESTATUS[0]}\nEOF\n)"'),
    ("[[ == ]] inside a function body (replay FP)",
     'RC() { if [[ "$RURL" == rediss://* ]]; then echo tls; fi; }; RC'),
    ("zsh (..) pattern word after an argument (replay FP)",
     "grep -n \\\"if (low === 'on' || low === 'off')\\\" /tmp/x"),
    # --- 2. timeout near misses ------------------------------------------------------
    ("--timeout", "curl --timeout 5 https://x"),
    ("timeout= env prefix", "timeout=5 python3 x.py"),
    ("timeout as an argument", "grep -rn timeout src/"),
    ("timeout inside double quotes", 'echo "timeout 5 x"'),
    ("timeout inside single quotes", "echo 'timeout 5 x'"),
    ("bash -c single quoted", "bash -c 'timeout 5 x'"),
    ("timeout function defined", "timeout() { perl -e 'alarm shift; exec @ARGV' \"$@\"; }; timeout 5 x"),
    ("function keyword form", "function timeout { perl -e 'alarm shift; exec @ARGV' \"$@\"; }; timeout 5 x"),
    ("heredoc body", "cat <<EOF\ntimeout 5 x\nEOF"),
    ("comment", "ls # timeout 5 x"),
    ("--timeout=5", "node x.js --timeout=5"),
    ("commit message", 'git commit -m "add timeout handling"'),
    ("case pattern", "case $e in timeout) echo t;; esac"),
    ("perl alarm rewrite", "perl -e 'alarm shift; exec @ARGV' 300 npm test"),
    ("existence probe first (replay)",
     "(command -v gtimeout >/dev/null && gtimeout 280 node run.cjs || node run.cjs)"),
    ("perl fallback already present (replay)",
     "(gtimeout 420 gh pr checks 277 --watch || perl -e 'alarm 420; exec @ARGV' gh pr checks 277 --watch)"),
    ("command -v timeout is only a question", "command -v timeout gtimeout gsed"),
    ("variable named timeout", "echo $timeout ${timeout}"),
    # --- 3. glob near misses -----------------------------------------------------------
    ("single quoted --include", "grep -rn foo --include='*.tsx' ."),
    ("double quoted --include", 'grep -rn foo --include="*.tsx" .'),
    ("escaped star", "grep -rn foo --include=\\*.tsx ."),
    ("noglob wrapper", "noglob grep -rn foo --include=*.py ."),
    ("setopt nonomatch", "setopt nonomatch; grep -rn foo --include=*.py ."),
    ("curl single quoted URL", "curl 'https://a?b'"),
    ("curl double quoted URL", 'curl "https://a?b"'),
    ("bash -c single quoted", "bash -c 'grep -r x --include=*.py .'"),
    ("heredoc body", "cat <<'EOF'\ngrep --include=*.py x\nEOF"),
    ("case pattern", 'case "$1" in --include=*) echo inc;; esac'),
    ("[[ ]] pattern", '[[ $x == --include=* ]] && echo m'),
    ("$? in an option value", "echo --status=$?"),
    ("${#arr[*]} in an option value", "echo --n=${#arr[*]}"),
    ("no glob in the value", "git log --since=2.weeks --format=%h"),
    # --- 4. PIPESTATUS near misses -----------------------------------------------------
    ("single quoted", "echo '${PIPESTATUS[0]}'"),
    ("grep for the word", "grep -rn PIPESTATUS ."),
    ("grep for the expansion, single quoted", "grep -n '\\$PIPESTATUS' /tmp/x"),
    ("bash -c single quoted", "bash -c 'x | y; echo ${PIPESTATUS[0]}'"),
    ("script written through a quoted heredoc", "cat > /tmp/x.sh <<'EOF'\nx | y\necho ${PIPESTATUS[0]}\nEOF"),
    ("unquoted heredoc body", "cat <<EOF\n$PIPESTATUS\nEOF"),
    ("<<- heredoc body", "cat <<-EOF\n\techo ${PIPESTATUS[0]}\n\tEOF\necho done"),
    ("$pipestatus lowercase", "x | y; echo $pipestatus"),
    ("comment", "ls # echo ${PIPESTATUS[0]}"),
    ("escaped in double quotes", 'echo "echo \\${PIPESTATUS[0]}" >> /tmp/s.sh'),
    ("$'...' string", "echo $'${PIPESTATUS[0]}'"),
    ("portable fallback to $pipestatus (replay)",
     'x | y; echo "rc=${PIPESTATUS[0]:-${pipestatus[1]}}"'),
    # --- 5. for near misses ------------------------------------------------------------
    ("array", "VAR=(a b); for x in $VAR; do echo $x; done"),
    ("${=VAR}", 'VAR="a b"; for x in ${=VAR}; do echo $x; done'),
    ("loop over $(...) directly", "for x in $(ls /tmp); do echo $x; done"),
    ("quoted $VAR is deliberate", 'VAR="a b"; for x in "$VAR"; do echo $x; done'),
    ("single word scalar", "F=/tmp/x.log; for f in $F; do echo $f; done"),
    ("not assigned in this command", "for x in $UNSET_HERE; do echo $x; done"),
    ("setopt shwordsplit", 'setopt shwordsplit; V="a b"; for x in $V; do echo $x; done'),
    ("bash -c single quoted", "bash -c 'V=\"a b\"; for x in $V; do echo $x; done'"),
    ("heredoc body", "cat <<'EOF'\nV=\"a b\"; for x in $V; do echo; done\nEOF"),
    ("VAR=value assignment alone", 'VAR="a b c"; echo "$VAR"'),
    ("env prefix, not a shell variable", 'VAR="a b" env; for x in $VAR; do echo; done'),
    ("reassigned to an array before the loop", 'V="a b"; V=(a b); for x in $V; do echo; done'),
    ("one-line substitution (| head -1)", "F=$(ls -t /tmp/*.log | head -1); for f in $F; do echo $f; done"),
    # QA 2026-09-27 round 1: false blocks found in the replay
    ("several single-value vars in one list (replay FP)",
     "IPH=$(cat /tmp/a.id); IPD=$(cat /tmp/b.id); for S in $IPH $IPD; do echo $S; done"),
    ("one-word substitution: date", "START=$(date +%s); for t in $START; do echo $t; done"),
    ("one-word substitution: git rev-parse", "SHA=$(git rev-parse HEAD); for s in $SHA; do git show --stat $s; done"),
    ("one-word substitution: cat of an .id file", "ID=$(cat /tmp/sim.id); for d in $ID; do echo $d; done"),
    ("one-word substitution: basename", 'B=$(basename "$f"); for x in $B; do echo $x; done'),
    ("=[ is literal in zsh", "echo =["),
    # --- 6. sed N,+M: BSD sed on this Mac ACCEPTS it (probed 2026-09-27) ---------------
    ("sed -n N,+Mp works on macOS 26 sed", "sed -n '10,+5p' /tmp/x"),
    ("sed -n with a computed start", "sed -n \"$(grep -n foo /tmp/x | head -1 | cut -d: -f1),+30p\" /tmp/x"),
    # --- parse failures fail open ------------------------------------------------------
    ("unterminated double quote", 'echo === "unterminated'),
    ("unterminated single quote", "timeout 5 x 'unterminated"),
    ("unterminated substitution", "echo $(timeout 5 x"),
    ("empty", ""),
    ("whitespace", "   \n  "),
]


def _check_pure(passed, failed):
    for label, cmd, shape in BLOCK_CASES:
        got = smg.find_block(cmd)
        got_shape = got[0] if got else None
        if got_shape == shape:
            passed += 1
            print(f"PASS | block {shape}: {label}")
        else:
            failed += 1
            print(f"FAIL | block {shape}: {label} (got {got_shape!r}) :: {cmd!r}")
    for label, cmd in ALLOW_CASES:
        got = smg.find_block(cmd)
        if got is None:
            passed += 1
            print(f"PASS | allow: {label}")
        else:
            failed += 1
            print(f"FAIL | allow: {label} (got {got!r}) :: {cmd!r}")
    return passed, failed


def _check_messages(passed, failed):
    """Every block message names the rewrite that works here."""
    need = {
        "equals": ["'==='", "[[ ]]"],
        "timeout": ["perl -e 'alarm shift; exec @ARGV or die", "142", "gtimeout"],
        "glob_opt": ["--include='*.tsx'", "no matches found"],
        "pipestatus": ["$pipestatus", "echo EXIT=$?"],
        "for_scalar": ["${=", "array"],
    }
    samples = {
        "equals": "echo ===",
        "timeout": "timeout 5 x",
        "glob_opt": "grep -rn foo --include=*.tsx .",
        "pipestatus": "x | y; echo ${PIPESTATUS[0]}",
        "for_scalar": 'F="a b"; for x in $F; do echo; done',
    }
    for shape, cmd in samples.items():
        got = smg.find_block(cmd)
        msg = smg.block_message(got) if got else ""
        missing = [n for n in need[shape] if n not in msg]
        bad_dash = any(ch in msg for ch in ("\u2014", "\u2013"))
        if got and not missing and not bad_dash:
            passed += 1
            print(f"PASS | message for {shape} names its rewrite")
        else:
            failed += 1
            print(f"FAIL | message for {shape}: missing {missing}, dash={bad_dash}")
    return passed, failed


def _check_perf(passed, failed):
    """QA 2026-09-27 round 1: 20,000 `setopt` words took 63 s (a lazy regex
    scanned to the end of the line from every one). Bounded now."""
    import time
    for label, cmd in (("20k setopt words then a glob option", "setopt " * 20000 + " --x=*"),
                       ("20k set -o words", "set -o " * 20000 + " --x=*"),
                       ("20k unsetopt words then ==", "unsetopt " * 20000 + " echo =="),
                       ("20k for-in words", "for x in " * 20000 + "$y")):
        t = time.perf_counter()
        smg.find_blocks(cmd)
        dt = time.perf_counter() - t
        if dt < 2.0:
            passed += 1
            print(f"PASS | perf: {label} in {dt:.2f}s")
        else:
            failed += 1
            print(f"FAIL | perf: {label} took {dt:.2f}s")
    return passed, failed


def _check_fuzz(passed, failed):
    """find_block never raises, whatever it is fed."""
    rnd = random.Random(1234)
    alphabet = list("ab =;&|()$`'\"\\\n#<>{}[]*?-~+") + ["timeout", "PIPESTATUS", "for x in ", "<<EOF", "$(", "${", "==="]
    errors = 0
    for _ in range(3000):
        s = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40)))
        try:
            smg.find_block(s)
        except Exception as e:  # noqa: BLE001
            errors += 1
            if errors <= 3:
                print(f"     raised {e!r} on {s!r}")
    if errors == 0:
        passed += 1
        print("PASS | find_block never raises on 3000 random inputs")
    else:
        failed += 1
        print(f"FAIL | find_block raised on {errors} random inputs")
    return passed, failed


def main():
    passed = failed = 0
    dirs = []

    for label, cmd, expect, marker in CASES:
        d = tempfile.mkdtemp(prefix="shellmech-")
        dirs.append(d)
        rc, ctx, err = run_raw(cmd, d)
        if expect == BLOCK:
            ok = rc == 2 and ctx is None and marker in err
        elif expect == WARN:
            ok = rc == 0 and ctx is not None and (marker is None or marker in ctx)
        else:
            ok = rc == 0 and ctx is None and not err.strip()
        if ok:
            passed += 1
            print(f"PASS | {label}")
        else:
            failed += 1
            print(f"FAIL | {label} (expected {expect}, got rc={rc} ctx={ctx!r} err={err!r})")

    # once per class per session
    d = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d)
    first = run("cd delta-agents && npm test", d)
    second = run("cd other-repo && npm test", d)
    third = run("npm run build 2>&1 | tail -5; echo EXIT=$?", d)
    for label, cond in (
        ("first relative cd warns", first is not None),
        ("second relative cd is silent (once per session)", second is None),
        ("a DIFFERENT class still warns in the same session", third is not None),
    ):
        if cond:
            passed += 1
            print(f"PASS | {label}")
        else:
            failed += 1
            print(f"FAIL | {label}")

    # a different session gets its own budget
    d2 = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d2)
    run("cd delta-agents && npm test", d2, session="s1")
    other = run("cd delta-agents && npm test", d2, session="s2")
    if other is not None:
        passed += 1
        print("PASS | a different session warns independently")
    else:
        failed += 1
        print("FAIL | a different session warns independently")

    # block and warn never both fire, and a block does not spend the warn budget
    d4 = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d4)
    rc, ctx, err = run_raw("cd rel && timeout 5 npm test", d4)
    ok_block = rc == 2 and ctx is None and "timeout" in err
    later = run("cd rel && npm test", d4)
    for label, cond in (
        ("block + warn-worthy command: exit 2, stderr only, no warn JSON", ok_block),
        ("the blocked command did not spend the relative-cd warn", later is not None),
    ):
        if cond:
            passed += 1
            print(f"PASS | {label}")
        else:
            failed += 1
            print(f"FAIL | {label} (rc={rc} ctx={ctx!r} err={err!r} later={later!r})")

    # blocks are not rate limited: the same shape blocks every time
    d5 = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d5)
    rcs = [run_raw("echo ===", d5)[0] for _ in range(2)]
    if rcs == [2, 2]:
        passed += 1
        print("PASS | a block fires on every call, not once per session")
    else:
        failed += 1
        print(f"FAIL | a block fires on every call (got {rcs})")

    passed, failed = _check_pure(passed, failed)
    passed, failed = _check_messages(passed, failed)
    passed, failed = _check_perf(passed, failed)
    passed, failed = _check_fuzz(passed, failed)

    # --- MALFORMED input: must exit 0 and stay silent -------------------------
    d3 = tempfile.mkdtemp(prefix="shellmech-"); dirs.append(d3)
    malformed = [
        ("unparseable JSON", None, '{"broken":'),
        ("empty stdin", None, ""),
        ("missing tool_input", {"tool_name": "Bash", "session_id": "s"}, None),
        ("tool_input is null", {"tool_name": "Bash", "tool_input": None}, None),
        ("command is a dict", {"tool_name": "Bash", "tool_input": {"command": {"a": 1}}}, None),
        ("command is a list", {"tool_name": "Bash", "tool_input": {"command": ["cd x"]}}, None),
        ("no tool_name", {"tool_input": {"command": "cd x && ls"}}, None),
        ("wrong tool", {"tool_name": "Read", "tool_input": {"file_path": "/x"}}, None),
        ("top-level list", None, "[1,2,3]"),
        ("session_id is a dict", {"session_id": {"a": 1}, "tool_name": "Bash",
                                  "tool_input": {"command": "cd rel && ls"}}, None),
        ("blockable command under the wrong tool", {"tool_name": "Read",
                                                   "tool_input": {"command": "echo ==="}}, None),
    ]
    for label, pl, raw in malformed:
        try:
            got = run(None, d3, payload=pl, raw=raw)
        except AssertionError as e:
            print(f"FAIL | malformed: {label} ({e})")
            failed += 1
            continue
        # session_id-is-a-dict is a real command and MAY warn; it must not crash.
        if label == "session_id is a dict":
            passed += 1
            print(f"PASS | malformed: {label} (exit 0, no crash)")
        elif got is None:
            passed += 1
            print(f"PASS | malformed: {label}")
        else:
            failed += 1
            print(f"FAIL | malformed: {label}: expected silence, got {got!r}")

    # unwritable state dir must not crash or block
    try:
        run("cd rel && ls", "/proc/nonexistent-nope")
        passed += 1
        print("PASS | unwritable state dir still exits 0")
    except AssertionError as e:
        failed += 1
        print(f"FAIL | unwritable state dir ({e})")

    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)

    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
