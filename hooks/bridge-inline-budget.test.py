"""Behaviour suite for bridge-inline-budget. Run: python3 ~/.claude/hooks/bridge-inline-budget.test.py

Fixtures mirror real PreToolUse / PostToolUse / PostToolUseFailure payloads
captured live from Claude Code CLI 2.1.259 on 2026-09-17: `tool_use_id` on
both sides, `prompt_id` per user prompt, `duration_ms` on both Post events, a
failing command firing PostToolUseFailure (never PostToolUse), and a subagent's
Bash carrying the parent's session_id and prompt_id plus agent_id/agent_type.

The clock is fake: every call passes an explicit epoch through
BRIDGE_INLINE_BUDGET_NOW. No real sleeps anywhere.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HOOK = os.path.expanduser("~/.claude/hooks/bridge-inline-budget.py")
SESSION = "test-session-bib-0000"
T0 = 1_800_000_000.0  # arbitrary fixed epoch

passed = 0
failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS | {label}")
    else:
        failed += 1
        print(f"FAIL | {label}")


def fresh_dir():
    return tempfile.mkdtemp(prefix="bridge-inline-budget-test-")


def base_env(state_dir, lane="chat", tmux=None):
    env = dict(os.environ)
    env.pop("TMUX", None)
    env.pop("LEASH_LANE", None)
    env.pop("BRIDGE_INLINE_BUDGET_NOW", None)
    env["BRIDGE_INLINE_BUDGET_STATE_DIR"] = state_dir
    if lane is not None:
        env["LEASH_LANE"] = lane
    if tmux is not None:
        env["TMUX"] = tmux
    return env


def run_hook(payload, state_dir, now, raw=None, lane="chat", tmux=None):
    data = raw if raw is not None else json.dumps(payload)
    env = base_env(state_dir, lane=lane, tmux=tmux)
    env["BRIDGE_INLINE_BUDGET_NOW"] = repr(float(now))
    p = subprocess.run(["python3", HOOK], input=data, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


def pre_bash(command, tuid, prompt_id="prompt-A", agent=None, run_in_background=False):
    d = {
        "session_id": SESSION,
        "prompt_id": prompt_id,
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "permission_mode": "bypassPermissions",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "run_in_background": run_in_background},
        "tool_use_id": tuid,
    }
    if agent:
        d["agent_id"] = agent
        d["agent_type"] = "Explore"
    return d


def post_bash(command, tuid, prompt_id="prompt-A", duration_ms=None, agent=None,
              failed_call=False, interrupted=False, run_in_background=False):
    d = {
        "session_id": SESSION,
        "prompt_id": prompt_id,
        "transcript_path": "/tmp/x.jsonl",
        "cwd": "/tmp",
        "permission_mode": "bypassPermissions",
        "hook_event_name": "PostToolUseFailure" if failed_call else "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "run_in_background": run_in_background},
        "tool_use_id": tuid,
    }
    if failed_call:
        d["error"] = "Exit code 1\nFAIL tests"
        d["is_interrupt"] = False
    else:
        d["tool_response"] = {
            "stdout": "ok",
            "stderr": "",
            "interrupted": interrupted,
            "isImage": False,
            "noOutputExpected": False,
        }
    if duration_ms is not None:
        d["duration_ms"] = duration_ms
    if agent:
        d["agent_id"] = agent
        d["agent_type"] = "Explore"
    return d


def nudge_of(result):
    rc, out, err = result
    if not out.strip():
        return None
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def tick(self, s):
        self.t += s
        return self.t


def call(state_dir, clock, seconds, tuid, prompt_id="prompt-A", agent=None,
         failed_call=False, lane="chat", tmux=None, duration_ms=None):
    """One complete Bash call: Pre at clock.t, Post `seconds` later. Returns (pre, post)."""
    pre = run_hook(pre_bash("cmd " + tuid, tuid, prompt_id, agent), state_dir, clock.t, lane=lane, tmux=tmux)
    clock.tick(seconds)
    post = run_hook(
        post_bash("cmd " + tuid, tuid, prompt_id, duration_ms=duration_ms, agent=agent, failed_call=failed_call),
        state_dir, clock.t, lane=lane, tmux=tmux,
    )
    return pre, post


def state_of(state_dir):
    p = os.path.join(state_dir, SESSION + ".json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def main():
    start = time.time()
    dirs = []

    # 1. Outside the chat lane: LEASH_LANE unset, or 'bg' -> exit 0, no
    #    output, and not even a state file.
    for lane in (None, "bg", "worker", "CHAT"):
        d = fresh_dir(); dirs.append(d)
        c = Clock()
        results = []
        for i in range(5):
            pre, post = call(d, c, 100, f"t{i}", lane=lane)
            results += [pre, post]
        check(f"1: lane={lane!r} -> silent, exit 0, no state",
              all(r[0] == 0 and not r[1].strip() for r in results) and state_of(d) is None)

    # 2. Inside tmux (LEASH_LANE=chat but $TMUX set) -> silent.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    results = []
    for i in range(5):
        pre, post = call(d, c, 100, f"t{i}", tmux="/private/tmp/tmux-501/default,1234,0")
        results += [pre, post]
    check("2: $TMUX set -> silent, exit 0, no state",
          all(r[0] == 0 and not r[1].strip() for r in results) and state_of(d) is None)

    # 3. Three 50 s calls then one 40 s call -> 190 s: the first warning fires
    #    exactly once, on the 4th Post, via PostToolUse additionalContext.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    results = []
    for i, secs in enumerate((50, 50, 50, 40)):
        results.append(call(d, c, secs, f"t{i}"))
    check("3a: silent through 150 s", all(nudge_of(r[0]) is None and nudge_of(r[1]) is None for r in results[:3]))
    check("3b: Pre never emits anything", all(nudge_of(r[0]) is None for r in results))
    n = nudge_of(results[3][1])
    check("3c: fires on the 4th Post at 190 s", n is not None and n.startswith("Bridge chat lane: 190 s of foreground Bash this turn."))
    check("3d: names the handoff command", n is not None and "node ~/dev/claude-telegram-bridge/bg.mjs --file <brief>" in n)
    check("3e: not the second warning", n is not None and "SECOND WARNING" not in n)
    out_json = json.loads(results[3][1][1])["hookSpecificOutput"]
    check("3f: correct rail: PostToolUse additionalContext, no decision field",
          out_json.get("hookEventName") == "PostToolUse" and "decision" not in out_json
          and "permissionDecision" not in out_json)
    check("3g: exit 0 on every call", all(r[0][0] == 0 and r[1][0] == 0 for r in results))
    # two more 50 s calls (290 s) stay silent: once per threshold
    more = [call(d, c, 50, f"u{i}") for i in range(2)]
    check("3h: fires exactly once below 480 s", all(nudge_of(r[1]) is None for r in more))
    st = state_of(d)
    check("3i: state carries the running total", st is not None and abs(st["total_s"] - 290) < 1e-6 and st["warned"] == 1)

    # 4. The 480 s second warning fires exactly once, prefixed SECOND WARNING,
    #    and nothing fires after it.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    fired = []
    for i in range(12):  # 12 x 60 s = 720 s
        pre, post = call(d, c, 60, f"t{i}")
        n = nudge_of(post)
        if n:
            fired.append((i, n))
    check("4a: exactly two warnings over 720 s", len(fired) == 2)
    check("4b: first at 180 s (3rd call)", fired and fired[0][0] == 2 and fired[0][1].startswith("Bridge chat lane: 180 s"))
    check("4c: second at 480 s (8th call), prefixed",
          len(fired) == 2 and fired[1][0] == 7 and fired[1][1].startswith("SECOND WARNING: Bridge chat lane: 480 s"))
    check("4d: second warning carries the same body",
          len(fired) == 2 and fired[1][1].split(": ", 1)[1].split(" s of ")[1] == fired[0][1].split(" s of ")[1])

    # 5. A new turn (prompt_id changes) resets the total and the warnings.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    for i in range(4):
        call(d, c, 50, f"a{i}", prompt_id="prompt-A")  # 200 s, warned once
    check("5a: turn A warned", state_of(d)["warned"] == 1)
    pre, post = call(d, c, 100, "b0", prompt_id="prompt-B")
    st = state_of(d)
    check("5b: new prompt_id -> silent 100 s call, total reset",
          nudge_of(post) is None and st["prompt_id"] == "prompt-B" and abs(st["total_s"] - 100) < 1e-6
          and st["warned"] == 0 and st["calls"] == 1)
    pre, post = call(d, c, 100, "b1", prompt_id="prompt-B")
    check("5c: turn B accumulates on its own and warns again at 200 s", nudge_of(post) is not None)

    # 6. Missing or corrupt state file -> treated as zero, no crash, exit 0.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    seeded = os.path.join(d, SESSION + ".json")
    corrupt_bodies = [
        "this is not json {",
        "",
        "[]",
        json.dumps({"schema": 2, "total_s": 999}),
        json.dumps({"schema": 1, "prompt_id": "prompt-A", "total_s": -5, "calls": 1, "warned": 0, "last_seen": 0, "pending": {}}),
        json.dumps({"schema": 1, "prompt_id": "prompt-A", "total_s": "999", "calls": 1, "warned": 0, "last_seen": 0, "pending": {}}),
        json.dumps({"schema": 1, "prompt_id": "prompt-A", "total_s": 999, "calls": 1, "warned": 7, "last_seen": 0, "pending": {}}),
        json.dumps({"schema": 1, "prompt_id": "prompt-A", "total_s": 999, "calls": 1, "warned": 0, "last_seen": 0, "pending": "nope"}),
        json.dumps({"schema": 1, "prompt_id": 5, "total_s": 999, "calls": 1, "warned": 0, "last_seen": 0, "pending": {}}),
    ]
    all_ok = True
    for body in corrupt_bodies:
        with open(seeded, "w") as f:
            f.write(body)
        pre, post = call(d, c, 100, "c-" + str(abs(hash(body)) % 10000))
        st = state_of(d)
        ok = (pre[0] == 0 and post[0] == 0 and nudge_of(post) is None
              and st is not None and abs(st["total_s"] - 100) < 1e-6 and st["calls"] == 1)
        if not ok:
            all_ok = False
            print(f"      corrupt body {body[:50]!r}: pre={pre} post={post} st={st}")
    check("6a: every corrupt state body reads as zero and heals", all_ok)
    # missing file is the default path; also a state DIR that does not exist yet
    d2 = os.path.join(fresh_dir(), "nested", "dir"); dirs.append(os.path.dirname(os.path.dirname(d2)))
    pre, post = call(d2, Clock(), 30, "m0")
    check("6b: missing state dir/file -> created, exit 0, silent",
          pre[0] == 0 and post[0] == 0 and nudge_of(post) is None and state_of(d2)["calls"] == 1)
    # a corrupt entry inside pending is dropped, the rest kept
    d = fresh_dir(); dirs.append(d)
    with open(os.path.join(d, SESSION + ".json"), "w") as f:
        json.dump({"schema": 1, "prompt_id": "prompt-A", "total_s": 170, "calls": 2, "warned": 0,
                   "last_seen": T0, "pending": {"good": T0 - 15, "bad": "x", "neg": -3, "lst": [1], "none": None}}, f)
    r = run_hook(post_bash("cmd", "good", duration_ms=1), d, T0)
    n = nudge_of(r)
    check("6c: seeded 170 s + 15 s matched start -> warns at 185 s, bad pending entries dropped",
          n is not None and n.startswith("Bridge chat lane: 185 s") and state_of(d)["pending"] == {})

    # 7. Exit code is always 0, and silent: garbage stdin, empty stdin, unknown
    #    events/tools, missing fields.
    d = fresh_dir(); dirs.append(d)
    cases = [
        run_hook(None, d, T0, raw="this is not json {"),
        run_hook(None, d, T0, raw=""),
        run_hook(None, d, T0, raw="   \n"),
        run_hook(None, d, T0, raw="[1,2,3]"),
        run_hook({}, d, T0),
        run_hook({"tool_name": "Bash"}, d, T0),
        run_hook({"hook_event_name": "PostToolUse", "tool_name": "Bash"}, d, T0),
        run_hook({"session_id": SESSION, "hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}, d, T0),
        run_hook({"session_id": SESSION, "hook_event_name": "SessionStart"}, d, T0),
        run_hook({"session_id": SESSION, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": None}, d, T0),
        run_hook({"session_id": "../../etc/passwd", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "x"}}, d, T0),
    ]
    check("7a: garbage in -> exit 0, silent", all(rc == 0 and not out.strip() for rc, out, _ in cases))
    check("7b: session id is sanitised (no path escape)",
          not os.path.exists(os.path.join(d, "..", "..", "etc")) and any(n.startswith("etcpasswd") for n in os.listdir(d)))
    # SIGINT while blocked on stdin -> still exit 0, silent
    import signal
    env = base_env(fresh_dir())
    p = subprocess.Popen(["python3", HOOK], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    time.sleep(0.5)
    p.send_signal(signal.SIGINT)
    out, _err = p.communicate(timeout=5)
    check("7c: SIGINT -> exit 0, no output", p.returncode == 0 and not out.strip())

    # 8. Failing commands fire PostToolUseFailure, not PostToolUse (CLI
    #    2.1.259): they count all the same, and the warning rides that event.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    results = [call(d, c, 70, f"f{i}", failed_call=True) for i in range(3)]
    n = nudge_of(results[2][1])
    check("8a: three failing 70 s calls warn at 210 s", n is not None and n.startswith("Bridge chat lane: 210 s"))
    check("8b: rail is PostToolUseFailure additionalContext",
          json.loads(results[2][1][1])["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure")

    # 9. Subagent Bash (agent_id present, parent's session/prompt ids) counts
    #    toward the same turn.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    call(d, c, 100, "main0")
    pre, post = call(d, c, 90, "sub0", agent="a802694fd501a30d8")
    n = nudge_of(post)
    check("9a: main 100 s + subagent 90 s -> warning at 190 s", n is not None and "190 s" in n)
    # a subagent-first turn: the subagent's Bash arrives before any main Bash
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    call(d, c, 100, "a0", prompt_id="prompt-A")
    pre, post = call(d, c, 100, "s0", prompt_id="prompt-B", agent="agent-xyz")
    check("9b: subagent Bash with a new prompt_id starts the new turn (100 s, silent)",
          nudge_of(post) is None and state_of(d)["prompt_id"] == "prompt-B" and abs(state_of(d)["total_s"] - 100) < 1e-6)
    pre, post = call(d, c, 100, "m1", prompt_id="prompt-B")
    check("9c: the main thread's later Bash adds to it (200 s -> warns)", nudge_of(post) is not None)

    # 10. A single long call never fires on its own; the next call does.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    pre, post = call(d, c, 300, "long0")
    check("10a: one 300 s call alone stays silent", nudge_of(post) is None)
    pre, post = call(d, c, 5, "short0")
    n = nudge_of(post)
    check("10b: the next 5 s call fires with the sum (305 s)", n is not None and n.startswith("Bridge chat lane: 305 s"))
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    pre, post = call(d, c, 600, "long1")
    check("10c: one 600 s call alone stays silent (above both thresholds)", nudge_of(post) is None)
    pre, post = call(d, c, 1, "short1")
    n = nudge_of(post)
    check("10d: next call goes straight to SECOND WARNING at 601 s, once",
          n is not None and n.startswith("SECOND WARNING: Bridge chat lane: 601 s"))
    pre, post = call(d, c, 100, "short2")
    check("10e: nothing after the second warning", nudge_of(post) is None)

    # 11. Nothing fires mid-call: a Pre for a call that never completes adds
    #     nothing, however long ago it started.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    run_hook(pre_bash("hang", "hang0"), d, c.t)
    c.tick(500)
    pre, post = call(d, c, 10, "n0")
    pre, post = call(d, c, 10, "n1")
    st = state_of(d)
    check("11: an unfinished call contributes nothing (20 s counted, no warning)",
          nudge_of(post) is None and abs(st["total_s"] - 20) < 1e-6 and "hang0" in st["pending"])

    # 12. Post without a recorded start falls back to duration_ms; with
    #     neither it counts zero.
    d = fresh_dir(); dirs.append(d)
    r1 = run_hook(post_bash("x", "nopre0", duration_ms=100_000), d, T0)
    r2 = run_hook(post_bash("x", "nopre1", duration_ms=95_000), d, T0)
    n = nudge_of(r2)
    check("12a: duration_ms fallback (100 s + 95 s) warns at 195 s", n is not None and "195 s" in n)
    d = fresh_dir(); dirs.append(d)
    for i in range(5):
        run_hook(post_bash("x", f"bare{i}"), d, T0)
    check("12b: no start and no duration_ms counts zero", abs(state_of(d)["total_s"]) < 1e-9 and state_of(d)["calls"] == 5)

    # 13. Idle fallback (payloads WITHOUT prompt_id): > 600 s of no Bash
    #     activity before a Pre resets; a long single call does not.
    d = fresh_dir(); dirs.append(d)
    c = Clock()

    def nopid(payload):
        payload.pop("prompt_id", None)
        return payload

    for i in range(2):
        run_hook(nopid(pre_bash("x", f"i{i}")), d, c.t); c.tick(80)
        run_hook(nopid(post_bash("x", f"i{i}")), d, c.t)
    check("13a: 160 s accumulated without prompt_id", abs(state_of(d)["total_s"] - 160) < 1e-6)
    c.tick(601)
    run_hook(nopid(pre_bash("x", "i2")), d, c.t); c.tick(80)
    r = run_hook(nopid(post_bash("x", "i2")), d, c.t)
    check("13b: >600 s idle before a Pre resets (80 s, silent)",
          nudge_of(r) is None and abs(state_of(d)["total_s"] - 80) < 1e-6)
    run_hook(nopid(pre_bash("x", "i3")), d, c.t); c.tick(590)
    r = run_hook(nopid(post_bash("x", "i3")), d, c.t)
    check("13c: a 590 s single call does not reset itself (670 s total, 2 calls -> SECOND WARNING)",
          nudge_of(r) is not None and nudge_of(r).startswith("SECOND WARNING") and abs(state_of(d)["total_s"] - 670) < 1e-6)

    # 14. Backgrounded Bash calls are not counted (their Post returns at once
    #     and they are blocked in the headless lane anyway).
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    for i in range(3):
        run_hook(pre_bash("x", f"bg{i}", run_in_background=True), d, c.t); c.tick(100)
        run_hook(post_bash("x", f"bg{i}", run_in_background=True), d, c.t)
    st = state_of(d)
    check("14: run_in_background calls add nothing", st is None or (st["calls"] == 0 and st["total_s"] == 0))

    # 15. Interrupted calls still count (wall time is wall time).
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    run_hook(pre_bash("x", "int0"), d, c.t); c.tick(100)
    run_hook(post_bash("x", "int0", interrupted=True), d, c.t)
    run_hook(pre_bash("x", "int1"), d, c.t); c.tick(100)
    r = run_hook(post_bash("x", "int1"), d, c.t)
    check("15: interrupted 100 s + 100 s -> warning at 200 s", nudge_of(r) is not None)

    # 16. State files older than 48h are cleaned up opportunistically.
    d = fresh_dir(); dirs.append(d)
    stale = os.path.join(d, "old-session.json")
    with open(stale, "w") as f:
        f.write("{}")
    old = time.time() - 3 * 24 * 3600
    os.utime(stale, (old, old))
    run_hook(pre_bash("x", "k0"), d, T0)
    check("16: >48h state file removed", not os.path.exists(stale))

    # 17. Pending starts are capped so a turn of Pre-only calls cannot grow
    #     the file without bound.
    d = fresh_dir(); dirs.append(d)
    for i in range(80):
        run_hook(pre_bash("x", f"p{i}"), d, T0 + i)
    check("17: pending starts capped at 50, newest kept",
          len(state_of(d)["pending"]) == 50 and "p79" in state_of(d)["pending"] and "p0" not in state_of(d)["pending"])

    # 18. A payload with no tool_use_id still accounts by sequence.
    d = fresh_dir(); dirs.append(d)
    c = Clock()
    for i in range(2):
        p = pre_bash("x", "zz"); p.pop("tool_use_id")
        run_hook(p, d, c.t); c.tick(100)
        q = post_bash("x", "zz", duration_ms=100_000); q.pop("tool_use_id")
        r = run_hook(q, d, c.t)
    check("18: no tool_use_id -> duration_ms path, 200 s warns", nudge_of(r) is not None)

    # 19. Real-shaped payload from the live capture (extra fields present) is
    #     accepted as-is.
    d = fresh_dir(); dirs.append(d)
    real_pre = {"session_id": SESSION, "transcript_path": "/Users/zalo/.claude/projects/-Users-zalo-dev/x.jsonl",
                "cwd": "/Users/zalo/dev", "prompt_id": "9f3c75c1-0000-4000-8000-000000000000",
                "permission_mode": "bypassPermissions", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "npm test", "description": "Run tests", "timeout": 600000},
                "tool_use_id": "toolu_011pBHYU", "effort": {"level": "high"},
                "scratchpad_dir": "/tmp/claude-501/-Users-zalo-dev/x/scratchpad"}
    real_post = dict(real_pre, hook_event_name="PostToolUse",
                     tool_response={"stdout": "ok", "stderr": "", "interrupted": False, "isImage": False, "noOutputExpected": False},
                     duration_ms=62)
    r1 = run_hook(real_pre, d, T0)
    r2 = run_hook(real_post, d, T0 + 200)
    r3 = run_hook(dict(real_pre, tool_use_id="toolu_2"), d, T0 + 200)
    r4 = run_hook(dict(real_post, tool_use_id="toolu_2"), d, T0 + 210)
    check("19: live-captured payload shape accounts (200 s + 10 s -> warns)",
          all(r[0] == 0 for r in (r1, r2, r3, r4)) and nudge_of(r4) is not None)

    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)

    elapsed = time.time() - start
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed in {elapsed:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
