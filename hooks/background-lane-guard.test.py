#!/usr/bin/env python3
"""Suite for background-lane-guard.py.

Run: python3 ~/.claude/hooks/background-lane-guard.test.py
Changing the guard means re-running this, same rule as tmux-peer-guard.

Three rules live in the guard, and each has its own block here:
  - Bash: run_in_background with $TMUX unset (the original half, unchanged).
  - P2, Agent/Task: a headless run must pass run_in_background exactly false.
    SendMessage in a headless run gets a warning, never a block.
  - P3, Agent/Task: a verifier dispatch in a bridge worker needs the draft
    report on disk first ($BG_REPORT_DRAFT, fresh for this run).

Every case runs the real script in a subprocess with a scrubbed environment,
so nothing from the shell running the suite leaks into a verdict.

Exit 0 = all pass.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "background-lane-guard.py")

ALLOW, BLOCK = 0, 2

# Every variable the guard reads. Scrubbed before each case so the suite gives
# the same answer inside tmux, inside a bridge worker, and in a plain terminal.
SCRUB = (
    "TMUX",
    "LEASH_LANE",
    "CLAUDE_CODE_ENTRYPOINT",
    "BG_REPORT_DRAFT",
    "BG_RUN_STARTED_AT",
    "LEASH_TRIGGER",
    "LEASH_SCHEDULE_ID",
    "LEASH_ALLOW_WRITE",
)

TMUX_VAL = "/tmp/tmux-501/default,123,0"
BG = {"LEASH_LANE": "bg", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}
CHAT = {"LEASH_LANE": "chat", "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}
SCRIPT_RUN = {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}
INTERACTIVE_TMUX = {"TMUX": TMUX_VAL, "CLAUDE_CODE_ENTRYPOINT": "cli"}
INTERACTIVE_BARE = {"CLAUDE_CODE_ENTRYPOINT": "cli"}

SCRATCH = tempfile.mkdtemp(prefix="blg-test-")


def run(payload, env_over=None):
    env = dict(os.environ)
    for k in SCRUB:
        env.pop(k, None)
    env.update(env_over or {})
    if isinstance(payload, (dict, list)):
        data = json.dumps(payload)
    else:
        data = payload
    p = subprocess.run(
        [sys.executable, GUARD],
        input=data,
        capture_output=True,
        text=True,
        env=env,
    )
    return p.returncode, p.stdout, p.stderr


def bash(command="echo hi", background=False):
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command, "run_in_background": background},
    }


_OMIT = object()


def agent(rib=_OMIT, subagent_type="general-purpose", tool="Agent", **extra):
    ti = {"description": "d", "prompt": "p", "subagent_type": subagent_type}
    if rib is not _OMIT:
        ti["run_in_background"] = rib
    payload = {"tool_name": tool, "tool_input": ti}
    payload.update(extra)
    return payload


def send_message():
    return {
        "tool_name": "SendMessage",
        "tool_input": {"to": "a0123", "summary": "re-verify", "message": "please re-verify"},
    }


CASES = []


def case(name, want, payload, env=None, stderr_has=(), stdout_has=(),
         stdout_empty=False, order=None, stdout_lacks=()):
    CASES.append((name, want, payload, env or {}, tuple(stderr_has), tuple(stdout_has),
                  stdout_empty, order, tuple(stdout_lacks)))


# ============================================================================
# Bash half (unchanged behaviour)
# ============================================================================
case("bash: headless + background => BLOCK", BLOCK, bash("sleep 60", True), None,
     ["background-lane-guard"])
case("bash: tmux + background => allow", ALLOW, bash("sleep 60", True), {"TMUX": TMUX_VAL})
case("bash: headless + foreground => allow", ALLOW, bash("sleep 60", False))
case("bash: tmux + foreground => allow", ALLOW, bash("sleep 60", False), {"TMUX": TMUX_VAL})
case(
    "bash: the 2026-07-28 deploy poller => BLOCK",
    BLOCK,
    bash("until [ \"$(curl -s https://x | grep -o y)\" != 'z' ]; do sleep 15; done", True),
)
case("bash: bg.mjs handoff backgrounded => allow", ALLOW,
     bash('node ~/dev/claude-telegram-bridge/bg.mjs "do a thing"', True))
case("bash: schedule.mjs backgrounded => allow", ALLOW,
     bash('node ~/dev/claude-telegram-bridge/schedule.mjs add in 10m "ping" --run', True))
case("bash: no tool_input => allow", ALLOW, {"tool_name": "Bash"})
case("bash: run_in_background explicitly false => allow", ALLOW,
     {"tool_name": "Bash", "tool_input": {"command": "x", "run_in_background": False}})
case("bash: block message names bg.mjs", BLOCK, bash("sleep 1", True), None, ["bg.mjs"])
case("bash: block message names schedule.mjs", BLOCK, bash("sleep 1", True), None, ["schedule.mjs"])
case("bash: block message names FOREGROUND", BLOCK, bash("sleep 1", True), None, ["FOREGROUND"])
case("bash: a bridge worker env does not change the Bash half", BLOCK, bash("sleep 1", True), BG)

# ============================================================================
# P2: Agent/Task in a headless run
# ============================================================================
# -- block: the omitted flag is the common failure shape ----------------------
case("P2: bg worker, run_in_background omitted => BLOCK", BLOCK, agent(), BG,
     ["background-lane-guard", "run_in_background: false"])
case("P2: bg worker, run_in_background true => BLOCK", BLOCK, agent(True), BG)
case("P2: bg worker, run_in_background the STRING 'false' => BLOCK", BLOCK, agent("false"), BG)
case("P2: bg worker, run_in_background 0 => BLOCK (not JSON false)", BLOCK, agent(0), BG)
case("P2: bg worker, run_in_background null => BLOCK", BLOCK, agent(None), BG)
case("P2: chat lane, omitted => BLOCK", BLOCK, agent(), CHAT)
case("P2: headless script (sdk-cli, no LEASH_LANE), omitted => BLOCK", BLOCK, agent(), SCRIPT_RUN)
case("P2: other sdk entrypoint (sdk-ts), omitted => BLOCK", BLOCK, agent(),
     {"CLAUDE_CODE_ENTRYPOINT": "sdk-ts"})
case("P2: LEASH_LANE set with no entrypoint, omitted => BLOCK", BLOCK, agent(), {"LEASH_LANE": "bg"})
case("P2: legacy Task tool name, omitted => BLOCK", BLOCK, agent(tool="Task"), BG)
case("P2: inside a subagent (agent_id set) the rule still applies", BLOCK,
     agent(agent_id="a1b2", agent_type="general-purpose"), BG)
# -- the block message carries the fix and the alternative --------------------
case("P2: message says the background default dies at turn end", BLOCK, agent(), BG,
     ["turn end", "never arrive"])
case("P2: message names the long-work alternative", BLOCK, agent(), BG,
     ["node ~/dev/claude-telegram-bridge/bg.mjs --file <brief>"])

# -- allow --------------------------------------------------------------------
case("P2: bg worker, explicit false => allow", ALLOW, agent(False), BG)
case("P2: chat lane, explicit false => allow", ALLOW, agent(False), CHAT)
case("P2: TMUX set, omitted => allow", ALLOW, agent(), INTERACTIVE_TMUX)
case("P2: TMUX set wins over LEASH_LANE, omitted => allow", ALLOW, agent(),
     dict(BG, TMUX=TMUX_VAL))
case("P2: TMUX set, run_in_background true => allow", ALLOW, agent(True), INTERACTIVE_TMUX)
case("P2: interactive cli outside tmux, omitted => allow", ALLOW, agent(), INTERACTIVE_BARE)
case("P2: interactive cli outside tmux, true => allow", ALLOW, agent(True), INTERACTIVE_BARE)
case("P2: no marker env at all, omitted => allow", ALLOW, agent(), {})

# -- malformed payloads fail open ---------------------------------------------
case("P2 malformed: not json => allow", ALLOW, "not json at all", BG)
case("P2 malformed: empty stdin => allow", ALLOW, "", BG)
case("P2 malformed: empty object => allow", ALLOW, {}, BG)
case("P2 malformed: json list => allow", ALLOW, [1, 2, 3], BG)
case("P2 malformed: Agent with no tool_input => allow", ALLOW, {"tool_name": "Agent"}, BG)
case("P2 malformed: Agent with a string tool_input => allow", ALLOW,
     {"tool_name": "Agent", "tool_input": "oops"}, BG)
case("P2 malformed: Agent with a list tool_input => allow", ALLOW,
     {"tool_name": "Agent", "tool_input": [1]}, BG)
case("P2 malformed: tool_name not a string => allow", ALLOW,
     {"tool_name": 7, "tool_input": {}}, BG)

# ============================================================================
# P2: SendMessage warns in a headless run, never blocks
# ============================================================================
case("SendMessage: bg worker => allow with a warning", ALLOW, send_message(), BG,
     (), ["additionalContext", "run_in_background: false", "dies at turn end"])
case("SendMessage: warning says re-verify is a fresh foreground Agent", ALLOW, send_message(), BG,
     (), ["prior verdict pasted"])
case("SendMessage: the warning never approves the call (no permissionDecision)", ALLOW,
     send_message(), BG, (), ["additionalContext"], stdout_lacks=["permissionDecision"])
case("SendMessage: script run => allow with a warning", ALLOW, send_message(), SCRIPT_RUN,
     (), ["additionalContext"])
case("SendMessage: TMUX set => allow, silent", ALLOW, send_message(), INTERACTIVE_TMUX,
     stdout_empty=True)
case("SendMessage: interactive cli => allow, silent", ALLOW, send_message(), INTERACTIVE_BARE,
     stdout_empty=True)
case("SendMessage: malformed tool_input => allow", ALLOW,
     {"tool_name": "SendMessage", "tool_input": "x"}, BG)

# ============================================================================
# P3: verifier dispatch needs the draft report on disk
# ============================================================================
NOW_MS = int(time.time() * 1000)
START_MS = str(NOW_MS - 60_000)  # the worker started a minute ago


def draft_file(name, content="# Draft\nwork so far\n", age_s=None):
    p = os.path.join(SCRATCH, name)
    with open(p, "w") as f:
        f.write(content)
    if age_s is not None:
        t = time.time() - age_s
        os.utime(p, (t, t))
    return p


MISSING = os.path.join(SCRATCH, "bg-1234.draft.md")
EMPTY = draft_file("empty.draft.md", "")
FRESH = draft_file("fresh.draft.md")
STALE = draft_file("stale.draft.md", age_s=3600)  # older than the run start
SLACK = draft_file("slack.draft.md", age_s=60.5)  # 0.5 s before the start: inside the 1 s slack
DIR_AT_PATH = os.path.join(SCRATCH, "a-dir.draft.md")
os.makedirs(DIR_AT_PATH, exist_ok=True)
LOCKED_DIR = os.path.join(SCRATCH, "locked")
os.makedirs(LOCKED_DIR, exist_ok=True)
LOCKED = os.path.join(LOCKED_DIR, "x.draft.md")


def worker(draft, started=START_MS, lane=BG):
    env = dict(lane)
    env["BG_REPORT_DRAFT"] = draft
    if started is not None:
        env["BG_RUN_STARTED_AT"] = started
    return env


# -- block --------------------------------------------------------------------
case("P3: qa-agent, draft missing => BLOCK", BLOCK, agent(False, "qa-agent"), worker(MISSING),
     [MISSING, "Write tool", "usage limit"])
case("P3: live-test, draft missing => BLOCK", BLOCK, agent(False, "live-test"), worker(MISSING))
case("P3: outcomes-grader, draft missing => BLOCK", BLOCK, agent(False, "outcomes-grader"),
     worker(MISSING))
case("P3: qa-agent, draft empty => BLOCK", BLOCK, agent(False, "qa-agent"), worker(EMPTY),
     [EMPTY])
case("P3: qa-agent, draft older than this run => BLOCK", BLOCK, agent(False, "qa-agent"),
     worker(STALE), [STALE])
case("P3: message says full text, not a summary, then re-issue", BLOCK,
     agent(False, "qa-agent"), worker(MISSING), ["full text", "re-issue"])

# -- allow --------------------------------------------------------------------
case("P3: qa-agent, fresh non-empty draft => allow", ALLOW, agent(False, "qa-agent"), worker(FRESH))
case("P3: draft 0.5 s older than the start is inside the slack => allow", ALLOW,
     agent(False, "qa-agent"), worker(SLACK))
case("P3: BG_RUN_STARTED_AT missing, old non-empty draft => allow", ALLOW,
     agent(False, "qa-agent"), worker(STALE, started=None))
case("P3: BG_RUN_STARTED_AT unparsable, old non-empty draft => allow", ALLOW,
     agent(False, "qa-agent"), worker(STALE, started="yesterday"))
case("P3: BG_RUN_STARTED_AT unparsable, draft missing => BLOCK", BLOCK,
     agent(False, "qa-agent"), worker(MISSING, started="yesterday"))
case("P3: a non-verifier agent never needs the draft", ALLOW, agent(False, "Explore"),
     worker(MISSING))
case("P3: no BG_REPORT_DRAFT => the rule is off", ALLOW, agent(False, "qa-agent"), BG)
case("P3: empty BG_REPORT_DRAFT => the rule is off", ALLOW, agent(False, "qa-agent"),
     dict(BG, BG_REPORT_DRAFT=""))
case("P3: inside a subagent (agent_id set) the draft rule is skipped", ALLOW,
     agent(False, "qa-agent", agent_id="a1b2", agent_type="general-purpose"), worker(MISSING))
case("P3 fail open: a directory at the draft path => allow", ALLOW, agent(False, "qa-agent"),
     worker(DIR_AT_PATH))
case("P3 fail open: unreadable metadata (permission) => allow", ALLOW, agent(False, "qa-agent"),
     worker(LOCKED))
case("P3: subagent_type not a string => allow", ALLOW, agent(False, ["qa-agent"]),
     worker(MISSING))

# -- both rules on one call: both reasons, P3 first ----------------------------
case("P2+P3: draft missing AND flag omitted => BLOCK with both reasons, P3 first", BLOCK,
     agent(_OMIT, "qa-agent"), worker(MISSING),
     [MISSING, "run_in_background: false"], order=(MISSING, "run_in_background: false"))
case("P2+P3: draft fresh, flag omitted => BLOCK on P2 only", BLOCK, agent(_OMIT, "qa-agent"),
     worker(FRESH), ["run_in_background: false"])
case("P3 applies in tmux too (only BG_REPORT_DRAFT decides)", BLOCK, agent(_OMIT, "qa-agent"),
     worker(MISSING, lane=INTERACTIVE_TMUX), [MISSING])


def main():
    os.chmod(LOCKED_DIR, 0o000)
    failed = 0
    try:
        for name, want, payload, env, err_has, out_has, out_empty, order, out_lacks in CASES:
            code, out, err = run(payload, env)
            problems = []
            if code != want:
                problems.append(f"exit {code} (wanted {want})")
            for s in err_has:
                if s not in err:
                    problems.append(f"stderr missing {s!r}")
            for s in out_has:
                if s not in out:
                    problems.append(f"stdout missing {s!r}")
            for s in out_lacks:
                if s in out:
                    problems.append(f"stdout has {s!r}")
            if out_empty and out.strip():
                problems.append(f"stdout not empty: {out[:80]!r}")
            if order:
                a, b = order
                if not (a in err and b in err and err.index(a) < err.index(b)):
                    problems.append(f"{a!r} does not come before {b!r} in stderr")
            if problems:
                failed += 1
                print(f"FAIL  {name}: " + "; ".join(problems))
            else:
                print(f"ok    {name}")
    finally:
        os.chmod(LOCKED_DIR, 0o755)
    total = len(CASES)
    print()
    if failed:
        print(f"{total - failed}/{total} passed, {failed} FAILED")
        return 1
    print(f"{total}/{total} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
