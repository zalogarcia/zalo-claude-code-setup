#!/usr/bin/env python3
"""Tests for qa-verdict-guard.py.

Run: python3 ~/.claude/hooks/qa-verdict-guard.test.py
Must stay green before touching ~/.claude/settings.json wiring.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-verdict-guard.py")

PASSED = 0
FAILED = 0


def run(payload, raw=None):
    """Run the hook on a payload. Returns (exit_code, stdout, stderr)."""
    data = raw if raw is not None else json.dumps(payload)
    p = subprocess.run(
        [sys.executable, HOOK],
        input=data,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return p.returncode, p.stdout, p.stderr


def agent_payload(body, tool="Task", shape="list"):
    if shape == "list":
        resp = {"content": [{"type": "text", "text": body}]}
    elif shape == "str":
        resp = body
    elif shape == "nested":
        resp = {"content": [{"type": "text", "text": ""}, {"type": "text", "text": body}]}
    else:
        raise ValueError(shape)
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"subagent_type": "qa-agent", "prompt": "audit this"},
        "tool_response": resp,
    }


def check(name, cond, extra=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("  ok   %s" % name)
    else:
        FAILED += 1
        print("  FAIL %s %s" % (name, extra))


def nudge_of(out):
    """Return the additionalContext string, or None."""
    if not out.strip():
        return None
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return None
    return ((d.get("hookSpecificOutput") or {}).get("additionalContext")) or None


def expect_silent(name, payload, raw=None):
    code, out, err = run(payload, raw)
    check(name, code == 0 and nudge_of(out) is None,
          "code=%s out=%r" % (code, out[:200]))


def expect_nudge(name, payload, must_contain=()):
    code, out, err = run(payload)
    n = nudge_of(out)
    if n is None:
        check(name, False, "no nudge emitted (code=%s out=%r)" % (code, out[:200]))
        return
    missing = [s for s in must_contain if s not in n]
    check(name, code == 0 and not missing, "missing=%s nudge=%r" % (missing, n[:300]))


CLEAN = """### Verdict

- Total: 0 findings (Critical: 0, High: 0, Medium: 0, Low: 0)
- Files reviewed: src/a.ts
- Assessment: PASS

## VERIFICATION PASSED

**Status:** DONE

**Commands run:** `npx vitest run` -> 42 passed
"""

CONCERNS = CLEAN.replace("Assessment: PASS", "Assessment: PASS WITH CONCERNS (DB surface not live verified)")
CONCERNS = CONCERNS.replace("**Status:** DONE", "**Status:** DONE_WITH_CONCERNS")

print("qa-verdict-guard tests")
print("-" * 60)

# --- 1. the core defect -----------------------------------------------------
expect_nudge("concerned verdict under a pass marker is flagged", agent_payload(CONCERNS),
             ("ISSUES FOUND", "PASS WITH CONCERNS"))
expect_silent("clean pass passes through silently", agent_payload(CLEAN))

fail_body = CLEAN.replace("Assessment: PASS", "Assessment: FAIL, the invariant does not exist")
expect_nudge("FAIL under a pass marker is flagged", agent_payload(fail_body), ("ISSUES FOUND",))

status_only = CLEAN.replace("**Status:** DONE", "**Status:** DONE_WITH_CONCERNS")
expect_nudge("DONE_WITH_CONCERNS status under a pass marker is flagged",
             agent_payload(status_only), ("ISSUES FOUND", "DONE_WITH_CONCERNS"))

bold_status = CLEAN.replace("**Status:** DONE", "**Status:** __DONE_WITH_CONCERNS__")
expect_nudge("underscore-bolded status is quoted back without mangling",
             agent_payload(bold_status), ("DONE_WITH_CONCERNS",))

blocked_status = CLEAN.replace("**Status:** DONE", "**Status:** BLOCKED")
expect_nudge("BLOCKED status under a pass marker is flagged", agent_payload(blocked_status))

# --- 2. the two mandated fields --------------------------------------------
no_assess = CLEAN.replace("- Assessment: PASS\n", "")
expect_nudge("pass marker with no Assessment line is flagged",
             agent_payload(no_assess), ("Assessment:",))

no_evidence = CLEAN.replace("**Commands run:** `npx vitest run` -> 42 passed", "")
expect_nudge("pass marker with no evidence line is flagged",
             agent_payload(no_evidence), ("Commands run",))

verif_named = CLEAN.replace("**Commands run:**", "**Verification:**")
expect_silent("the generic **Verification:** field satisfies the evidence rule",
              agent_payload(verif_named))

empty_evidence = CLEAN.replace("**Commands run:** `npx vitest run` -> 42 passed",
                               "**Commands run:** none")
expect_nudge("an evidence line saying none is flagged", agent_payload(empty_evidence))

heading_form = CLEAN.replace(
    "**Commands run:** `npx vitest run` -> 42 passed",
    "### Commands run\n\n1. `git status --porcelain` -> clean\n2. `npx vitest run` -> 42 passed")
expect_silent("a bare '### Commands run' heading with the commands underneath counts as evidence",
              agent_payload(heading_form))

bare_heading_empty = CLEAN.replace(
    "**Commands run:** `npx vitest run` -> 42 passed", "### Commands run")
expect_nudge("a '### Commands run' heading with nothing under it is flagged",
             agent_payload(bare_heading_empty))

# --- 3. no false positives --------------------------------------------------
prose_fp = CLEAN.replace(
    "### Verdict",
    "Skeptic pass 4: if any sub check was skipped the verdict is PASS WITH CONCERNS\n"
    "at best, never a clean PASS. No sub check was skipped here.\n\n### Verdict")
expect_silent("prose mentioning PASS WITH CONCERNS does not false positive",
              agent_payload(prose_fp))

fenced = ("Here is the contract text I edited:\n\n```markdown\n"
          "## VERIFICATION PASSED\n\n- Assessment: PASS WITH CONCERNS\n```\n\n"
          "Done editing the file.\n")
expect_silent("a marker quoted inside a fenced code block is ignored",
              agent_payload(fenced))

template_echo = CLEAN.replace("- Assessment: PASS",
                              "- Assessment: PASS / PASS WITH CONCERNS / FAIL\n- Assessment: PASS")
expect_silent("the echoed template line is ignored, the real verdict wins",
              agent_payload(template_echo))

two_assess = CLEAN.replace("- Assessment: PASS",
                           "- Assessment: PASS WITH CONCERNS\n\n(revised after re check)\n\n- Assessment: PASS")
expect_silent("the LAST Assessment line is the verdict", agent_payload(two_assess))

# --- 4. out of scope stays untouched ---------------------------------------
expect_silent("## ISSUES FOUND is already routed, no nudge",
              agent_payload(CONCERNS.replace("## VERIFICATION PASSED", "## ISSUES FOUND")))
expect_silent("## OUTCOMES PASSED belongs to outcomes-grader, untouched",
              agent_payload(CONCERNS.replace("## VERIFICATION PASSED", "## OUTCOMES PASSED")))
expect_silent("## UI VERIFIED belongs to live-test, untouched",
              agent_payload(CONCERNS.replace("## VERIFICATION PASSED", "## UI VERIFIED")))
expect_silent("a return with no marker is untouched",
              agent_payload("I read the files and everything looks fine."))
expect_silent("a non agent tool is untouched", agent_payload(CONCERNS, tool="Bash"))

# --- 5. the superstring hazard ---------------------------------------------
superstring = CONCERNS.replace("## VERIFICATION PASSED", "## VERIFICATION PASSED WITH CONCERNS")
expect_nudge("an unregistered superstring marker is flagged, not read as a clean pass",
             agent_payload(superstring), ("ISSUES FOUND",))

# --- 6. payload shapes ------------------------------------------------------
expect_nudge("tool_response as a plain string is parsed",
             agent_payload(CONCERNS, shape="str"), ("ISSUES FOUND",))
expect_nudge("tool_response with several content blocks is parsed",
             agent_payload(CONCERNS, shape="nested"), ("ISSUES FOUND",))

# --- 6b. defects found by the qa-agent audit of this change (2026-09-19) ----
# Each case below failed before the fix; they are the regression set.

# the dispatch prompt sits beside the return in the real Agent result and must
# never be read (measured: 266 of 266 real agent results carry a prompt key)
real_shape = {
    "hook_event_name": "PostToolUse", "tool_name": "Task",
    "tool_input": {"subagent_type": "general-purpose"},
    "tool_response": {
        "status": "completed",
        "prompt": ("Emit exactly one of these markers:\n## VERIFICATION PASSED\n"
                   "## ISSUES FOUND\n## BLOCKED\n\n**Verification:** [what was tested]\n"
                   "- Assessment: PASS\n"),
        "agentId": "abc123", "agentType": "general-purpose",
        "content": [{"type": "text", "text":
                     "## IMPLEMENTATION COMPLETE\n\n**Status:** DONE\n"}],
        "totalTokens": 1234,
    },
}
expect_silent("the dispatch prompt is never read as the return", real_shape)

prompt_hides_gap = {
    "hook_event_name": "PostToolUse", "tool_name": "Task",
    "tool_response": {
        "prompt": "**Verification:** [what was tested + result]\n- Assessment: PASS\n",
        "content": [{"type": "text", "text":
                     "## VERIFICATION PASSED\n\n**Status:** DONE\n"}],
    },
}
expect_nudge("a prompt quoting the mandated fields cannot satisfy them for the return",
             prompt_hides_gap, ("Assessment:",))

# a clean PASS whose tail merely contains the word "concern"
for tail in ("PASS (no concerns)", "PASS. No concerns beyond LOW.",
             "PASS, zero concerns raised"):
    expect_silent("clean verdict %r is not flagged" % tail,
                  agent_payload(CLEAN.replace("Assessment: PASS", "Assessment: " + tail)))

# ...but the phrase itself is caught wherever it sits in the value
expect_nudge("Overall: PASS WITH CONCERNS is caught even with a prefix",
             agent_payload(CLEAN.replace("Assessment: PASS",
                                         "Assessment: Overall PASS WITH CONCERNS")),
             ("ISSUES FOUND",))

# realistic spellings of the two strings the hook keys on
for variant in ("FAILED", "NOT PASS", "Failed, the invariant does not exist"):
    expect_nudge("Assessment %r is caught" % variant,
                 agent_payload(CLEAN.replace("Assessment: PASS", "Assessment: " + variant)),
                 ("ISSUES FOUND",))

for variant in ("DONE WITH CONCERNS", "DONE-WITH-CONCERNS", "DONE\\_WITH\\_CONCERNS"):
    expect_nudge("Status %r is caught" % variant,
                 agent_payload(CLEAN.replace("**Status:** DONE", "**Status:** " + variant)),
                 ("ISSUES FOUND",))

# NEEDS_CONTEXT and BLOCKED have their own branches, the nudge must say so
code, out, err = run(agent_payload(CLEAN.replace("**Status:** DONE",
                                                 "**Status:** NEEDS_CONTEXT")))
n = nudge_of(out) or ""
check("NEEDS_CONTEXT is routed to its own branch, not to ISSUES FOUND",
      "NEEDS_CONTEXT` branch" in n and "Route it as `## ISSUES FOUND`." not in n, repr(n[:200]))
code, out, err = run(agent_payload(blocked_status))
n = nudge_of(out) or ""
check("BLOCKED is routed to its own branch", "BLOCKED` branch" in n, repr(n[:200]))

# an evidence field left blank with the next field right under it
blank_then_field = CLEAN.replace(
    "**Commands run:** `npx vitest run` -> 42 passed",
    "**Commands run:**\n\n**Files reviewed:** src/a.ts")
expect_nudge("a blank evidence field followed by the next field is not evidence",
             agent_payload(blank_then_field), ("Commands run",))

no_commands_prose = CLEAN.replace("**Commands run:** `npx vitest run` -> 42 passed",
                                  "**Commands run:** No commands, static review only")
expect_nudge("'No commands, static review only' is not evidence",
             agent_payload(no_commands_prose))

# an UNCLOSED fence must not swallow the real marker that follows it
unclosed = ("Here is a snippet:\n\n```ts\nconst x = 1\n\n" + CONCERNS)
expect_nudge("an unclosed fence does not hide the marker after it",
             agent_payload(unclosed), ("ISSUES FOUND",))

# performance: the size cap must be O(1) per node, not O(n^2)
import time
many = {"hook_event_name": "PostToolUse", "tool_name": "Task",
        "tool_response": {"content": [{"type": "text", "text": "chunk %d" % i}
                                      for i in range(12000)] + [
                              {"type": "text", "text": CONCERNS}]}}
t0 = time.time()
code, out, err = run(many)
elapsed = time.time() - t0
check("12k content blocks finish well inside the 10s hook timeout (%.2fs)" % elapsed,
      code == 0 and elapsed < 5.0, "elapsed=%.2f code=%s" % (elapsed, code))

# --- 6c. defects found by the round 2 re-audit (2026-09-19) ----------------

for variant in ("PASS_WITH_CONCERNS", "PASS-WITH-CONCERNS", "PASS WITH CONCERN"):
    expect_nudge("Assessment %r is caught" % variant,
                 agent_payload(CLEAN.replace("Assessment: PASS", "Assessment: " + variant)),
                 ("ISSUES FOUND",))

for variant in ("FAILURE", "FAILING"):
    expect_nudge("Assessment %r is caught" % variant,
                 agent_payload(CLEAN.replace("Assessment: PASS", "Assessment: " + variant)),
                 ("ISSUES FOUND",))

bold_marker = CONCERNS.replace("## VERIFICATION PASSED", "## **VERIFICATION PASSED**")
expect_nudge("a bold-wrapped marker is still seen",
             agent_payload(bold_marker), ("ISSUES FOUND",))

table_form = ("| Field | Value |\n| --- | --- |\n| Assessment | PASS WITH CONCERNS |\n"
              "| Commands run | `npx vitest run` -> 42 passed |\n\n"
              "## VERIFICATION PASSED\n\n**Status:** DONE\n")
expect_nudge("a table-form Assessment cell is read",
             agent_payload(table_form), ("ISSUES FOUND",))

table_clean = table_form.replace("| Assessment | PASS WITH CONCERNS |", "| Assessment | PASS |")
expect_silent("a table-form clean pass with table-form evidence is silent",
              agent_payload(table_clean))

subheading_evidence = CLEAN.replace(
    "**Commands run:** `npx vitest run` -> 42 passed",
    "**Commands run:**\n\n#### Tests\n\n- `npx vitest run` -> 42 passed")
expect_silent("a sub-heading between a blank evidence field and its list is allowed",
              agent_payload(subheading_evidence))

prose_list = CLEAN.replace(
    "**Commands run:** `npx vitest run` -> 42 passed",
    "**Commands run:**\n\n- Verification of the token path: `npx vitest run` -> 42 passed")
expect_silent("a list line starting with the word Verification is not a field header",
              agent_payload(prose_list))

# --- 7. fail open -----------------------------------------------------------
expect_silent("malformed stdin exits 0 silently", None, raw="{not json")
expect_silent("empty stdin exits 0 silently", None, raw="")
expect_silent("payload with no tool_response exits 0 silently",
              {"hook_event_name": "PostToolUse", "tool_name": "Task"})
expect_silent("payload with a null tool_response exits 0 silently",
              {"hook_event_name": "PostToolUse", "tool_name": "Task", "tool_response": None})

huge = {"hook_event_name": "PostToolUse", "tool_name": "Task",
        "tool_response": {"content": [{"type": "text", "text": CONCERNS + ("x" * 400000)}]}}
code, out, err = run(huge)
check("a very large return still exits 0", code == 0, "code=%s" % code)

# --- 8. the nudge names the consequence ------------------------------------
code, out, err = run(agent_payload(CONCERNS))
n = nudge_of(out) or ""
check("nudge names the routing target", "ISSUES FOUND" in n)
check("nudge forbids reporting QA as passed", "not a clean pass" in n.lower())
check("nudge names the three way consequence", "did not run" in n.lower())
check("nudge forbids re dispatching the same audit", "re dispatch" in n.lower() or "redispatch" in n.lower())
DASHES = "\u2012\u2013\u2014\u2015"  # figure, en, em, horizontal bar
check("nudge carries no em or en dashes", not any(c in n for c in DASHES), repr(n[:120]))

print("-" * 60)
print("passed %d, failed %d" % (PASSED, FAILED))
sys.exit(1 if FAILED else 0)
