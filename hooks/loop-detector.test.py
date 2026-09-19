"""Behaviour suite for loop-detector. Run: python3 ~/.claude/hooks/loop-detector.test.py

Fixtures mirror real PostToolUse/PreToolUse payloads captured from Claude Code
CLI 2.1.220 (state/loop-detector/payload-samples.jsonl). Key empirical facts
encoded here: PostToolUse fires only on SUCCESS (no exit-code field; failures
produce no event), so failures are inferred as Pre attempts with no Post
success in between, and nudges ride hookSpecificOutput.additionalContext.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = os.path.expanduser("~/.claude/hooks/loop-detector.py")
SESSION = "test-session-0000"

passed = 0
failed = 0


def run_hook(payload, state_dir, raw=None):
    data = raw if raw is not None else json.dumps(payload)
    env = dict(os.environ, LOOP_DETECTOR_STATE_DIR=state_dir)
    p = subprocess.run(
        ["python3", HOOK], input=data, capture_output=True, text=True, env=env
    )
    return p.returncode, p.stdout, p.stderr


def pre_bash(command):
    return {
        "session_id": SESSION,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": "/tmp",
    }


def post_bash(command, interrupted=False, rci=None):
    resp = {
        "stdout": "ok",
        "stderr": "",
        "interrupted": interrupted,
        "isImage": False,
        "noOutputExpected": False,
    }
    if rci:
        resp["returnCodeInterpretation"] = rci
    return {
        "session_id": SESSION,
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": resp,
        "cwd": "/tmp",
    }


def post_edit(file_path, tool="Edit"):
    return {
        "session_id": SESSION,
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"},
        "tool_response": {"filePath": file_path, "userModified": False},
        "cwd": "/tmp",
    }


def drive(events, state_dir):
    """Feed a payload sequence; return list of (rc, stdout, stderr)."""
    return [run_hook(e, state_dir) for e in events]


def nudge_of(result):
    rc, out, err = result
    if not out.strip():
        return None
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS | {label}")
    else:
        failed += 1
        print(f"FAIL | {label}")


def fresh_dir():
    return tempfile.mkdtemp(prefix="loop-detector-test-")


def main():
    start = time.time()
    dirs = []

    # 1. Three same-shape failures (rewritten args, same head+paths) -> the
    #    nudge is injected at the NEXT attempt of that shape, via the
    #    PreToolUse allow+additionalContext rail, and only once.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash("python3 /tmp/fix.py --attempt 1"),
            pre_bash("python3 /tmp/fix.py --attempt 2 --verbose"),
            pre_bash("python3 /tmp/fix.py --retry --attempt 3"),
            pre_bash("python3 /tmp/fix.py --attempt 4"),
        ],
        d,
    )
    check("1a: silent during first 3 attempts", all(nudge_of(r) is None for r in results[:3]))
    n = nudge_of(results[3])
    check("1b: fires at 4th attempt (3 known failures)", n is not None and "failed 3 consecutive times" in n)
    check("1c: cites the 3+ Fixes Rule", n is not None and "3+ Fixes Rule" in n)
    out_json = json.loads(results[3][1])["hookSpecificOutput"]
    check(
        "1d: correct rail — PreToolUse allow + additionalContext",
        out_json.get("hookEventName") == "PreToolUse"
        and out_json.get("permissionDecision") == "allow",
    )
    check("1e: exit 0 on every call", all(r[0] == 0 for r in results))

    # 2. Success of the shape resets -> 2 more failures stay silent.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash("python3 /tmp/fix.py --a"),
            pre_bash("python3 /tmp/fix.py --b"),
            pre_bash("python3 /tmp/fix.py --c"),
            post_bash("python3 /tmp/fix.py --c"),  # success resets
            pre_bash("python3 /tmp/fix.py --d"),
            pre_bash("python3 /tmp/fix.py --e"),
        ],
        d,
    )
    check("2: success resets the counter", all(nudge_of(r) is None for r in results))

    # 3. Three failures of three DIFFERENT shapes -> no fire.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash("python3 /tmp/alpha.py"),
            pre_bash("node /tmp/beta.js"),
            pre_bash("sh /tmp/gamma.sh"),
            pre_bash("python3 /tmp/alpha.py"),
            pre_bash("node /tmp/beta.js"),
            pre_bash("sh /tmp/gamma.sh"),
        ],
        d,
    )
    check("3: different shapes never cross-count", all(nudge_of(r) is None for r in results))

    # 4. grep exit 1 (exploration) -> excluded head, never counted.
    d = fresh_dir(); dirs.append(d)
    results = drive([pre_bash("grep needle /tmp/haystack.txt")] * 5, d)
    check("4: excluded heads (grep) never fire", all(nudge_of(r) is None for r in results))

    # 5. curl against the same URL failing twice -> 2-Strike nudge at the
    #    3rd (rewritten) attempt.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash("curl -sf https://api.example.com/v1/things"),
            pre_bash("curl -s -X POST https://api.example.com/v1/things"),
            pre_bash("curl -v https://api.example.com/v1/things"),
        ],
        d,
    )
    check("5a: silent during first 2 attempts", all(nudge_of(r) is None for r in results[:2]))
    n = nudge_of(results[2])
    check("5b: 2-Strike nudge on 3rd attempt", n is not None and "2-Strike Probe Rule" in n and "ground-truth probe" in n)

    # 6. Edit spiral: 4 edits same file -> fires on the 4th (PostToolUse
    #    rail); a passing verification command between resets all counters.
    d = fresh_dir(); dirs.append(d)
    results = drive([post_edit("/tmp/app/logic.ts")] * 4, d)
    check("6a: silent during first 3 edits", all(nudge_of(r) is None for r in results[:3]))
    n = nudge_of(results[3])
    check("6b: fires on 4th unverified edit", n is not None and "edited 4 times" in n)
    check(
        "6c: correct rail — PostToolUse additionalContext",
        json.loads(results[3][1])["hookSpecificOutput"]["hookEventName"] == "PostToolUse",
    )
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            post_edit("/tmp/app/logic.ts"),
            post_edit("/tmp/app/logic.ts"),
            post_edit("/tmp/app/logic.ts"),
            post_bash("npm test"),  # passing verification resets ALL edit counters
            post_edit("/tmp/app/logic.ts"),
        ],
        d,
    )
    check("6d: passing npm test between edits resets", all(nudge_of(r) is None for r in results))

    # 7. Markdown files are exempt.
    d = fresh_dir(); dirs.append(d)
    results = drive([post_edit("/tmp/docs/PLAN.md", tool="Write")] * 6, d)
    check("7: .md edits never fire", all(nudge_of(r) is None for r in results))

    # 8. Cooldown: after firing at 3 failures, 4th/5th are silent, 6th
    #    escalates.
    d = fresh_dir(); dirs.append(d)
    results = drive([pre_bash(f"python3 /tmp/fix.py --n {i}") for i in range(7)], d)
    fired = [i for i, r in enumerate(results) if nudge_of(r)]
    check("8a: fires exactly at attempts 4 and 7", fired == [3, 6])
    n = nudge_of(results[6])
    check("8b: re-fire is escalated with the running count", n is not None and "STILL" in n and "6" in n)

    # 9. Malformed / empty / field-less stdin -> exit 0, no output.
    d = fresh_dir(); dirs.append(d)
    cases = [
        run_hook(None, d, raw="this is not json {"),
        run_hook(None, d, raw=""),
        run_hook(None, d, raw="   \n"),
        run_hook({}, d),
        run_hook({"tool_name": "Bash"}, d),
        run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, d),
    ]
    check("9: garbage in -> exit 0, silent", all(rc == 0 and not out.strip() for rc, out, _ in cases))

    # 10. Unknown tool names and events -> exit 0, silent.
    d = fresh_dir(); dirs.append(d)
    cases = [
        run_hook({"session_id": SESSION, "hook_event_name": "PostToolUse", "tool_name": "Glob", "tool_input": {"pattern": "*.ts"}}, d),
        run_hook({"session_id": SESSION, "hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/tmp/x.ts"}}, d),
        run_hook({"session_id": SESSION, "hook_event_name": "SessionStart", "tool_name": "Bash", "tool_input": {}}, d),
    ]
    check("10: unknown tool/event -> exit 0, silent", all(rc == 0 and not out.strip() for rc, out, _ in cases))

    # 11. State files older than 48h are cleaned up opportunistically.
    d = fresh_dir(); dirs.append(d)
    stale = os.path.join(d, "old-session.json")
    with open(stale, "w") as f:
        f.write("{}")
    old = time.time() - 3 * 24 * 3600
    os.utime(stale, (old, old))
    run_hook(pre_bash("echo hi"), d)
    check("11: >48h state file removed", not os.path.exists(stale))

    # 12. Interrupted commands do not count as failures.
    d = fresh_dir(); dirs.append(d)
    seq = []
    for i in range(3):
        seq.append(pre_bash("python3 /tmp/slow.py"))
        seq.append(post_bash("python3 /tmp/slow.py", interrupted=True))
    seq.append(pre_bash("python3 /tmp/slow.py"))
    results = drive(seq, d)
    check("12: interrupted attempts un-counted", all(nudge_of(r) is None for r in results))

    # 13. Global cap: max 2 nudges per 20 tracked calls.
    d = fresh_dir(); dirs.append(d)
    seq = (
        [pre_bash(f"python3 /tmp/a.py --{i}") for i in range(4)]
        + [pre_bash(f"node /tmp/b.js --{i}") for i in range(4)]
        + [pre_bash(f"sh /tmp/c.sh --{i}") for i in range(4)]
    )
    results = drive(seq, d)
    nudges = [n for n in (nudge_of(r) for r in results) if n]
    check("13: capped at 2 nudges per 20 calls", len(nudges) == 2)

    # 14. Informational non-zero exits (returnCodeInterpretation) arrive as
    #     Post successes and reset like any success.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash("python3 /tmp/fix.py --a"),
            pre_bash("python3 /tmp/fix.py --b"),
            post_bash("python3 /tmp/fix.py --b", rci="No matches found"),
            pre_bash("python3 /tmp/fix.py --c"),
            pre_bash("python3 /tmp/fix.py --d"),
        ],
        d,
    )
    check("14: rci success resets like plain success", all(nudge_of(r) is None for r in results))

    # 15. QA 2026-08-01: pathless one-liners must not collapse into one
    #     bare-head shape — but identical pathless commands still count.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash('python3 -c "import requests"'),
            pre_bash('python3 -c "assert 1==2"'),
            pre_bash('python3 -c "print(undefined_var)"'),
            pre_bash('python3 -c "from lib import thing"'),
        ],
        d,
    )
    check("15a: unrelated pathless one-liners never cross-count", all(nudge_of(r) is None for r in results))
    d = fresh_dir(); dirs.append(d)
    results = drive([pre_bash('python3 -c "import missing_module"')] * 4, d)
    check("15b: identical pathless command still fires", nudge_of(results[3]) is not None)

    # 16. QA 2026-08-01: curl against env-var endpoints — different vars are
    #     different shapes; the same var repeatedly is a real 2-Strike.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash('curl -sf "$STRIPE_URL"'),
            pre_bash('curl -X POST "$WEBHOOK_TARGET"'),
            pre_bash('curl -s "$THIRD_ENDPOINT"'),
        ],
        d,
    )
    check("16a: different env-var endpoints never cross-count", all(nudge_of(r) is None for r in results))
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash('curl -sf "$API_URL"'),
            pre_bash('curl -v "$API_URL"'),
            pre_bash('curl -s "$API_URL"'),
        ],
        d,
    )
    n = nudge_of(results[2])
    check("16b: same env-var endpoint (boolean-flag rewrites) fires 2-Strike", n is not None and "2-Strike" in n)

    # 17. QA 2026-08-01: passing verification behind wrappers still resets
    #     edit counters (timeout 120 npm test, bash -c 'npm test').
    for wrapped in ("timeout 120 npm test", "timeout -k 5 30 npm test", "bash -c 'npm test'"):
        d = fresh_dir(); dirs.append(d)
        results = drive(
            [
                post_edit("/tmp/app/logic.ts"),
                post_edit("/tmp/app/logic.ts"),
                post_edit("/tmp/app/logic.ts"),
                post_bash(wrapped),
                post_edit("/tmp/app/logic.ts"),
            ],
            d,
        )
        check(f"17: `{wrapped}` resets edit counters", all(nudge_of(r) is None for r in results))

    # 18. QA 2026-08-01: git -C <dir> — the dir is not the subcommand;
    #     different subcommands stay distinct, one subcommand still fires.
    d = fresh_dir(); dirs.append(d)
    results = drive(
        [
            pre_bash("git -C /tmp/repo fetch"),
            pre_bash("git -C /tmp/repo pull"),
            pre_bash("git -C /tmp/repo push origin dev"),
            pre_bash("git -C /tmp/repo status"),
        ],
        d,
    )
    check("18a: different git -C subcommands never cross-count", all(nudge_of(r) is None for r in results))
    d = fresh_dir(); dirs.append(d)
    results = drive([pre_bash("git -C /tmp/repo push origin dev")] * 4, d)
    n = nudge_of(results[3])
    check("18b: repeated git -C push fires with real subcommand in shape", n is not None and "git push" in n)

    # 19. QA 2026-08-01: corrupt-but-typed state entries are dropped on load
    #     (self-heal) — detection keeps working, state file gets repaired.
    d = fresh_dir(); dirs.append(d)
    seeded = os.path.join(d, f"{SESSION}.json")
    with open(seeded, "w") as f:
        json.dump({"schema": 1, "calls": 5, "nudges": [], "shapes": {"python3 /tmp/x.py": "corrupt"}, "edits": {}}, f)
    results = drive([pre_bash(f"python3 /tmp/x.py --n {i}") for i in range(4)], d)
    check("19a: detection survives corrupt state entry", nudge_of(results[3]) is not None)
    with open(seeded) as f:
        healed = json.load(f)
    check("19b: state file self-healed", healed["calls"] == 9 and isinstance(healed["shapes"].get("python3 /tmp/x.py"), dict))

    # 20. Cap-window expiry: old nudges age out after CAP_WINDOW calls and a
    #     later spiral fires again.
    d = fresh_dir(); dirs.append(d)
    seq = (
        [pre_bash(f"python3 /tmp/a.py --{i}") for i in range(4)]  # nudge @ call 4
        + [pre_bash(f"node /tmp/b.js --{i}") for i in range(4)]  # nudge @ call 8
        + [pre_bash(f"sh /tmp/filler-{i}.sh") for i in range(16)]  # calls 9-24
        + [pre_bash(f"python3 /tmp/c.py --{i}") for i in range(4)]  # calls 25-28
    )
    results = drive(seq, d)
    nudges = [i for i, r in enumerate(results) if nudge_of(r)]
    check("20: nudges age out of the cap window", nudges == [3, 7, 27])

    # 21. QA 2026-08-01: SIGINT while blocked on stdin -> still exit 0, silent.
    import signal

    env = dict(os.environ, LOOP_DETECTOR_STATE_DIR=fresh_dir())
    p = subprocess.Popen(
        ["python3", HOOK],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    time.sleep(0.5)
    p.send_signal(signal.SIGINT)
    out, _err = p.communicate(timeout=5)
    check("21: SIGINT -> exit 0, no output", p.returncode == 0 and not out.strip())

    # --- P10: python "ghost edit" detector (audit 2026-08-28) ----------------
    GHOST_CMD = (
        "python3 - <<'PY'\n"
        "s = open('/tmp/app.ts').read()\n"
        "s = s.replace(OLD, NEW)\n"
        "open('/tmp/app.ts', 'w').write(s)\n"
        "PY"
    )

    # 22. FIRES: file was Edited (so a formatter ran), then python-replaced
    #     with no guard.
    d = fresh_dir(); dirs.append(d)
    r = drive([post_edit("/tmp/app.ts"), pre_bash(GHOST_CMD)], d)
    n = nudge_of(r[1])
    check("22a: ghost edit on a formatter-touched file fires",
          n is not None and "no longer exist on disk" in n)
    check("22b: nudge names the file and the assert guard",
          n is not None and "/tmp/app.ts" in n and "assert OLD in s" in n)
    check("22c: fires once per file per session",
          nudge_of(drive([pre_bash(GHOST_CMD)], d)[0]) is None)

    # 23. QUIET: the replace is already guarded with an assert.
    d = fresh_dir(); dirs.append(d)
    guarded = GHOST_CMD.replace("s = s.replace(OLD, NEW)",
                                "assert OLD in s, 'anchor missing'\ns = s.replace(OLD, NEW)")
    check("23: assert-guarded replace stays quiet",
          nudge_of(drive([post_edit("/tmp/app.ts"), pre_bash(guarded)], d)[1]) is None)

    # 23b. QUIET: re.subn with a checked count is equally guarded.
    d = fresh_dir(); dirs.append(d)
    subn = GHOST_CMD.replace("s = s.replace(OLD, NEW)", "s, n = re.subn(OLD, NEW, s)")
    check("23b: re.subn variant stays quiet",
          nudge_of(drive([post_edit("/tmp/app.ts"), pre_bash(subn)], d)[1]) is None)

    # 24. QUIET: file was never Edited this session -> no formatter ran on it,
    #     so there is no stale-anchor hazard to warn about.
    d = fresh_dir(); dirs.append(d)
    check("24: untouched file stays quiet",
          nudge_of(drive([pre_bash(GHOST_CMD)], d)[0]) is None)

    # 25. QUIET: markdown/other extensions are not formatted by the PostToolUse
    #     formatters (prettier excludes md; ruff is py-only).
    d = fresh_dir(); dirs.append(d)
    md_cmd = GHOST_CMD.replace("app.ts", "notes.md")
    check("25: non-formatted extension stays quiet",
          nudge_of(drive([post_edit("/tmp/notes.md"), pre_bash(md_cmd)], d)[1]) is None)

    # 26. QUIET: a python read of the same file (no write-back) is not an edit.
    d = fresh_dir(); dirs.append(d)
    read_only = "python3 -c \"print(open('/tmp/app.ts').read().replace('a','b'))\""
    check("26: replace with no write-back stays quiet",
          nudge_of(drive([post_edit("/tmp/app.ts"), pre_bash(read_only)], d)[1]) is None)

    # 27. MALFORMED: missing keys / wrong types must not crash or nudge.
    d = fresh_dir(); dirs.append(d)
    bad = [
        {"session_id": SESSION, "hook_event_name": "PreToolUse", "tool_name": "Bash"},
        {"session_id": SESSION, "hook_event_name": "PreToolUse", "tool_name": "Bash",
         "tool_input": None},
        {"session_id": SESSION, "hook_event_name": "PostToolUse", "tool_name": "Edit",
         "tool_input": {"file_path": None}},
        {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {}},
        {},
    ]
    res = drive(bad, d)
    check("27a: malformed payloads exit 0", all(r[0] == 0 for r in res))
    check("27b: malformed payloads stay silent", all(nudge_of(r) is None for r in res))
    rc, out, _ = run_hook(None, d, raw='{"broken": ')
    check("27c: unparseable JSON exits 0 silently", rc == 0 and not out.strip())

    # 28. Backward compat: a schema-1 state file written before "formatted"
    #     existed must still be honoured, not discarded.
    d = fresh_dir(); dirs.append(d)
    legacy = os.path.join(d, SESSION + ".json")
    with open(legacy, "w") as f:
        json.dump({"schema": 1, "calls": 7, "nudges": [], "shapes": {}, "edits": {}}, f)
    run_hook(post_edit("/tmp/app.ts"), d)
    with open(legacy) as f:
        st_after = json.load(f)
    check("28: legacy state kept its call count and gained 'formatted'",
          st_after.get("calls") == 8 and "/tmp/app.ts" in (st_after.get("formatted") or {}))

    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)

    elapsed = time.time() - start
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed in {elapsed:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
