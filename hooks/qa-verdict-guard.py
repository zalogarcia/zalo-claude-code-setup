#!/usr/bin/env python3
"""PostToolUse (Agent|Task): a concerned qa-agent verdict must not route as a
clean pass.

Why this exists (harness sweep 2026-09-19, measured on the complete 30 day
population of 57 pass class subagent returns extracted from 3,308 transcripts)
---------------------------------------------------------------------------
`~/.claude/agents/qa-agent.md` gives the agent a THREE value verdict
(PASS / PASS WITH CONCERNS / FAIL). `~/.claude/rules/agent-contracts.md` gave
qa-agent TWO non blocked markers. The middle value had no marker, so it
collapsed onto the pass side, and every orchestrator routes on the marker
alone (`~/.claude/commands/autopilot.md:1304`).

Measured on the 47 returns that carry `## VERIFICATION PASSED`:
  21 say `Assessment: PASS WITH CONCERNS` in the body
  17 say `**Status:** DONE_WITH_CONCERNS`
   1 says `Assessment: FAIL` and emits the pass marker anyway
So 23 of 47 clean looking passes were not clean passes. The contract now maps
PASS WITH CONCERNS and FAIL onto `## ISSUES FOUND`; this hook is the mechanism
that catches a return that did not get the memo, at the exact moment the
orchestrator is about to route it.

What it does
------------
Fires only on a return carrying a `## VERIFICATION PASSED` marker line (qa
agent's pass marker, and nobody else's). Two checks, both pure regex over two
field names, no model call:

  MISMATCH   the body's own verdict contradicts the pass marker
             (Assessment is PASS WITH CONCERNS or FAIL, or Status is
             DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED).
  INCOMPLETE the pass class marker is missing one of the two mandated fields:
             an `Assessment:` line, or an evidence line carrying a command and
             its result (`**Commands run:**`, qa-agent's own field name, or the
             generic `**Verification:**`).

On either, it injects `hookSpecificOutput.additionalContext` naming the
routing target and the consequence. It does NOT block: the audit already ran
and blocking a returned verdict throws the whole audit away. The nudge lands
in the orchestrator's context at the routing decision, which is the only
moment it can change anything.

What it reads, and what it deliberately does not
------------------------------------------------
The Agent tool's result dict carries the DISPATCH PROMPT next to the return
(measured: 266 of 266 real agent results under ~/.claude/projects have a
`prompt` key beside `content`). The dispatch prompt routinely quotes the
marker names and the return template, so scanning it would let an
orchestrator's own prompt satisfy the evidence check, and would attribute a
pass marker to a return that never emitted one. So: when the response carries
a `content` key, ONLY `content` is read; `prompt` and `description` are never
read.

False positive control (calibrated against the real 47 return population,
/tmp/jev-harness/pass_markers.json):
- closed fenced code blocks are stripped, so an agent that QUOTES the contract
  (a session editing these very files) is not flagged. An UNCLOSED fence is
  left alone rather than swallowing the rest of the return.
- the verdict is the LAST `Assessment:` line, not the first, and the template
  echo `PASS / PASS WITH CONCERNS / FAIL` is never read as a verdict.
- prose that merely mentions "PASS WITH CONCERNS" (skeptic pass 4 text says
  exactly that) is ignored: only the Assessment FIELD line counts.
- the concern test is the PHRASE "WITH CONCERNS", not the word "concern", so
  `Assessment: PASS (no concerns)` is a clean pass.
Result on the real population: 23 of 47 flagged MISMATCH, 1 flagged
INCOMPLETE, 23 clean passes through untouched, 0 hand checked false positives.

Scope, deliberately narrow
--------------------------
qa-agent's pass marker only. `## OUTCOMES PASSED` (outcomes-grader),
`## UI VERIFIED` (live-test) and `## IMPLEMENTATION COMPLETE` are untouched.

Codex: this hook has an `Agent|Task` matcher, and codex-sync.py drops those
deliberately (Codex has no subagent tool). The CONTRACT half of the fix does
reach Codex, through the generated `~/.codex/agents/qa-agent.toml`.

Fail open contract: this hook runs on every Agent/Task return in EVERY session
on this machine. Any internal error, malformed stdin, unknown payload or
signal (BaseException) => exit 0, no output. It must never exit non zero.

Wiring. `~/.claude/settings.json` is gitignored on this machine, so the entry
below is NOT carried by any commit. Recreate it by hand on a fresh checkout,
under `hooks.PostToolUse`:

    {"matcher": "Agent|Task",
     "hooks": [{"type": "command",
                "command": "python3 /Users/zalo/.claude/hooks/qa-verdict-guard.py",
                "timeout": 10}]}

Tests: python3 ~/.claude/hooks/qa-verdict-guard.test.py
"""
import json
import re
import sys

AGENT_TOOLS = ("Task", "Agent")

# Never read: the dispatch prompt quotes markers and field names, and the
# description is the caller's words, not the agent's verdict.
SKIP_KEYS = ("prompt", "description", "tool_use_id", "id", "type", "usage",
             "uuid", "agentId", "agentType", "resolvedModel", "outputFile")

# The qa-agent pass marker, as an H2 at the start of a line. A trailing tail
# (the "## VERIFICATION PASSED WITH CONCERNS" superstring shape) is captured so
# it can be reported: that marker is not in the registry, and under a prefix
# match it would read as a clean pass, which is the defect this hook exists for.
PASS_MARKER = re.compile(
    r"(?m)^[ \t]{0,3}##[ \t]*\**[ \t]*VERIFICATION[ \t]+PASSED\**[ \t]*(.*)$")

# Field lines. The leading class absorbs list bullets, quote markers, table
# pipes and bold stars, all of which appear in the real population.
ASSESSMENT = re.compile(r"(?mi)^[\s>*\-|#]{0,8}\**\s*Assessment\**\s*[:|]\**\s*(.+)$")
STATUS = re.compile(r"(?mi)^[\s>*\-|#]{0,8}\**\s*Status\**\s*[:|]\**\s*(.+)$")

# Two accepted forms, and nothing else. The real population carries this field
# both as "**Commands run:** <value>" and as a bare "### Commands run" heading
# with the commands in a numbered list underneath. The alternation must NOT
# swallow the marker line itself: "## VERIFICATION PASSED" has neither a colon
# nor an end of line after the field word, so it does not match.
EVIDENCE = re.compile(
    r"(?mi)^[\s>*\-|#]{0,8}\**\s*(?:Verification|Commands?\s+run)\**\s*"
    r"(?:[:|]\**[ \t]*(?P<inline>.*)$|[ \t]*\**[ \t]*$)"
)

# The qa-agent.md template line, echoed verbatim by an agent that pasted the
# output format instead of filling it in. Never a verdict.
TEMPLATE_ECHO = re.compile(r"(?i)PASS\s*/\s*PASS\s+WITH\s+CONCERNS\s*/\s*FAIL")

# Only CLOSED fences are stripped. An unclosed fence used to swallow every
# marker after it, which is a silent false negative on the one tier that
# matters.
FENCE = re.compile(r"(?ms)^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}\1[ \t]*$")

CONCERN_STATUSES = ("DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED")
OWN_BRANCH_STATUSES = ("NEEDS_CONTEXT", "BLOCKED")

# An evidence line whose value is one of these carries no command and no
# result, so it does not satisfy the Iron Law.
EMPTY_EVIDENCE = re.compile(
    r"(?i)^\W*(none|n/?a|nil|nothing|not\s+applicable|no\s+commands?)\b")

# A field line directly under an empty evidence field means the evidence field
# was left blank, not filled in by a list underneath it.
NEXT_FIELD = re.compile(
    r"(?i)^[*_#>\s]*(Files\s+reviewed|Status|Summary|Assessment|Concerns|"
    r"Blockers|Verification|Commands?\s+run|Files\s+changed)\**\s*[:|]")

MAX_BODY = 600000
MAX_QUOTE = 160


def collect_text(node, out, budget, depth=0):
    """Collect every string in a tool_response, shape agnostically.

    The Agent tool's response shape is not pinned by any contract we own, so
    this handles a plain string, {content: [...]}, nested blocks, and degrades
    to "found no marker" rather than to a crash on an unknown future shape.
    `budget` is a one element list used as a running total, so the size cap
    costs O(1) per node instead of re-summing `out` on every call.
    """
    if depth > 8 or budget[0] > MAX_BODY:
        return
    if isinstance(node, str):
        out.append(node)
        budget[0] += len(node)
    elif isinstance(node, list):
        for x in node:
            collect_text(x, out, budget, depth + 1)
    elif isinstance(node, dict):
        for k, v in node.items():
            if k in SKIP_KEYS:
                continue
            collect_text(v, out, budget, depth + 1)


def return_text(resp):
    """The agent's RETURN only, never the dispatch prompt beside it."""
    parts = []
    budget = [0]
    if isinstance(resp, dict) and resp.get("content") is not None:
        collect_text(resp["content"], parts, budget)
    else:
        collect_text(resp, parts, budget)
    return "\n".join(parts)[:MAX_BODY]


def strip_fences(text):
    return FENCE.sub("\n", text)


def clean(value):
    """Strip markdown emphasis without mangling the value.

    Underscores are stripped only at the edges: DONE_WITH_CONCERNS must survive
    verbatim so the nudge can quote the agent's own words back at it.
    """
    value = re.sub(r"[`*]", "", value or "")
    return re.sub(r"^[\s_]+|[\s_]+$", "", value)


def norm_status(value):
    """DONE WITH CONCERNS, DONE-WITH-CONCERNS and DONE\\_WITH\\_CONCERNS are all
    the same status. Collapse the separators before comparing."""
    return re.sub(r"[\\\s_\-]+", "_", (value or "").upper())


def last_field(rx, text, skip=None):
    vals = [clean(m.group(1)) for m in rx.finditer(text)]
    if skip:
        vals = [v for v in vals if not skip.search(v)]
    vals = [v for v in vals if v]
    return vals[-1] if vals else None


def _has_content_after(body, match):
    """True when the commands sit on the lines BELOW a blank field line.

    A sub-heading between the field and its list is allowed (real returns write
    "**Commands run:**" then "#### Tests" then the list); what disqualifies the
    field is the NEXT contract field starting right underneath it, which means
    the evidence field was simply left blank.
    """
    tail = body[match.end():match.end() + 400].lstrip()
    for line in tail.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        return not NEXT_FIELD.match(line)
    return False


def _q(value):
    value = " ".join((value or "").split())
    return value[:MAX_QUOTE] + ("..." if len(value) > MAX_QUOTE else "")


def evaluate(body):
    """Return (kind, reasons, status) or None. kind is mismatch or incomplete."""
    m = PASS_MARKER.search(body)
    if not m:
        return None
    tail = clean(m.group(1))

    assessment = last_field(ASSESSMENT, body, skip=TEMPLATE_ECHO)
    status_raw = last_field(STATUS, body)
    status = norm_status(status_raw)
    hit_status = next((c for c in CONCERN_STATUSES if status.startswith(c)), None)

    has_evidence = False
    for match in EVIDENCE.finditer(body):
        value = clean(match.group("inline") or "")
        if value:
            if not EMPTY_EVIDENCE.match(value):
                has_evidence = True
                break
        elif _has_content_after(body, match):
            has_evidence = True
            break

    reasons = []
    # PASS_WITH_CONCERNS, PASS-WITH-CONCERNS and PASS WITH CONCERN are the same
    # verdict; FAILED / FAILURE / FAILING are the same as FAIL.
    up = norm_status(assessment)
    if assessment and (re.match(r"^\W*FAIL", up) or re.match(r"^\W*NOT_PASS", up)):
        reasons.append("its body says `Assessment: %s`" % _q(assessment))
    elif assessment and "WITH_CONCERN" in up:
        reasons.append("its body says `Assessment: %s`" % _q(assessment))
    if hit_status:
        reasons.append("its body says `Status: %s`" % _q(status_raw))
    if tail:
        reasons.append(
            "its marker line reads `## VERIFICATION PASSED %s`, which is not a "
            "registered marker" % _q(tail))
    if reasons:
        return ("mismatch", reasons, hit_status)

    missing = []
    if not assessment:
        missing.append("an `Assessment:` line (PASS / PASS WITH CONCERNS / FAIL)")
    if not has_evidence:
        missing.append("a `**Commands run:**` or `**Verification:**` line carrying a "
                       "command and its result")
    if missing:
        return ("incomplete", missing, hit_status)
    return None


MISMATCH_NUDGE = (
    "qa-verdict-guard: this return carries `## VERIFICATION PASSED` but {why}. "
    "Per ~/.claude/rules/agent-contracts.md this is NOT a clean pass. {route} "
    "Do not report QA as passed.\n"
    "Consequence, pick exactly one by reading the concern:\n"
    "1. it names a finding: fix CRITICAL and HIGH, defer MEDIUM and LOW as the "
    "ISSUES FOUND branch already does.\n"
    "2. it names a check that did not run (a mock stood in for the real system, a "
    "coverage claim with no denominator, a surface not live verified): run that one "
    "check yourself now. If you cannot, cap the run's terminal claim at "
    "CODE-COMPLETE, NOT LIVE-VERIFIED and list the unproven surface first in "
    "Remaining Issues.\n"
    "3. it is an observation only: say it to the user in the report and proceed.\n"
    "Then STOP this audit round: do not re dispatch the same audit for the same "
    "concern, and do not loop waiting for the concern to disappear. The verdict is "
    "already in."
)

ROUTE_ISSUES = "Route it as `## ISSUES FOUND`."
ROUTE_OWN = ("Route it to the `{status}` branch, not to the clean pass branch "
             "(supply what is missing and re dispatch for NEEDS_CONTEXT, Tiered "
             "Decision Protocol for BLOCKED).")

INCOMPLETE_NUDGE = (
    "qa-verdict-guard: this return carries `## VERIFICATION PASSED` but is missing "
    "{what}. Per ~/.claude/rules/agent-contracts.md a pass class marker requires "
    "both, and a return missing either is treated as NOT passing. Route it as "
    "`## ISSUES FOUND` with the concern 'contract fields missing', or re dispatch "
    "that one agent ONCE with the field names quoted. Do not report QA as passed "
    "on an unevidenced marker."
)


def build_nudge(kind, detail, status):
    if kind == "mismatch":
        route = (ROUTE_OWN.format(status=status)
                 if status in OWN_BRANCH_STATUSES else ROUTE_ISSUES)
        return MISMATCH_NUDGE.format(why=", and ".join(detail), route=route)
    return INCOMPLETE_NUDGE.format(what=" and ".join(detail))


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    data = json.loads(raw)
    if not isinstance(data, dict):
        return
    if data.get("tool_name") not in AGENT_TOOLS:
        return
    resp = data.get("tool_response")
    if resp is None:
        return
    body = return_text(resp)
    if "VERIFICATION" not in body:
        return
    verdict = evaluate(strip_fences(body))
    if not verdict:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": data.get("hook_event_name") or "PostToolUse",
        "additionalContext": build_nudge(*verdict),
    }}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
