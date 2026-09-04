#!/usr/bin/env python3
"""Behaviour suite for codex-sync.

Run: python3 ~/.claude/scripts/codex-sync.test.py
Exercises the pure functions and the config-splice logic against fixtures. The
generators themselves are proven end to end by running `codex-sync.py all`
twice and seeing zero changes on the second pass.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT = os.path.expanduser("~/.claude/scripts/codex-sync.py")
spec = importlib.util.spec_from_file_location("codex_sync", SCRIPT)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

_dirs = []
passed = failed = 0


def check(label, ok):
    global passed, failed
    if ok:
        passed += 1
        print("  ok   %s" % label)
    else:
        failed += 1
        print("  FAIL %s" % label)


def workdir():
    d = tempfile.mkdtemp(prefix="codex-sync-test-")
    _dirs.append(d)
    return d


def main():
    # --- frontmatter ------------------------------------------------------
    meta, body = cs.frontmatter("---\nname: x\nmodel: fable\n---\n\nbody here\n")
    check("1: frontmatter reads scalars", meta == {"name": "x", "model": "fable"})
    check("2: frontmatter returns the body", body.strip() == "body here")

    nested = ("---\nname: fs\nmcpServers:\n  - a:\n      type: stdio\n"
              "effort: high\n---\nreal body\n")
    meta, body = cs.frontmatter(nested)
    check("3: nested YAML blocks do not corrupt the scalar keys",
          meta.get("name") == "fs" and meta.get("effort") == "high")
    check("4: nested YAML blocks stay out of the body",
          body.strip() == "real body" and "stdio" not in body)

    meta, body = cs.frontmatter("no frontmatter here\n")
    check("5: a file with no frontmatter is all body",
          meta == {} and body.startswith("no frontmatter"))

    meta, _ = cs.frontmatter("---\ndescription: 'it''s quoted'\n---\nb\n")
    check("6: single-quoted YAML scalars are unescaped",
          meta.get("description") == "it's quoted")

    # --- TOML emission ----------------------------------------------------
    check("7: toml_str escapes quotes and backslashes",
          cs.toml_str('a "b" \\ c') == '"a \\"b\\" \\\\ c"')
    check("8: toml_str escapes newlines",
          cs.toml_str("a\nb") == '"a\\nb"')
    check("9: toml_key quotes a key with a dot",
          cs.toml_key("n8n.api") == '"n8n.api"')
    check("10: toml_key leaves a plain key bare", cs.toml_key("n8n-api") == "n8n-api")

    lit = cs.toml_multiline("has a \\backslash and 'quotes'\n")
    check("11: multiline prefers the literal form so backslashes survive",
          lit.startswith("'''") and "\\backslash" in lit)
    esc = cs.toml_multiline("contains ''' inside\n")
    check("12: multiline falls back to basic when ''' appears",
          esc.startswith('"""'))

    import tomllib
    doc = "x = %s\n" % cs.toml_multiline("line1\nline2 with \\d regex\n")
    check("13: the emitted multiline round-trips through a TOML parser",
          tomllib.loads(doc)["x"] == "line1\nline2 with \\d regex\n")

    # --- config splice ----------------------------------------------------
    block = cs.BEGIN + "\nkey = 1\n" + cs.END + "\n"

    existing = '[projects."/tmp/a"]\ntrust_level = "trusted"\n'
    out = cs.splice_block(existing, block)
    check("14: a fresh file gets the block above the first table",
          out.index(cs.BEGIN) < out.index("[projects."))
    check("15: pre-existing tables survive verbatim",
          '[projects."/tmp/a"]\ntrust_level = "trusted"' in out)

    replaced = cs.splice_block(out, cs.BEGIN + "\nkey = 2\n" + cs.END + "\n")
    check("16: a second splice replaces rather than duplicates",
          replaced.count(cs.BEGIN) == 1 and "key = 2" in replaced
          and "key = 1" not in replaced)
    check("17: replacing preserves everything outside the block",
          '[projects."/tmp/a"]' in replaced)

    leading = 'model = "x"\n\n[projects."/tmp/a"]\ntrust_level = "trusted"\n'
    out = cs.splice_block(leading, block)
    check("18: root keys already in the file stay above the block",
          out.index('model = "x"') < out.index(cs.BEGIN))
    check("19: the spliced result is valid TOML",
          tomllib.loads(out).get("model") == "x" and tomllib.loads(out)["key"] == 1)

    out = cs.splice_block("", block)
    check("20: an empty config file is handled", cs.BEGIN in out and cs.END in out)

    # --- shim wrapping ----------------------------------------------------
    plain = cs.wrap_in_shim("python3 /Users/zalo/.claude/hooks/emdash-guard.py")
    check("21: a shell-safe command uses the readable -- form",
          " -- python3 " in plain and "--b64" not in plain)
    gnarly = cs.wrap_in_shim("FILE=$(cat | jq -r '.x'); echo \"$FILE\"")
    check("22: a command with shell metacharacters is base64 encoded",
          "--b64" in gnarly and "$(" not in gnarly)
    import base64
    encoded = gnarly.split("--b64 ", 1)[1]
    check("23: the base64 round-trips to the original command",
          base64.b64decode(encoded).decode() == "FILE=$(cat | jq -r '.x'); echo \"$FILE\"")

    check("24: hook timeouts are clamped to the Codex ceiling",
          cs.clamp(10000) == cs.MAX_HOOK_TIMEOUT and cs.clamp(15) == 15
          and cs.clamp(None) is None)

    # --- command body rewriting ------------------------------------------
    body = "intro\n\n@~/.claude/rules/gates.md\n\nuse $ARGUMENTS now\n"
    out = cs.rewrite_command_body(body)
    check("25: an @include line becomes a read instruction",
          "Read ~/.claude/rules/gates.md before proceeding" in out
          and "\n@~/" not in out)
    check("26: $ARGUMENTS is rewritten", "$ARGUMENTS" not in out
          and "the user's request text" in out)
    check("27: an email-like @ in prose is left alone",
          "@" in cs.rewrite_command_body("mail zalo@blackumbrella.app now\n"))

    meta, b = cs.frontmatter("---\ndescription: from frontmatter\n---\n# H1\n\npara\n")
    check("28: description prefers the frontmatter",
          cs.command_description(meta, b) == "from frontmatter")
    check("29: description falls back to the first prose paragraph",
          cs.command_description({}, "# H1\n\nthe first para\n\nsecond\n")
          == "the first para")

    # --- Sync.remove refuses to delete real directories -------------------
    d = workdir()
    victim = os.path.join(d, "realdir")
    os.makedirs(victim)
    open(os.path.join(victim, "content.txt"), "w").write("precious")
    s = cs.Sync()
    s.remove(victim)
    check("30: remove() refuses to delete a real directory",
          os.path.isfile(os.path.join(victim, "content.txt")))
    check("31: the refusal is reported, not silent",
          any("refused to delete" in n for n in s.notes))

    link = os.path.join(d, "alink")
    os.symlink(victim, link)
    s.remove(link)
    check("32: remove() does unlink a symlink",
          not os.path.lexists(link) and os.path.isdir(victim))

    # --- write_if_changed is the idempotency mechanism ---------------------
    d = workdir()
    p = os.path.join(d, "sub", "f.txt")
    s = cs.Sync()
    check("33: first write reports a change", s.write(p, "hello") is True)
    check("34: identical rewrite reports no change", s.write(p, "hello") is False)
    check("35: different content reports a change", s.write(p, "world") is True)
    s = cs.Sync(dry=True)
    check("36: a dry run reports the change without touching the file",
          s.write(p, "changed") is True and open(p).read() == "world")

    # --- --on-edit routing -------------------------------------------------
    def route(path):
        real = os.path.realpath(os.path.expanduser(path))
        t = list(cs.WATCHED_EXACT.get(real) or [])
        if not t:
            for dd, suffix, tt in cs.WATCHED_DIRS:
                if real.startswith(os.path.realpath(dd) + os.sep) and real.endswith(suffix):
                    return list(tt)
        return t

    check("37: ~/.claude/CLAUDE.md routes to agents-md",
          route("~/.claude/CLAUDE.md") == ["agents-md"])
    check("38: ~/dev/CLAUDE.md routes to agents-md",
          route("~/dev/CLAUDE.md") == ["agents-md"])
    check("39: the Codex adapter routes to agents-md",
          route("~/.claude/codex/AGENTS.delta.md") == ["agents-md"])
    check("40: an agent definition routes to agents",
          route("~/.claude/agents/qa-agent.md") == ["agents"])
    check("41: a command routes to skills",
          route("~/.claude/commands/autopilot.md") == ["skills"])
    check("42: a new skill routes to skills",
          route("~/.claude/skills/telegram/SKILL.md") == ["skills"])
    check("43: settings.json routes to hooks",
          route("~/.claude/settings.json") == ["hooks"])
    check("44: ~/.claude.json routes to mcp", route("~/.claude.json") == ["mcp"])
    check("45: an unrelated repo file routes nowhere",
          route("/Users/zalo/dev/zalo-os/package.json") == [])
    check("46: a non-SKILL.md file inside a skill routes nowhere",
          route("~/.claude/skills/telegram/scripts/send.sh") == [])

    # --on-edit on an unwatched path must be silent and write nothing
    payload = json.dumps({"tool_input": {"file_path": "/tmp/nothing-to-do.txt"}})
    r = subprocess.run(["python3", SCRIPT, "--on-edit"], input=payload,
                       capture_output=True, text=True)
    check("47: --on-edit on an unwatched path exits 0 silently",
          r.returncode == 0 and r.stdout == "" and r.stderr == "")
    r = subprocess.run(["python3", SCRIPT, "--on-edit"], input="not json",
                       capture_output=True, text=True)
    check("48: --on-edit on a malformed payload exits 0", r.returncode == 0)

    # --- QA finding 1: --on-edit must SHOUT when hooks.json changes ---------
    src = open(SCRIPT, encoding="utf-8").read()
    on_edit_src = src.split("def on_edit(", 1)[1].split("\ndef ", 1)[0]
    check("52: --on-edit emits the re-trust warning when hooks.json changed",
          "HOOKS_RETRUST_WARNING" in on_edit_src)
    check("53: --on-edit returns 2 so Claude Code surfaces that stderr",
          "return 2" in on_edit_src)
    check("54: the warning names the fix (/hooks) and the consequence",
          "/hooks" in cs.HOOKS_RETRUST_WARNING
          and "UNTRUSTED" in cs.HOOKS_RETRUST_WARNING)

    # --- QA finding 5: a Bash grant is not a read-only sandbox --------------
    check("55: live-test is projected workspace-write, not read-only",
          cs.SANDBOX_OVERRIDES.get("live-test") == "workspace-write")
    check("56: bug-fix is projected workspace-write",
          cs.SANDBOX_OVERRIDES.get("bug-fix") == "workspace-write")
    check("57: the verdict-only agents keep read-only",
          all(a not in cs.SANDBOX_OVERRIDES
              for a in ("qa-agent", "outcomes-grader", "safe-planner", "brainstorm")))
    import tomllib
    agents_dir = os.path.expanduser("~/.codex/agents")
    boxes = {}
    for f in os.listdir(agents_dir):
        if f.endswith(".toml"):
            a = tomllib.load(open(os.path.join(agents_dir, f), "rb"))
            boxes[a["name"]] = a.get("sandbox_mode")
    check("58: the generated TOMLs carry the overridden sandboxes",
          boxes.get("live-test") == "workspace-write"
          and boxes.get("bug-fix") == "workspace-write"
          and boxes.get("qa-agent") == "read-only")

    # --- QA finding 4: deletions must propagate ----------------------------
    d = workdir()
    skills_out = os.path.join(d, "skills")
    os.makedirs(skills_out)
    # an orphaned command skill (generated banner, no source command)
    orphan_cmd = os.path.join(skills_out, "gone-command")
    os.makedirs(orphan_cmd)
    open(os.path.join(orphan_cmd, "SKILL.md"), "w").write(
        "---\nname: gone-command\n---\n<!--\nGENERATED by "
        "~/.claude/scripts/codex-sync.py from x\n-->\nbody\n")
    # an orphaned symlink into ~/.claude/skills whose target is gone
    orphan_link = os.path.join(skills_out, "gone-skill")
    os.symlink(os.path.expanduser("~/.claude/skills/no-such-skill"), orphan_link)
    # somebody else's real directory, which must survive untouched
    bystander = os.path.join(skills_out, "not-ours")
    os.makedirs(bystander)
    open(os.path.join(bystander, "SKILL.md"), "w").write("hand written\n")
    open(os.path.join(bystander, "extra.md"), "w").write("data\n")
    # a symlink pointing somewhere else entirely, also not ours
    foreign = os.path.join(skills_out, "foreign")
    os.symlink("/tmp", foreign)

    saved = cs.SKILLS_OUT
    try:
        cs.SKILLS_OUT = skills_out
        s2 = cs.Sync(quiet=True)
        n = cs.prune_orphan_skills(s2, set(), set())
    finally:
        cs.SKILLS_OUT = saved
    check("59: an orphaned generated command skill is removed",
          not os.path.exists(orphan_cmd))
    check("60: a dangling symlink into ~/.claude/skills is removed",
          not os.path.lexists(orphan_link))
    check("61: a real directory that is not ours survives",
          os.path.isfile(os.path.join(bystander, "extra.md")))
    check("62: a symlink pointing outside ~/.claude/skills survives",
          os.path.lexists(foreign))
    check("63: the prune count matches what it removed", n == 2)

    # QA confirmation pass: a REVERSE ORIGINAL must never be pruned. Eleven
    # skills live physically in ~/.agents/skills with ~/.claude/skills holding
    # the symlink; deleting one destroys the only copy.
    d2 = workdir()
    fake_claude_skills = os.path.join(d2, "claude-skills")
    fake_out = os.path.join(d2, "agents-skills")
    os.makedirs(fake_claude_skills)
    os.makedirs(fake_out)
    original = os.path.join(fake_out, "mediabunny")
    os.makedirs(original)
    open(os.path.join(original, "SKILL.md"), "w").write(
        "mentions ~/.claude/scripts/codex-sync.py in passing\n")
    os.symlink(original, os.path.join(fake_claude_skills, "mediabunny"))
    saved_out, saved_claude = cs.SKILLS_OUT, cs.CLAUDE
    try:
        cs.SKILLS_OUT = fake_out
        cs.CLAUDE = d2
        os.rename(fake_claude_skills, os.path.join(d2, "skills"))
        s4 = cs.Sync(quiet=True)
        n2 = cs.prune_orphan_skills(s4, set(), set())
    finally:
        cs.SKILLS_OUT, cs.CLAUDE = saved_out, saved_claude
    check("65: a reverse-original skill is never pruned, even when its SKILL.md "
          "mentions codex-sync.py",
          os.path.isfile(os.path.join(original, "SKILL.md")) and n2 == 0)

    # and a live source must NOT be pruned
    saved = cs.SKILLS_OUT
    try:
        cs.SKILLS_OUT = skills_out
        os.makedirs(os.path.join(skills_out, "keepme"))
        open(os.path.join(skills_out, "keepme", "SKILL.md"), "w").write(
            "<!--\nGENERATED by ~/.claude/scripts/codex-sync.py from x\n-->\n")
        s3 = cs.Sync(quiet=True)
        # "autopilot" is a real command, so a projection named after it stays
        os.rename(os.path.join(skills_out, "keepme"),
                  os.path.join(skills_out, "autopilot"))
        cs.prune_orphan_skills(s3, set(), {"autopilot"})
    finally:
        cs.SKILLS_OUT = saved
    check("64: a command skill whose source still exists is kept",
          os.path.isfile(os.path.join(skills_out, "autopilot", "SKILL.md")))

    # --- the model map is the single point of truth ------------------------
    check("49: fable maps to the flagship at xhigh",
          cs.MODEL_MAP["fable"] == ("gpt-5.6-sol", "xhigh"))
    check("50: opus maps to the volume tier at high",
          cs.MODEL_MAP["opus"] == ("gpt-5.5", "high"))
    check("51: an unknown pin falls back to the volume tier",
          cs.MODEL_MAP.get("no-such-model", cs.DEFAULT_MODEL) == cs.MODEL_MAP["opus"])

    for x in _dirs:
        shutil.rmtree(x, ignore_errors=True)
    total = passed + failed
    print("\n%d/%d passed, %d failed" % (passed, total, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
