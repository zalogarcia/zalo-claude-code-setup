#!/usr/bin/env python3
"""Behaviour suite for codex-shim.

Run: python3 ~/.claude/hooks/codex-shim.test.py
The shim translates a Codex hook payload into the Claude shape an unmodified
Claude hook expects. Exit 2 is a deny; exit 0 with silence is a pass-through.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile

SHIM = os.path.expanduser("~/.claude/hooks/codex-shim.py")

_dirs = []
passed = failed = 0


def workdir():
    d = tempfile.mkdtemp(prefix="codex-shim-test-")
    _dirs.append(d)
    return d


def check(label, ok):
    global passed, failed
    if ok:
        passed += 1
        print("  ok   %s" % label)
    else:
        failed += 1
        print("  FAIL %s" % label)


def spy(d, name="spy.py", exit_code=0, stdout="", stderr=""):
    """A stand-in hook that records every payload it is handed."""
    rec = os.path.join(d, name + ".jsonl")
    src = os.path.join(d, name)
    with open(src, "w", encoding="utf-8") as f:
        f.write(
            "import json,sys\n"
            "raw=sys.stdin.read()\n"
            "open(%r,'a').write(raw.replace(chr(10),' ')+chr(10))\n"
            "sys.stdout.write(%r)\n"
            "sys.stderr.write(%r)\n"
            "sys.exit(%d)\n" % (rec, stdout, stderr, exit_code)
        )
    return src, rec


def deny_on(d, needle, name="denier.py"):
    """A stand-in hook that exits 2 only for payloads containing `needle`."""
    rec = os.path.join(d, name + ".jsonl")
    src = os.path.join(d, name)
    with open(src, "w", encoding="utf-8") as f:
        f.write(
            "import sys\n"
            "raw=sys.stdin.read()\n"
            "open(%r,'a').write(raw.replace(chr(10),' ')+chr(10))\n"
            "if %r in raw:\n"
            "    sys.stderr.write('DENIED by test hook')\n"
            "    sys.exit(2)\n"
            "sys.exit(0)\n" % (rec, needle)
        )
    return src, rec


def run(payload, wrapped_argv=None, b64=None):
    argv = ["python3", SHIM]
    if b64 is not None:
        argv += ["--b64", base64.b64encode(b64.encode()).decode()]
    else:
        argv += ["--"] + (wrapped_argv or [])
    p = subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def recorded(rec):
    if not os.path.exists(rec):
        return []
    return [json.loads(l) for l in open(rec, encoding="utf-8") if l.strip()]


def patch_payload(patch, event="PreToolUse", cwd="/tmp/proj", **extra):
    p = {
        "session_id": "sess-1",
        "turn_id": "turn-1",
        "cwd": cwd,
        "hook_event_name": event,
        "model": "gpt-5.6-sol",
        "tool_name": "apply_patch",
        "tool_use_id": "exec-1",
        "tool_input": {"command": patch},
    }
    p.update(extra)
    return p


ADD = (
    "*** Begin Patch\n"
    "*** Add File: /tmp/proj/new.md\n"
    "+hello world\n"
    "+second line\n"
    "*** End Patch"
)
UPDATE = (
    "*** Begin Patch\n"
    "*** Update File: rel/thing.ts\n"
    "@@ ctx\n"
    " unchanged\n"
    "-old line\n"
    "+new line\n"
    "*** End Patch"
)
MULTI = (
    "*** Begin Patch\n"
    "*** Add File: a.txt\n"
    "+alpha\n"
    "*** Add File: b.txt\n"
    "+bravo\n"
    "*** End Patch"
)
DELETE = "*** Begin Patch\n*** Delete File: gone.txt\n*** End Patch"
MOVE = (
    "*** Begin Patch\n"
    "*** Update File: old/name.md\n"
    "*** Move to: new/name.md\n"
    "+moved text\n"
    "*** End Patch"
)


def main():
    # 1. Add File becomes a Write payload with content
    d = workdir()
    src, rec = spy(d)
    rc, out, err = run(patch_payload(ADD), ["python3", src])
    got = recorded(rec)
    check("1: Add File -> exactly one payload", len(got) == 1)
    check("2: Add File -> tool_name Write",
          got and got[0]["tool_name"] == "Write")
    check("3: Add File -> absolute file_path",
          got and got[0]["tool_input"]["file_path"] == "/tmp/proj/new.md")
    check("4: Add File -> content is the added lines only",
          got and got[0]["tool_input"]["content"] == "hello world\nsecond line")
    check("5: clean run exits 0", rc == 0)

    # 2. Update File becomes an Edit payload, relative path resolved against cwd
    d = workdir()
    src, rec = spy(d)
    run(patch_payload(UPDATE), ["python3", src])
    got = recorded(rec)
    check("6: Update File -> tool_name Edit",
          got and got[0]["tool_name"] == "Edit")
    check("7: relative path resolved against cwd",
          got and got[0]["tool_input"]["file_path"] == "/tmp/proj/rel/thing.ts")
    check("8: new_string is the + lines",
          got and got[0]["tool_input"]["new_string"] == "new line")
    check("9: old_string is the - lines",
          got and got[0]["tool_input"]["old_string"] == "old line")
    check("10: context lines are not counted as written text",
          got and "unchanged" not in got[0]["tool_input"]["new_string"])

    # 3. A multi-file patch fans out one invocation per file
    d = workdir()
    src, rec = spy(d)
    run(patch_payload(MULTI), ["python3", src])
    got = recorded(rec)
    paths = [g["tool_input"]["file_path"] for g in got]
    check("11: 2-file patch -> 2 invocations", len(got) == 2)
    check("12: both files present",
          paths == ["/tmp/proj/a.txt", "/tmp/proj/b.txt"])

    # 4. Delete File carries no written text
    d = workdir()
    src, rec = spy(d)
    run(patch_payload(DELETE), ["python3", src])
    got = recorded(rec)
    check("13: Delete File -> Edit with empty new_string",
          got and got[0]["tool_name"] == "Edit"
          and got[0]["tool_input"]["new_string"] == "")

    # 5. Move to: judges the destination path
    d = workdir()
    src, rec = spy(d)
    run(patch_payload(MOVE), ["python3", src])
    got = recorded(rec)
    check("14: Move to -> destination path is what the guard sees",
          got and got[0]["tool_input"]["file_path"] == "/tmp/proj/new/name.md")

    # 6. First deny wins and stops the fan-out
    d = workdir()
    src, rec = deny_on(d, "bravo")
    rc, out, err = run(patch_payload(MULTI), ["python3", src])
    check("15: a denying hook makes the shim exit 2", rc == 2)
    check("16: the deny reason reaches stderr", "DENIED by test hook" in err)
    check("17: fan-out stops at the deny", len(recorded(rec)) == 2)

    d = workdir()
    src, rec = deny_on(d, "alpha")
    rc, out, err = run(patch_payload(MULTI), ["python3", src])
    check("18: denying on the FIRST file skips the second",
          rc == 2 and len(recorded(rec)) == 1)

    # 7. A JSON deny on stdout is forwarded, not swallowed
    d = workdir()
    deny_json = json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": "nope"}})
    src, rec = spy(d, stdout=deny_json)
    rc, out, err = run(patch_payload(ADD), ["python3", src])
    check("19: JSON deny is forwarded verbatim", "permissionDecision" in out)

    # 8. Non-deny stdout from several files merges into ONE json object
    d = workdir()
    ctx = json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": "note"}})
    src, rec = spy(d, stdout=ctx)
    rc, out, err = run(patch_payload(MULTI, event="PostToolUse"), ["python3", src])
    parsed = json.loads(out.strip())
    check("20: merged stdout is a single JSON object",
          isinstance(parsed, dict) and "hookSpecificOutput" in parsed)

    # 9. A Bash payload is passed straight through, untouched
    d = workdir()
    src, rec = spy(d)
    bash = {"session_id": "s", "hook_event_name": "PreToolUse", "cwd": "/tmp",
            "tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    run(bash, ["python3", src])
    got = recorded(rec)
    check("21: Bash payload forwarded unchanged",
          got and got[0]["tool_name"] == "Bash"
          and got[0]["tool_input"]["command"] == "echo hi")

    # 10. An unparseable patch is forwarded, never dropped
    d = workdir()
    src, rec = spy(d)
    run(patch_payload("this is not a patch at all"), ["python3", src])
    got = recorded(rec)
    check("22: unparseable patch is forwarded verbatim (fail open)",
          len(got) == 1 and got[0]["tool_name"] == "apply_patch")

    # 11. Malformed stdin never wedges the caller
    p = subprocess.run(["python3", SHIM, "--", "true"],
                       input="not json{", capture_output=True, text=True)
    check("23: malformed stdin exits 0", p.returncode == 0)
    p = subprocess.run(["python3", SHIM], input="{}", capture_output=True, text=True)
    check("24: no wrapped command exits 0", p.returncode == 0)

    # 12. The --b64 form survives shell metacharacters
    d = workdir()
    marker = os.path.join(d, "b64.txt")
    cmd = "FILE=$(cat | python3 -c \"import json,sys;print(json.load(sys.stdin)['tool_input']['file_path'])\"); echo \"$FILE\" > %s" % marker
    rc, out, err = run(patch_payload(ADD), b64=cmd)
    got = open(marker).read().strip() if os.path.exists(marker) else ""
    check("25: --b64 wrapped one-liner receives the synthesized file_path",
          got == "/tmp/proj/new.md")

    # 13. Stop payloads get a Claude-shaped transcript built for them
    d = workdir()
    rollout = os.path.join(d, "rollout.jsonl")
    with open(rollout, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "session_meta", "payload": {}}) + "\n")
        f.write(json.dumps({"type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "<recommended_plugins>noise"}]}}) + "\n")
        f.write(json.dumps({"type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "the real brief"}]}}) + "\n")
    src, rec = spy(d, name="stopspy.py")
    stop = {"session_id": "stop-sess", "hook_event_name": "Stop", "cwd": d,
            "transcript_path": rollout, "last_assistant_message": "Next, I'll do the thing"}
    run(stop, ["python3", src])
    got = recorded(rec)
    tpath = got[0]["transcript_path"] if got else ""
    check("26: Stop transcript_path is rewritten", tpath != rollout)
    body = [json.loads(l) for l in open(tpath, encoding="utf-8") if l.strip()] if os.path.exists(tpath) else []
    kinds = [(b["type"], b["message"]["content"][0]["text"]) for b in body]
    check("27: synthetic Codex user messages are filtered out",
          all("recommended_plugins" not in t for _, t in kinds))
    check("28: the real user turn survives translation",
          ("user", "the real brief") in kinds)
    check("29: last_assistant_message is appended as the final assistant turn",
          kinds and kinds[-1] == ("assistant", "Next, I'll do the thing"))

    # 14. A patch payload also gets the translated transcript
    d = workdir()
    rollout = os.path.join(d, "r2.jsonl")
    with open(rollout, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "response_item", "payload": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "no em dashes please"}]}}) + "\n")
    src, rec = spy(d, name="patchspy.py")
    run(patch_payload(ADD, transcript_path=rollout), ["python3", src])
    got = recorded(rec)
    check("30: apply_patch payload gets a translated transcript",
          got and got[0]["transcript_path"] != rollout
          and os.path.exists(got[0]["transcript_path"]))

    # 15. QA finding 3: an oversized patch is REFUSED, never partially guarded
    d = workdir()
    src, rec = spy(d, name="bigspy.py")
    big = ["*** Begin Patch"]
    for i in range(45):
        big += ["*** Add File: f%d.md" % i, "+line %d" % i]
    big.append("*** End Patch")
    rc, out, err = run(patch_payload("\n".join(big)), ["python3", src])
    check("32: a patch over the file cap is denied, not truncated", rc == 2)
    check("33: the denial names the count and the cap",
          "45 files" in err and "40-file cap" in err)
    check("34: no guard ran at all on the oversized patch", recorded(rec) == [])

    # PostToolUse cannot un-write the file, so it checks what it can and says
    # loudly which files it did not check.
    d = workdir()
    src, rec = spy(d, name="postbig.py")
    rc, out, err = run(patch_payload("\n".join(big), event="PostToolUse"),
                       ["python3", src])
    check("32b: over the cap at PostToolUse checks the first N instead of refusing",
          rc == 0 and len(recorded(rec)) == 40)
    check("32c: and says plainly that the rest went unchecked",
          "were NOT" in err and "45 files" in err)

    d = workdir()
    src, rec = spy(d, name="okspy.py")
    ok = ["*** Begin Patch"]
    for i in range(40):
        ok += ["*** Add File: g%d.md" % i, "+line %d" % i]
    ok.append("*** End Patch")
    rc, out, err = run(patch_payload("\n".join(ok)), ["python3", src])
    check("35: exactly at the cap still fans out to every file",
          rc == 0 and len(recorded(rec)) == 40)

    # 16. QA finding 7: an unknown marker must not truncate the written text
    d = workdir()
    src, rec = spy(d, name="eofspy.py")
    eof = ("*** Begin Patch\n*** Add File: a.md\n+one\n"
           "*** End of File\n+two\n*** End Patch")
    run(patch_payload(eof), ["python3", src])
    got = recorded(rec)
    check("36: content after an unrecognised *** marker still reaches the guard",
          got and got[0]["tool_input"]["content"] == "one\ntwo")

    # 17. QA finding 6: the newly-seen synthetic Codex blocks are filtered
    d = workdir()
    rollout = os.path.join(d, "r3.jsonl")
    with open(rollout, "w", encoding="utf-8") as f:
        for text in ("<user_action>   <context>User initiated a review</context>",
                     '<image name=[Image #1] path="/tmp/x.png">',
                     "the actual brief"):
            f.write(json.dumps({"type": "response_item", "payload": {
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": text}]}}) + "\n")
    src, rec = spy(d, name="synthspy.py")
    run(patch_payload(ADD, transcript_path=rollout), ["python3", src])
    tp = recorded(rec)[0]["transcript_path"]
    body = [json.loads(l) for l in open(tp, encoding="utf-8") if l.strip()]
    texts = [b["message"]["content"][0]["text"] for b in body]
    check("37: <user_action> and <image ...> are filtered out",
          texts == ["the actual brief"])

    # 15. A missing transcript is left alone rather than invented
    d = workdir()
    src, rec = spy(d, name="notx.py")
    run(patch_payload(ADD, transcript_path="/nope/missing.jsonl"), ["python3", src])
    got = recorded(rec)
    check("31: a missing transcript path is passed through untouched",
          got and got[0]["transcript_path"] == "/nope/missing.jsonl")

    for x in _dirs:
        shutil.rmtree(x, ignore_errors=True)
    total = passed + failed
    print("\n%d/%d passed, %d failed" % (passed, total, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
