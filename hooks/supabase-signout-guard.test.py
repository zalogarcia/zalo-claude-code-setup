#!/usr/bin/env python3
"""Behaviour suite for supabase-signout-guard.

Run: python3 ~/.claude/hooks/supabase-signout-guard.test.py
Must stay green: this is a PreToolUse hook on Bash, Write and Edit, and a
broken one either blocks every call or lets the 2026-09-29 sign out through.

The suite tests the hook that sits NEXT TO it (so a worktree copy is tested in
the worktree). SIGNOUT_GUARD_HOOK=<path> points it at another file, which is
how the failing-first run against an allow-everything stub was done.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("SIGNOUT_GUARD_HOOK") or os.path.join(
    HERE, "supabase-signout-guard.py"
)
BLOCK, WARN, ALLOW = "block", "warn", "allow"

# A throwaway git repo: `.git` is all the hook's walk-up looks for.
REPO = tempfile.mkdtemp(prefix="sog-repo-")
os.mkdir(os.path.join(REPO, ".git"))
DOCS = os.path.expanduser("~/Documents/sog-test-nonexistent")

passed = failed = 0


def run(payload):
    """Run the hook as Claude Code does. Returns (rc, stderr, context)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    p = subprocess.run(
        [sys.executable, HOOK], input=raw, capture_output=True, text=True
    )
    ctx = None
    if p.stdout.strip():
        try:
            ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            ctx = "<unparseable stdout> " + p.stdout
    return p.returncode, p.stderr, ctx


def bash(cmd, cwd="/tmp"):
    return {
        "session_id": "sog-test",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
        "cwd": cwd,
    }


def write(path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


def edit(path, new, old="x"):
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": old, "new_string": new},
    }


def multiedit(path, news):
    return {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": path,
            "edits": [{"old_string": "x", "new_string": n} for n in news],
        },
    }


def nbedit(path, src):
    return {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": path, "new_source": src},
    }


def check(label, payload, expect, marker=None):
    global passed, failed
    rc, err, ctx = run(payload)
    problems = []
    if expect == BLOCK:
        if rc != 2:
            problems.append(f"exit {rc}, wanted 2")
        elif "supabase-signout-guard" not in err:
            problems.append("stderr does not name the guard")
        elif marker and marker not in err:
            problems.append(f"stderr missing {marker!r}")
    elif expect == WARN:
        if rc != 0:
            problems.append(f"exit {rc}, wanted 0")
        elif not ctx or "supabase-signout-guard" not in ctx:
            problems.append("no warning context")
        elif marker and marker not in ctx:
            problems.append(f"context missing {marker!r}")
    else:
        if rc != 0:
            problems.append(f"exit {rc}, wanted 0")
        elif ctx:
            problems.append("unexpected warning context")
    if problems:
        failed += 1
        print(f"  FAIL  {label}: {'; '.join(problems)}")
        if err:
            print("        stderr: " + err[:300].replace("\n", " | "))
        if ctx:
            print("        context: " + ctx[:300].replace("\n", " | "))
    else:
        passed += 1
        print(f"  PASS  {label}")


INCIDENT = """import { createClient } from "@supabase/supabase-js";
const admin = createClient(url, SERVICE_ROLE_KEY, { auth: { persistSession: false } });
const { data: link } = await admin.auth.admin.generateLink({
  type: "magiclink", email: "admin@example.com",
});
const sb = createClient(url, ANON_KEY, { auth: { persistSession: false } });
await sb.auth.verifyOtp({ type: "magiclink", token_hash: link.properties.hashed_token });
const r = await fetch(`${url}/functions/v1/embed-transcripts`, { method: "POST" });
console.log(r.status);
await sb.auth.signOut();
"""

LOCAL_RIG = INCIDENT.replace(
    "await sb.auth.signOut();", "await sb.auth.signOut({ scope: 'local' });"
)

print("supabase-signout-guard tests\n")

# ---------------------------------------------------------------------------
print("regression: the 2026-09-29 incident shape")
check(
    "Write of /tmp/ob-lesson-fix/reembed.mjs ending in signOut() is blocked",
    write("/tmp/ob-lesson-fix/reembed.mjs", INCIDENT),
    BLOCK,
    "every session of that account",
)
check(
    "the block message names the fix: scope 'local' or drop the session",
    write("/tmp/ob-lesson-fix/reembed.mjs", INCIDENT),
    BLOCK,
    "drop the session",
)
check(
    "the same rig as a node heredoc in Bash is blocked",
    bash("node --input-type=module <<'EOF'\n" + INCIDENT + "EOF\necho done"),
    BLOCK,
    "scope: 'local'",
)
check(
    "the same rig written by cat heredoc to a scratch file is blocked",
    bash("mkdir -p /tmp/ob-lesson-fix && cat > /tmp/ob-lesson-fix/reembed.mjs <<'EOF'\n"
         + INCIDENT + "EOF"),
    BLOCK,
)

# ---------------------------------------------------------------------------
print("\nblock: JS/TS in Bash inline code")
check("node -e with auth.signOut()",
      bash("node -e \"const sb = mk(); await sb.auth.signOut()\""), BLOCK)
check("node -e with signOut({})",
      bash("node -e 'await supabase.auth.signOut({})'"), BLOCK)
check("node -e with scope global",
      bash("node -e \"await sb.auth.signOut({ scope: 'global' })\""), BLOCK)
check("node -e with scope others",
      bash("node -e 'await sb.auth.signOut({ scope: \"others\" })'"), BLOCK)
check("node -pe cluster flag",
      bash("node -pe 'sb.auth.signOut()'"), BLOCK)
check("optional-call form signOut?.()",
      bash("node -e 'await sb.auth.signOut?.()'"), BLOCK)
check("bracket form auth['signOut']()",
      bash("node -e \"await sb.auth['signOut']()\""), BLOCK)
check("admin.signOut(jwt) defaults to global too",
      bash("node -e 'await admin.auth.admin.signOut(jwt)'"), BLOCK)
check("admin.signOut(jwt, 'global')",
      bash("node -e \"await admin.auth.admin.signOut(jwt, 'global')\""), BLOCK)
check("a scope held in a variable is not provably local",
      bash("node -e 'await sb.auth.signOut({ scope })'"), BLOCK)
check("npx tsx -e",
      bash("npx tsx -e 'await sb.auth.signOut()'"), BLOCK)
check("env assignment and caffeinate prefixes",
      bash("FOO=1 caffeinate -i node -e 'await sb.auth.signOut()'"), BLOCK)
check("deno eval",
      bash("deno eval 'await sb.auth.signOut()'"), BLOCK)
check("bun -e",
      bash("bun -e 'await sb.auth.signOut()'"), BLOCK)
check("after a prose segment in an && chain",
      bash("cd /tmp && grep -c x y; node -e 'await sb.auth.signOut()'"), BLOCK)
check("inside a for loop body",
      bash("for i in 1 2; do node -e 'await sb.auth.signOut()'; done"), BLOCK)
check("bash -c wrapper",
      bash("bash -c \"node -e 'await sb.auth.signOut()'\""), BLOCK)
check("zsh -lc wrapper",
      bash("zsh -lc \"node -e 'await sb.auth.signOut()'\""), BLOCK)
check("command substitution inside an echo",
      bash("echo \"$(node -e 'await sb.auth.signOut()')\""), BLOCK)
check("subshell group",
      bash("(cd /tmp && node -e 'await sb.auth.signOut()')"), BLOCK)
check("echo piped into node",
      bash("echo 'await sb.auth.signOut()' | node --input-type=module"), BLOCK)
check("printf redirected to a scratch .mjs",
      bash("printf 'await sb.auth.signOut()\\n' > /tmp/rig.mjs"), BLOCK)
check("echo appended to a scratch .ts",
      bash("echo 'await sb.auth.signOut();' >> /tmp/sog/rig.ts"), BLOCK)
check("ssh runner wrapping node -e",
      bash("ssh box \"node -e 'await sb.auth.signOut()'\""), BLOCK)
check("docker exec runner wrapping node -e",
      bash("docker exec api node -e 'await sb.auth.signOut()'"), BLOCK)
check("watch runner wrapping node -e",
      bash("watch -n 5 node -e 'await sb.auth.signOut()'"), BLOCK)
check("find -exec wrapping node -e",
      bash("find /tmp -name x -exec node -e 'await sb.auth.signOut()' \\;"), BLOCK)
check("xargs wrapping node -e",
      bash("echo 1 | xargs -I{} node -e 'await sb.auth.signOut()'"), BLOCK)
check("here-string into node",
      bash("node --input-type=module <<< 'await sb.auth.signOut()'"), BLOCK)
check("here-string into python3, unspaced",
      bash("python3 <<<'sb.auth.sign_out()'"), BLOCK)
check("an unknown tool printing code into a scratch .mjs",
      bash("perl -e 'print \"await sb.auth.signOut()\"' > /tmp/rig.mjs"), BLOCK)
check("a logout URL does not borrow a later statement's scope=local",
      write("/tmp/rig.mjs", "await fetch(u + '/auth/v1/logout', { method: 'POST' }); "
                            "await fetch(u + '/rest/v1/x?scope=local');\n"), BLOCK)
check("heredoc to a file path held in a variable (target unknown)",
      bash("cat > \"$RIG\" <<'EOF'\nawait sb.auth.signOut()\nEOF"), BLOCK)
check("multi-line node -e with the call split over lines",
      bash("node -e \"\nconst sb = mk();\nawait sb.auth.signOut(\n  { scope: 'global' }\n);\n\""),
      BLOCK)

# ---------------------------------------------------------------------------
print("\nblock: heredoc forms")
check("heredoc with <<- and a tab-indented terminator",
      bash("node --input-type=module <<-EOF\n\tawait sb.auth.signOut()\n\tEOF"), BLOCK)
check("heredoc with a double-quoted delimiter",
      bash('node <<"JS"\nawait sb.auth.signOut()\nJS'), BLOCK)
check("heredoc with node -r value flag before stdin code",
      bash("node -r dotenv/config --input-type=module <<'EOF'\nawait sb.auth.signOut()\nEOF"),
      BLOCK)
check("heredoc into tsx with no script",
      bash("npx tsx <<'EOF'\nawait sb.auth.signOut()\nEOF"), BLOCK)
check("heredoc piped from cat into node",
      bash("cat <<'EOF' | node --input-type=module\nawait sb.auth.signOut()\nEOF"), BLOCK)
check("heredoc to tee on a scratch file",
      bash("tee /tmp/rig.mjs >/dev/null <<'EOF'\nawait sb.auth.signOut()\nEOF"), BLOCK)
check("heredoc redirect written after the marker",
      bash("cat <<'EOF' > /tmp/rig.js\nawait sb.auth.signOut()\nEOF"), BLOCK)
check("heredoc into bash whose body runs node -e",
      bash("bash <<'EOF'\nnode -e 'await sb.auth.signOut()'\nEOF"), BLOCK)
check("node -e fed by a cat heredoc substitution",
      bash("node --input-type=module -e \"$(cat <<'EOF'\nawait sb.auth.signOut()\nEOF\n)\""),
      BLOCK)
check("heredoc to an extensionless scratch file with a node shebang",
      bash("cat > /tmp/rig <<'EOF'\n#!/usr/bin/env node\nawait sb.auth.signOut()\nEOF"),
      BLOCK)

# ---------------------------------------------------------------------------
print("\nblock: Python")
check("python3 -c sign_out()",
      bash("python3 -c 'sb.auth.sign_out()'"), BLOCK)
check("python3 heredoc sign_out() with no args",
      bash("python3 - <<'EOF'\nfrom supabase import create_client\nsb = create_client(u, k)\nsb.auth.sign_out()\nEOF"),
      BLOCK)
check("python sign_out scope global",
      bash("python3 -c 'sb.auth.sign_out({\"scope\": \"global\"})'"), BLOCK)
check("python heredoc to a scratch .py",
      bash("cat > /tmp/rig.py <<'EOF'\nclient.auth.sign_out()\nEOF"), BLOCK)
check("uv run python -c",
      bash("uv run python -c 'sb.auth.sign_out()'"), BLOCK)

# ---------------------------------------------------------------------------
print("\nblock: raw GoTrue logout")
check("curl POST /auth/v1/logout with no scope",
      bash('curl -s -X POST "$SUPABASE_URL/auth/v1/logout" -H "apikey: $ANON" '
           '-H "Authorization: Bearer $JWT"'), BLOCK)
check("curl logout?scope=global",
      bash("curl -X POST 'https://x.supabase.co/auth/v1/logout?scope=global' -H 'apikey: k'"),
      BLOCK)
check("curl logout?scope=others",
      bash("curl -X POST 'https://x.supabase.co/auth/v1/logout?scope=others'"), BLOCK)
check("fetch to /auth/v1/logout in node -e",
      bash("node -e \"await fetch(url + '/auth/v1/logout', { method: 'POST', headers })\""),
      BLOCK)
check("requests.post to /auth/v1/logout in a python heredoc",
      bash("python3 - <<'EOF'\nimport requests\nrequests.post(f\"{url}/auth/v1/logout\", headers=h)\nEOF"),
      BLOCK)
check("wget --post-data to /auth/v1/logout",
      bash("wget --post-data='' https://x.supabase.co/auth/v1/logout"), BLOCK)

# ---------------------------------------------------------------------------
print("\nblock: Write / Edit / MultiEdit / NotebookEdit outside app source")
check("Write ~/Documents rig .py with sign_out()",
      write(os.path.join(DOCS, "rig.py"), "sb.auth.sign_out()\n"), BLOCK)
check("Edit of a /tmp rig introducing signOut()",
      edit("/tmp/rig.mjs", "await sb.auth.signOut();"), BLOCK)
check("MultiEdit of a /tmp rig, second edit introduces signOut()",
      multiedit("/tmp/rig.mjs", ["const a = 1;", "await sb.auth.signOut();"]), BLOCK)
check("NotebookEdit of a scratch notebook with sign_out()",
      nbedit("/tmp/rig.ipynb", "sb.auth.sign_out()"), BLOCK)
check("Write in a repo's scripts/ folder is blocked",
      write(os.path.join(REPO, "scripts", "reembed.mjs"), INCIDENT), BLOCK)
check("Write at a repo root (not app source) is blocked",
      write(os.path.join(REPO, "rig.mjs"), INCIDENT), BLOCK)
check("Write under apps/x/scripts/ is blocked (scratch dir wins)",
      write(os.path.join(REPO, "apps", "web", "scripts", "x.ts"), INCIDENT), BLOCK)
check("Write of an extensionless scratch file with a node shebang",
      write("/tmp/rig", "#!/usr/bin/env node\nawait sb.auth.signOut()\n"), BLOCK)
check("Write of a scratch .html page calling signOut()",
      write("/tmp/rig.html", "<script>await sb.auth.signOut()</script>"), BLOCK)
check("Write of a scratch .ts with a logout fetch",
      write("/tmp/rig.ts", "await fetch(`${u}/auth/v1/logout`, { method: 'POST' })\n"),
      BLOCK)
check("a global call next to a local one still blocks",
      write("/tmp/rig.mjs",
            "await a.auth.signOut({ scope: 'local' });\nawait b.auth.signOut();\n"),
      BLOCK)

# ---------------------------------------------------------------------------
print("\nwarn only: app source inside a git repo")
check("Write src/components/Settings.jsx with signOut()",
      write(os.path.join(REPO, "src", "components", "Settings.jsx"),
            "export async function onLogout() {\n  await supabase.auth.signOut();\n}\n"),
      WARN, "scope: 'local'")
check("Write supabase/functions/x/index.ts with signOut()",
      write(os.path.join(REPO, "supabase", "functions", "x", "index.ts"),
            "await client.auth.signOut();\n"), WARN)
check("Edit apps/web/src/auth.ts with signOut()",
      edit(os.path.join(REPO, "apps", "web", "src", "auth.ts"),
           "await supabase.auth.signOut();"), WARN)
check("Write packages/core/src/session.ts with signOut()",
      write(os.path.join(REPO, "packages", "core", "src", "session.ts"),
            "await supabase.auth.signOut();\n"), WARN)
check("Write of a co-located src test calling a store signOut()",
      write(os.path.join(REPO, "src", "store", "x.test.js"),
            "await useGameStore.getState().signOut();\n"), WARN)
check("Bash cat heredoc into repo src/ only warns",
      bash("cat > " + os.path.join(REPO, "src", "logout.ts")
           + " <<'EOF'\nawait supabase.auth.signOut();\nEOF"), WARN)

# ---------------------------------------------------------------------------
print("\nallow: local scope")
check("node -e with scope local (single quotes)",
      bash("node -e \"await sb.auth.signOut({ scope: 'local' })\""), ALLOW)
check("node -e with scope local (escaped double quotes)",
      bash("node -e \"await sb.auth.signOut({ scope: \\\"local\\\" })\""), ALLOW)
check("multi-line local call",
      bash("node --input-type=module <<'EOF'\nawait sb.auth.signOut(\n  { scope: 'local' }\n);\nEOF"),
      ALLOW)
check("chained .signOut({ scope: 'local' }) on its own line",
      write("/tmp/rig.mjs", "await supabase.auth\n  .signOut({ scope: \"local\" })\n  .catch(() => {});\n"),
      ALLOW)
check("python sign_out scope local",
      bash("python3 -c 'sb.auth.sign_out({\"scope\": \"local\"})'"), ALLOW)
check("python admin sign_out(jwt, 'local')",
      bash("python3 -c \"sb.auth.admin.sign_out(jwt, 'local')\""), ALLOW)
check("admin.signOut(jwt, 'local')",
      bash("node -e \"await admin.auth.admin.signOut(jwt, 'local')\""), ALLOW)
check("curl logout?scope=local",
      bash("curl -X POST 'https://x.supabase.co/auth/v1/logout?scope=local' -H 'apikey: k'"),
      ALLOW)
check("requests.post logout with params scope local",
      bash("python3 - <<'EOF'\nrequests.post(f\"{u}/auth/v1/logout\", params={\"scope\": \"local\"})\nEOF"),
      ALLOW)
check("Write of the incident rig with scope local",
      write("/tmp/ob-lesson-fix/reembed.mjs", LOCAL_RIG), ALLOW)
check("Swift / Dart style local scope",
      write("/tmp/rig.ts", "await supabase.auth.signOut(scope: SignOutScope.local)\n"),
      ALLOW)
check("Write in repo src/ with scope local gets no warning",
      write(os.path.join(REPO, "src", "a.ts"),
            "await supabase.auth.signOut({ scope: 'local' });\n"), ALLOW)
check("Edit of a /tmp rig that switches to scope local",
      edit("/tmp/rig.mjs", "await sb.auth.signOut({ scope: 'local' });",
           old="await sb.auth.signOut();"), ALLOW)

# ---------------------------------------------------------------------------
print("\nallow: mentions that are not calls")
check("grep for signOut() in a repo",
      bash('grep -rn "signOut()" src/'), ALLOW)
check("rg for an escaped pattern",
      bash("rg -n 'auth\\.signOut\\(\\)' ~/dev/90-day-cmaa-game-app/src"), ALLOW)
check("git log -S for the call",
      bash("git log -S 'signOut()' --oneline | head"), ALLOW)
check("git commit -m naming the call",
      bash('git commit -m "fix(rig): drop the default signOut() at the end"'), ALLOW)
check("commit-with-heredoc shape naming the call",
      bash("git commit -m \"$(cat <<'EOF'\nfeat(hooks): block a default scope signOut()\n\n"
           "sb.auth.signOut() defaults to global.\nEOF\n)\""), ALLOW)
check("gh pr body naming the call",
      bash("gh pr create --title t --body 'never call sb.auth.signOut() in a rig'"), ALLOW)
check("echo of prose, no redirect",
      bash("echo 'never call sb.auth.signOut() in a rig'"), ALLOW)
check("heredoc to a .md notes file",
      bash("cat > /tmp/notes.md <<'EOF'\nThe rig ended with sb.auth.signOut(), which is global.\nEOF"),
      ALLOW)
check("Write of a markdown note quoting the call",
      write(os.path.expanduser("~/.claude/projects/x/memory/note.md"),
            "```js\n// NEVER end with sb.auth.signOut(): see below.\nawait sb.auth.signOut();\n```\n"),
      ALLOW)
check("node script with a brief argument (argv is data)",
      bash("node ~/dev/claude-telegram-bridge/bg.mjs \"fix the rig that called sb.auth.signOut()\""),
      ALLOW)
check("python script fed a heredoc (stdin is data)",
      bash("python3 /tmp/check.py <<'EOF'\nsb.auth.signOut()\nEOF"), ALLOW)
check("hook payload piped into python3 hook.py (stdin is data)",
      bash("echo '{\"tool_input\":{\"command\":\"node -e sb.auth.signOut()\"}}' | "
           "python3 ~/.claude/hooks/supabase-signout-guard.py"), ALLOW)
check("sed -i that fixes the call to scope local",
      bash("sed -i '' 's/sb.auth.signOut()/sb.auth.signOut({ scope: \"local\" })/' /tmp/rig.mjs"),
      ALLOW)
check("sed -n search (prints only)",
      bash("sed -n '/signOut()/p' src/x.js"), ALLOW)
check("comment in a scratch rig mentioning the call",
      write("/tmp/rig.mjs", "// do not call sb.auth.signOut() here: it is global\n"
                            "/* nor signOut() in a block comment */\nconst x = 1;\n"),
      ALLOW)
check("python comment mentioning sign_out()",
      write("/tmp/rig.py", "# never call sb.auth.sign_out() here\nx = 1\n"), ALLOW)
check("a method definition named signOut",
      write("/tmp/store.mjs", "const s = {\n  async signOut() {\n    reset();\n  },\n};\n"),
      ALLOW)
check("a function declaration named signOut",
      write("/tmp/x.js", "async function signOut() {\n  reset();\n}\n"), ALLOW)
check("a TS interface signature",
      write("/tmp/x.ts", "interface A {\n  signOut(): Promise<void>;\n}\n"), ALLOW)
check("a python def sign_out",
      write("/tmp/x.py", "def sign_out(self):\n    pass\n"), ALLOW)
check("a reference without a call",
      write("/tmp/x.jsx", "<button onClick={signOut}>Log out</button>\n"), ALLOW)
check("look-alike names signOutMock() and handleSignOut()",
      write("/tmp/x.js", "signOutMock();\nhandleSignOut();\n"), ALLOW)
check("a test-name filter that mentions the call",
      bash("npx vitest run -t 'calls signOut() on expiry'"), ALLOW)
check("a curl body that only mentions the call",
      bash("curl -s -X POST https://api.example.com/msg -d 'text=never call signOut() in a rig'"),
      ALLOW)
check("a script with a prose argument",
      bash("~/.claude/scripts/peer-ask.sh zalo-os -m 'did the rig call sb.auth.signOut()?'"),
      ALLOW)
check("a peer message via tmux send-keys",
      bash("tmux send-keys -t zalo-os -l '[from x] the rig called sb.auth.signOut()'"), ALLOW)
check("httpie query param scope==local",
      bash("http POST https://x.supabase.co/auth/v1/logout scope==local apikey:k"), ALLOW)
check("a node one-liner that checks a file for the quoted name",
      bash("node -e \"console.log(fs.readFileSync('x.mjs','utf8').includes('signOut()'))\""),
      ALLOW)
check("here-string into a script is data",
      bash("python3 /tmp/check.py <<< 'sb.auth.signOut()'"), ALLOW)
check("supabase CLI logout is not an auth session",
      bash("supabase logout"), ALLOW)
check("a logout route that is not GoTrue",
      bash("curl -X POST https://example.com/api/logout"), ALLOW)

# ---------------------------------------------------------------------------
print("\nallow: ordinary commands and payloads")
check("ls", bash("ls -la /tmp"), ALLOW)
check("npm test", bash("cd /Users/zalo/dev/zalo-os && npm test"), ALLOW)
check("git status", bash("git status --short"), ALLOW)
check("node -e with nothing auth related",
      bash("node -e 'console.log(1 + 1)'"), ALLOW)
check("Write of ordinary code", write("/tmp/x.ts", "export const a = 1;\n"), ALLOW)
check("Read tool is ignored",
      {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}}, ALLOW)
check("malformed JSON fails open", "{not json", ALLOW)
check("empty stdin fails open", "", ALLOW)
check("non-object JSON fails open", "[1, 2]", ALLOW)
check("Bash with no command", {"tool_name": "Bash", "tool_input": {}}, ALLOW)
check("Write of this suite is exempt",
      write(os.path.join(HERE, "supabase-signout-guard.test.py"), INCIDENT), ALLOW)
check("Write of the hook itself is exempt",
      write(os.path.join(HERE, "supabase-signout-guard.py"), INCIDENT), ALLOW)

# ---------------------------------------------------------------------------
print("\nnesting and bounded time")
check("three levels of nested substitution still block",
      bash("echo \"$(echo \"$(echo \"$(node -e 'await sb.auth.signOut()')\")\")\""), BLOCK)
import time as _time  # noqa: E402

for label, payload in (
    ("60 levels of nested $( ) with a trigger",
     bash("echo " + "$(echo " * 60 + "sb.auth.signOut()" + ")" * 60)),
    ("5000 unterminated /* in a scratch rig",
     write("/tmp/rig.mjs", "/* x\n" * 5000 + "await sb.auth.signOut();\n")),
    ("20000 local sign out calls",
     write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: 'local' });\n" * 20000)),
    ("a 3 MB heredoc body",
     bash("node <<'EOF'\n" + ("const a = 1;\n" * 250000) + "await sb.auth.signOut()\nEOF")),
):
    t0 = _time.time()
    rc, _err, _ctx = run(payload)
    dt = _time.time() - t0
    if dt < 4.0 and rc in (0, 2):
        passed += 1
        print(f"  PASS  {label} ({dt:.2f}s, exit {rc})")
    else:
        failed += 1
        print(f"  FAIL  {label}: {dt:.2f}s, exit {rc}")

# ---------------------------------------------------------------------------
# QA round 1 (2026-09-29), finding MEDIUM: shlex is quadratic on a long
# token, so a 1 MB inline command ran past the 10 s hook timeout. A stage
# over the tokenizer cap is classified from its head word and the verdict
# must still be right, fast.
print("\nlarge inline commands: right verdict, bounded time")
BIG = "const a = 1;" * 90000  # about 1 MB
for label, payload, expect in (
    ("a 1 MB node -e ending in signOut() is blocked",
     bash("node -e '" + BIG + " await sb.auth.signOut()'"), BLOCK),
    ("a 1 MB echo piped into node ending in signOut() is blocked",
     bash("echo '" + BIG + " await sb.auth.signOut()' | node"), BLOCK),
    ("a 1 MB printf into a scratch rig ending in signOut() is blocked",
     bash("printf '" + BIG + " await sb.auth.signOut()' > /tmp/rig.mjs"), BLOCK),
    ("a 1 MB bash -c wrapping node -e with signOut() is blocked",
     bash("bash -c \"node -e '" + BIG + " await sb.auth.signOut()'\""), BLOCK),
    ("a 2 MB git commit message that mentions sb.auth.signOut() is allowed",
     bash("git commit -m 'fix: removed sb.auth.signOut() " + ("x" * 2000000) + "'"), ALLOW),
    ("a 1 MB grep pattern file argument naming signOut() is allowed",
     bash("grep -rn 'sb.auth.signOut() " + ("y" * 1000000) + "' src"), ALLOW),
    ("a 1 MB node -e with scope local is allowed",
     bash("node -e '" + BIG + " await sb.auth.signOut({ scope: \"local\" })'"), ALLOW),
):
    t0 = _time.time()
    rc, err, ctx = run(payload)
    dt = _time.time() - t0
    want = 2 if expect == BLOCK else 0
    if dt < 4.0 and rc == want and (expect != ALLOW or not ctx):
        passed += 1
        print(f"  PASS  {label} ({dt:.2f}s, exit {rc})")
    else:
        failed += 1
        print(f"  FAIL  {label}: {dt:.2f}s, exit {rc}, wanted {want}")

# The large-input tokenizer must split exactly as shlex does, or a big
# command would be classified differently from a small one.
import importlib.util as _ilu  # noqa: E402
import random as _random  # noqa: E402
import shlex as _shlex  # noqa: E402

_spec = _ilu.spec_from_file_location("sog_hook", HOOK)
_mod = _ilu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
    _linear = getattr(_mod, "split_words_linear", None)
except BaseException:  # a hook (or stub) that calls sys.exit() at import must not end the suite
    _linear = None


def _outcome(fn, s):
    try:
        return fn(s)
    except ValueError:
        return "ValueError"


_rng = _random.Random(20260929)
_alphabet = ["a", "b", "=", " ", "\t", "\n", "'", '"', "\\", "$", "#", "|", ";"]
_mismatch = None
if _linear is None:
    _mismatch = "split_words_linear is missing"
else:
    for _ in range(20000):
        s = "".join(_rng.choice(_alphabet) for _ in range(_rng.randint(0, 24)))
        if _outcome(_linear, s) != _outcome(lambda t: _shlex.split(t, posix=True), s):
            _mismatch = repr(s)
            break
if _mismatch is None:
    passed += 1
    print("  PASS  the linear tokenizer matches shlex.split on 20000 random strings")
else:
    failed += 1
    print(f"  FAIL  the linear tokenizer differs from shlex.split on {_mismatch}")

# QA round 1, finding LOW: any 'local' string in the arguments counted as a
# local scope, so a fallback or an unrelated key let a global scope through.
print("\nlocal must be the scope's own value")
check("scope: opts.scope || 'local' is blocked",
      bash("node -e \"await sb.auth.signOut({ scope: opts.scope || 'local' })\""), BLOCK,
      "not a literal 'local'")
check("scope: opts.scope ?? 'local' is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: opts.scope ?? 'local' });\n"), BLOCK)
check("a computed scope next to an unrelated 'local' key is blocked",
      bash("node -e \"await sb.auth.signOut({ scope: getScope(), tag: 'local' })\""), BLOCK)
check("an unrelated 'local' value with no scope key is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ reason: 'local' });\n"), BLOCK)
check("a ternary with a variable on the other arm is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: dev ? 'local' : s });\n"), BLOCK)
check("python scope or 'local' is blocked",
      bash("python3 -c 'sb.auth.sign_out({\"scope\": scope or \"local\"})'"), BLOCK)
check("admin.signOut(jwt, s || 'local') is blocked",
      bash("node -e \"await admin.auth.admin.signOut(jwt, s || 'local')\""), BLOCK)
check("scope 'local' as const is allowed",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: 'local' as const });\n"), ALLOW)
check("scope 'local' with a trailing comma over several lines is allowed",
      write("/tmp/rig.mjs", "await sb.auth.signOut({\n  scope: 'local',\n});\n"), ALLOW)
check("a spread before scope 'local' is allowed",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ ...opts, scope: 'local' });\n"), ALLOW)
check("scope 'local' before other keys is allowed",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: 'local', extra: 1 });\n"), ALLOW)
check("Swift style scope: .local is allowed",
      write("/tmp/rig.ts", "try await supabase.auth.signOut(scope: .local)\n"), ALLOW)
check("python single-quoted scope local is allowed",
      bash("python3 -c \"sb.auth.sign_out({'scope': 'local'})\""), ALLOW)
check("python options= keyword with scope local is allowed",
      bash("python3 -c 'sb.auth.sign_out(options={\"scope\": \"local\"})'"), ALLOW)
check("scope 'local' with a comment inside the call is allowed",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: 'local' /* rig only */ });\n"), ALLOW)

# QA round 2 (2026-09-29). auth-js 2.101 signOut(options = { scope: 'global' })
# destructures { scope } from its argument, so signOut('local') gets undefined
# and admin.signOut(jwt, scope = 'global') ends every session. Only the admin
# form takes the scope positionally (second argument).
print("\nthe client form needs an options object; fallbacks nested in calls")
check("client signOut('local') is blocked (a string is not the options object)",
      bash("node -e \"await sb.auth.signOut('local')\""), BLOCK, "options object")
check("client signOut(\"local\") in a scratch rig is blocked",
      write("/tmp/rig.mjs", "await supabase.auth.signOut(\"local\");\n"), BLOCK)
check("admin signOut('local') with no jwt is blocked",
      write("/tmp/rig.mjs", "await admin.auth.admin.signOut('local');\n"), BLOCK)
check("a spread after scope 'local' can override it, so it is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: 'local', ...opts });\n"), BLOCK)
check("python os.getenv fallback to 'local' is blocked",
      bash("python3 -c 'import os; sb.auth.sign_out({\"scope\": os.getenv(\"S\", \"local\")})'"), BLOCK)
check("python dict.get fallback to 'local' is blocked",
      write("/tmp/sog-rig.py", "sb.auth.sign_out({\"scope\": opts.get(\"scope\", \"local\")})\n"), BLOCK)
check("a helper call with a 'local' default is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: _.defaultTo(opts.scope, 'local') });\n"), BLOCK)
check("a helper wrapping the options object is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut(getOpts('local'));\n"), BLOCK)
check("a python ** spread after scope local is blocked",
      write("/tmp/sog-rig.py", "sb.auth.sign_out({\"scope\": \"local\", **opts})\n"), BLOCK)
check("a double cast of 'local' is allowed",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: 'local' as unknown as SignOutScope });\n"), ALLOW)
check("an angle-bracket cast of 'local' is allowed",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: <const>'local' });\n"), ALLOW)
check("a parenthesised 'local' is allowed",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: ('local') });\n"), ALLOW)
check("a cast to an indexed type is allowed",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: 'local' as SignOut['scope'] });\n"), ALLOW)
check("shell-escaped quotes around local inside a .sh file are allowed",
      write("/tmp/rig.sh",
            "node --input-type=module -e 'await sb.auth.signOut({ scope: '\\''local'\\'' })'\n"),
      ALLOW)
check("an admin API held in a variable, second argument 'local', is allowed",
      write("/tmp/rig.mjs",
            "const adminAuth = sb.auth.admin;\nawait adminAuth.signOut(jwt, 'local');\n"), ALLOW)
check("python admin sign_out(jwt, scope=\"local\") is allowed",
      bash("python3 -c 'sb.auth.admin.sign_out(jwt, scope=\"local\")'"), ALLOW)
check("python admin sign_out(jwt, \"local\") in a scratch rig is allowed",
      write("/tmp/sog-rig.py", "sb.auth.admin.sign_out(jwt, \"local\")\n"), ALLOW)

# QA round 3. auth-js reads the client form's FIRST argument only and the
# admin form's SECOND only (GoTrueClient.js _signOut({ scope } = ...),
# GoTrueAdminApi.js signOut(jwt, scope = 'global')); a local options object
# anywhere else was proven to send scope=global.
print("\nthe scope must sit in the argument auth-js reads")
check("client signOut(jwt, { scope: 'local' }) is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut(jwt, { scope: 'local' });\n"),
      BLOCK, "wrong argument")
check("client signOut(token, { scope: 'local' }) in node -e is blocked",
      bash("node -e \"await sb.auth.signOut(session.access_token, { scope: 'local' })\""), BLOCK)
check("client signOut(undefined, { scope: 'local' }) is blocked",
      write("/tmp/rig.mjs", "await sb.auth.signOut(undefined, { scope: 'local' });\n"), BLOCK)
check("admin signOut(jwt, undefined, { scope: 'local' }) is blocked",
      write("/tmp/rig.mjs", "await admin.auth.admin.signOut(jwt, undefined, { scope: 'local' });\n"),
      BLOCK)
check("JS signOut(scope = 'local') is an assignment, not a named argument",
      write("/tmp/rig.cjs", "sb.auth.signOut(scope = 'local');\n"), BLOCK)
check("JS signOut(scope='local') in node -e is blocked",
      bash("node -e \"await sb.auth.signOut(scope='local')\""), BLOCK)
check("client signOut({ scope: 'local' }, extra) is allowed (later arguments are ignored)",
      write("/tmp/rig.mjs", "await sb.auth.signOut({ scope: 'local' }, extra);\n"), ALLOW)
check("python sign_out(options={...local}) keyword form is allowed",
      bash("python3 -c 'sb.auth.sign_out(options={\"scope\": \"local\"})'"), ALLOW)

# GoTrue's logout handler reads the scope from the QUERY string only; a scope
# in the request body is ignored and the logout is global.
print("\na logout scope in the request body does not count")
check("fetch with a JSON body scope local is blocked",
      write("/tmp/rig.mjs", "await fetch(url + '/auth/v1/logout', { method: 'POST', headers, "
            "body: JSON.stringify({ scope: 'local' }) });\n"), BLOCK)
check("requests.post json={scope: local} is blocked",
      bash("python3 - <<'EOF'\nimport requests\nrequests.post(f\"{u}/auth/v1/logout\", "
           "headers=h, json={\"scope\": \"local\"})\nEOF"), BLOCK)
check("requests.post data={scope: local} is blocked",
      bash("python3 - <<'EOF'\nimport requests\nrequests.post(f\"{u}/auth/v1/logout\", "
           "headers=h, data={\"scope\": \"local\"})\nEOF"), BLOCK)
check("curl -d scope=local is blocked",
      bash('curl -s -X POST "$SUPABASE_URL/auth/v1/logout" -H "apikey: $ANON" '
           '-H "Authorization: Bearer $JWT" -d scope=local'), BLOCK)
check("curl --data-urlencode scope=local is blocked",
      bash('curl -s -X POST "$SUPABASE_URL/auth/v1/logout" --data-urlencode scope=local'), BLOCK)
check("curl -d JSON scope local is blocked",
      bash("curl -s -X POST \"$SUPABASE_URL/auth/v1/logout\" -d '{\"scope\":\"local\"}'"), BLOCK)
check("httpie scope=local is a JSON body field, blocked",
      bash("http POST https://x.supabase.co/auth/v1/logout scope=local apikey:k"), BLOCK)
check("axios.post body { scope: 'local' } is blocked",
      write("/tmp/rig.mjs", "await axios.post(url + '/auth/v1/logout', { scope: 'local' }, { headers });\n"),
      BLOCK)
check("fetch to logout?scope=local in a template literal is allowed",
      write("/tmp/rig.mjs", "await fetch(`${u}/auth/v1/logout?scope=local`, { method: 'POST', headers });\n"),
      ALLOW)
check("logout?a=1&scope=local is allowed",
      bash("curl -X POST 'https://x.supabase.co/auth/v1/logout?a=1&scope=local' -H 'apikey: k'"), ALLOW)
check("logout? plus URLSearchParams({ scope: 'local' }) is allowed",
      write("/tmp/rig.mjs", "await fetch(u + '/auth/v1/logout?' + new URLSearchParams({ scope: 'local' }), "
            "{ method: 'POST' });\n"), ALLOW)
check("axios params { scope: 'local' } is allowed",
      write("/tmp/rig.mjs", "await axios.post(u + '/auth/v1/logout', null, { params: { scope: 'local' }, headers });\n"),
      ALLOW)
check("a plain fetch has no params option, so params { scope: 'local' } is blocked",
      write("/tmp/rig.mjs", "await fetch(u + '/auth/v1/logout', { method: 'POST', params: { scope: 'local' } });\n"),
      BLOCK)
check("curl --url-query scope=local is allowed",
      bash('curl -s -X POST "$SUPABASE_URL/auth/v1/logout" --url-query scope=local -H "apikey: $ANON"'), ALLOW)
check("python urlencode({'scope': 'local'}) in the query is allowed",
      bash("python3 - <<'EOF'\nrequests.post(f\"{u}/auth/v1/logout?{urlencode({'scope': 'local'})}\", headers=h)\nEOF"),
      ALLOW)

print("\na cast or constructor around the whole options object")
check("{ scope: 'local' } as const is allowed",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: 'local' } as const);\n"), ALLOW)
check("{ scope: 'local' } satisfies SignOutOptions is allowed",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: 'local' } satisfies SignOutOptions);\n"), ALLOW)
check("python dict(scope=\"local\") is allowed",
      write("/tmp/sog-rig.py", "sb.auth.sign_out(dict(scope=\"local\"))\n"), ALLOW)
check("python SignOutOptions(scope=\"local\") is allowed",
      write("/tmp/sog-rig.py", "sb.auth.sign_out(SignOutOptions(scope=\"local\"))\n"), ALLOW)
check("python dict(**opts, scope=\"local\") is allowed (scope after the spread)",
      write("/tmp/sog-rig.py", "sb.auth.sign_out(dict(**opts, scope=\"local\"))\n"), ALLOW)
check("{ scope: 'global' } as const is blocked",
      write("/tmp/rig.ts", "await sb.auth.signOut({ scope: 'global' } as const);\n"), BLOCK)
check("python dict(scope=\"local\", **opts) is blocked (a spread can override)",
      write("/tmp/sog-rig.py", "sb.auth.sign_out(dict(scope=\"local\", **opts))\n"), BLOCK)
check("{ scope: 'local' } as any in the wrong argument is still blocked",
      write("/tmp/rig.ts", "await sb.auth.signOut(jwt, { scope: 'local' } as any);\n"), BLOCK)

# QA round 2, three slow paths on implausible but cheap-to-fix inputs.
print("\npathological shapes: right verdict, bounded time")
for label, payload, expect in (
    ("10000 pipeline stages of cat after a trigger",
     bash("echo 'sb.auth.signOut()'" + " | cat" * 10000), ALLOW),
    ("20000 pipeline stages of node after an echo of signOut()",
     bash("echo 'await sb.auth.signOut()'" + " | node" * 20000), BLOCK),
    ("10000 lines of 1<<n in a node -e with signOut()",
     bash("node -e '" + "x = 1<<n;\n" * 10000 + "await sb.auth.signOut()'"), BLOCK),
    ("399 bare signOut() calls in a 4 MB scratch Write",
     write("/tmp/rig.mjs", ("const a = 1;\n" * 800 + "signOut();\n") * 399), BLOCK),
    ("a 100k digit run before a redirect of signOut() (QA round 3)",
     bash("echo '" + "1" * 100000 + " sb.auth.signOut()' > /tmp/rig.mjs"), BLOCK),
    ("250000 VAR=x prefixes before a node -e signOut() (QA round 3)",
     bash("A=1 " * 250000 + "node -e 'await sb.auth.signOut()'"), BLOCK),
):
    t0 = _time.time()
    rc, err, ctx = run(payload)
    dt = _time.time() - t0
    want = 2 if expect == BLOCK else 0
    if dt < 4.0 and rc == want and (expect != ALLOW or not ctx):
        passed += 1
        print(f"  PASS  {label} ({dt:.2f}s, exit {rc})")
    else:
        failed += 1
        print(f"  FAIL  {label}: {dt:.2f}s, exit {rc}, wanted {want}")

# ---------------------------------------------------------------------------
print("\nmessage hygiene")
rc, err, _ = run(write("/tmp/rig.mjs", INCIDENT))
for label, ok in (
    ("block message says a global sign out ends every session, including the owner's",
     "a global sign out ends every session of that account, including the owner's" in err),
    ("block message has no em or en dashes",
     rc == 2 and "\u2014" not in err and "\u2013" not in err),
):
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}")

shutil.rmtree(REPO, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
