#!/usr/bin/env python3
r"""PreToolUse guard: a Supabase sign out that is not scoped to 'local'.

Why this exists
---------------
2026-09-29, 15:08 UTC. A background worker's re-embed rig minted an admin
session for the owner's own Operator Base account (auth.admin.generateLink
plus verifyOtp, no mail sent), wrote it to /tmp/ob-lesson-fix/reembed.mjs, ran
it, and "cleaned up" at the end with

    await sb.auth.signOut();

supabase-js v2 signOut() defaults to { scope: 'global' }, which revokes EVERY
session of the account, not just the rig's. The owner was signed out of
Operator Base on the web, in the app and on agents.operatorbase.app (same auth
project) and had to sign in again everywhere. A rig session needs no clean up;
if one is wanted, { scope: 'local' } ends only that session. The memory note
operator-base-admin-rpc-testing.md carries the why. This hook is the
mechanism, because a prose rule decays under momentum.

What it BLOCKS (exit 2, message on stderr)
------------------------------------------
A sign out call that is not provably local:
  * JS/TS: x.signOut(), x.signOut({}), signOut({ scope: 'global' }),
    signOut({ scope: 'others' }), signOut({ scope }) (a variable is not
    provably local), the admin form auth.admin.signOut(jwt) (its scope also
    defaults to 'global'), the optional call signOut?.() and bracket access
    auth['signOut']().
  * Python: sign_out(), sign_out({"scope": "global"}), admin.sign_out(jwt).
  * Raw GoTrue: .../auth/v1/logout without scope=local, whatever sends it
    (curl, wget, fetch, requests, axios).
A call is provably local when its scope is a local literal ('local', "local",
`local`, SignOutScope.local, .local; casts and parentheses are peeled off)
and no 'global' or 'others' appears in its arguments. auth-js reads the
scope from ONE argument, so the scope can sit only in
  - the FIRST argument of a client call, as an options object whose scope
    entry is local with no spread after it: signOut({ scope: 'local' }),
    Python sign_out({"scope": "local"}), dict(scope="local"),
    SignOutOptions(scope="local"); a cast around the whole object
    ({ ... } as const, satisfies T) is peeled off;
  - the second argument of an admin call (auth.admin.signOut(jwt, 'local'),
    any receiver whose name contains "admin");
  - a named argument (Swift or Dart scope: .local; for Python sign_out also
    scope="local").
NOT local: a bare signOut('local') (auth-js destructures { scope } from it
and falls back to 'global'); signOut(jwt, { scope: 'local' }) or any local
options object after the first argument (never read); a JS
signOut(scope = 'local') (an assignment, not a named argument); a 'local' in
a fallback (opts.scope || 'local', os.getenv("S", "local")), a ternary or
an unrelated key. A logout URL is local only when scope=local is in its
QUERY, which is all GoTrue reads: ?scope=local in the URL, httpie
scope==local, curl --url-query scope=local, URLSearchParams or urlencode of
{ scope: 'local' }, or a params / searchParams / query entry (axios,
requests, httpx, ky; not on a plain fetch(), which has no such option). A
scope in the request BODY (curl -d, json=, data=, body:, an axios second
argument, httpie scope=local) is ignored by GoTrue and does not count.

Where the rule applies
----------------------
  * Bash: text the command RUNS, or WRITES TO A CODE FILE.
      - inline code: node / bun / tsx / ts-node -e -p --eval --print,
        deno eval, python -c; bash / sh / zsh -c and eval are recursed;
      - heredoc bodies and here-strings fed to an interpreter that has no
        script argument (node <<EOF, python3 - <<EOF, cat <<EOF | node,
        node <<< '...'), or to a shell (recursed as commands);
      - text piped into such an interpreter (echo '...' | node);
      - text written to a file: cat / tee heredocs, echo / printf (or any
        tool not listed as prose below) with a > or >> redirect, tee in a
        pipeline, sed -i (the PATTERN half of each s/// is dropped first, so
        a sed that fixes the call passes);
      - $( ), backtick and ( ) group contents (recursed);
      - a runner wrapping a command (ssh, docker exec, watch, find -exec,
        xargs, yarn, pnpm): classified from the first interpreter word, and
        every multi-word argument is recursed as a command;
      - curl / wget / httpie / xh: the logout URL rule only (a body that
        merely mentions signOut() is data).
    Skipped as searches or prose: grep, rg, ag, ack, git, gh, tmux, claude,
    codex, echo / printf / cat without a redirect, sed without -i, an
    interpreter running a SCRIPT (its argv and stdin are data: a bg.mjs
    brief, a hook payload), and plain argv of an unknown tool (a test
    filter such as vitest -t 'calls signOut()').
  * Write / Edit / MultiEdit / NotebookEdit: only the NEW text (content,
    new_string, edits[].new_string, new_source), and only for a code file:
    .js .mjs .cjs .jsx .ts .mts .cts .tsx .py .pyw .ipynb .sh .bash .zsh
    .html .htm .vue .svelte .astro, or an extensionless file whose shebang
    names node, deno, bun, tsx, ts-node, python or a shell.
  * Line and block comments are ignored (// and /* */ anywhere, # when it
    starts a line or follows whitespace and is followed by a space).
  * The scope rule, for Write / Edit and for Bash writes to a file:
      - WARN only (exit 0 plus additionalContext) when the file is inside a
        git repo AND under app source (its first path part is one of
        SOURCE_TOP below, or it is under supabase/functions/, or it is a
        root middleware.* or auth.* file) AND no directory on its path is a
        scratch dir (SCRATCH_PARTS below). An app's own logout button
        legitimately signs its user out.
      - BLOCK everywhere else: /tmp, ~/Documents, rig folders, a repo's
        scripts/ or tools/, a repo root.
  * This hook and its suite are exempt: they have to quote the shapes.

What it ALLOWS
--------------
Local sign outs, dropping the session, and everything that is not a sign
out call: references (onClick={signOut}), method and function definitions,
TS signatures, def sign_out, look-alikes (handleSignOut(), signOutMock()),
a bare name in quotes ('signOut()' as a string to search for),
`supabase logout` (the CLI's own login), non-GoTrue /logout routes.

LIMITS, stated plainly
----------------------
  * A file that already exists is opaque: `node /tmp/x.mjs` shows only a
    path. The Write / Edit rule is what covers the incident route.
  * Edit checks only new_string: an edit that changes just the arguments of
    an existing call (new_string "{ scope: 'global' }") is not seen.
  * Indirection defeats it: code in a variable (node -e "$CODE", or a
    heredoc captured with X=$(cat <<EOF)), base64, signOut.call(auth), a
    method name built from strings, a heredoc fed to a sink it does not
    know (treated as prose), an unknown runner that takes code as an
    argument with no interpreter word in front of it. A scope computed at
    runtime is blocked, not allowed (fail closed).
  * A member call inside a string literal ("sb.auth.signOut()") is still
    treated as a call: generated or eval'd code looks exactly like that.
  * The admin form is recognised by its receiver's name. The admin API
    held under a name without "admin" and called with (jwt, 'local') is
    blocked (fail closed); any x.signOut(a, 'local') whose receiver x is
    named like adminAuth is read as the admin form.
  * A patch script that only MENTIONS the call (python -c
    "s.replace('signOut()', ...)") is blocked. Make such fixes with the Edit
    tool, which checks only the new text.

Exit 0 = allow (with an optional warning on stdout). Exit 2 = block.
Fails open: a malformed payload or any internal error exits 0.
Tests: python3 ~/.claude/hooks/supabase-signout-guard.test.py
"""

import bisect
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")

EXEMPT = {
    os.path.realpath(os.path.join(HERE, "supabase-signout-guard.py")),
    os.path.realpath(os.path.join(HERE, "supabase-signout-guard.test.py")),
    os.path.realpath(os.path.join(HOME, ".claude/hooks/supabase-signout-guard.py")),
    os.path.realpath(os.path.join(HOME, ".claude/hooks/supabase-signout-guard.test.py")),
}

# Cheap prefilter on the raw payload: nearly every call exits here. JSON may
# legally escape "/" as "\/", so the URL form tolerates that.
RAW_TRIGGER_RE = re.compile(r"signOut|sign_out|(?i:auth\\?/v1\\?/logout)")
TRIGGER_RE = re.compile(r"signOut|sign_out|(?i:auth/v1/logout)")

CALL_RE = re.compile(
    r"(?:(?<![\w$])(?P<name>signOut|sign_out)(?![\w$])"
    r"|\[\s*(?P<q>['\"`])(?P<bname>signOut|sign_out)(?P=q)\s*\])"
    r"\s*(?:\?\.\s*)?\("
)
# The whole value must be a local literal (after casts and parentheses are
# peeled off); '\'' is how a shell script quotes one inside single quotes.
LOCAL_LIT_RE = re.compile(
    r"""(?:'\\''|\\?['"`])local(?:'\\''|\\?['"`])|SignOutScope\.local|\.local"""
)
SCOPE_ENTRY_RE = re.compile(r"""^\\?['"`]?scope\\?['"`]?\s*:\s*(.*)$""", re.S)
NAMED_SCOPE_RE = re.compile(r"^scope\s*[:=]\s*(.*)$", re.S)
NAMED_COLON_RE = re.compile(r"^scope\s*:\s*(.*)$", re.S)
ADMIN_TAIL_RE = re.compile(r"(?i:admin)\w*\s*(?:\?\.|\.)?\s*$")
NONLOCAL_RE = re.compile(
    r"""\\?['"`](?:global|others)\\?['"`]"""
    r"""|\bSignOutScope\.(?:global|others)\b|(?<![\w$])\.(?:global|others)\b"""
)
LOGOUT_RE = re.compile(r"auth/v1/logout(?![\w-])", re.IGNORECASE)
# GoTrue's logout handler reads the scope from the QUERY string only, so a
# scope=local in a request body (-d, json=, data=, body:, an axios second
# argument, httpie scope=local) is ignored and the logout stays global.
URL_LOCAL_RE = re.compile(
    r"""\?(?:[^\s'"`&#?]*&)*scope=local\b"""
    r"""|(?<![\w'"=])scope==local\b"""
    r"""|--url-query(?:\s+|=)\\?['"]?scope=local\b"""
    r"""|\b(?:URLSearchParams|urlencode)\(\s*(?:\{[^{}]*?\bscope\\?['"`]?\s*:\s*\\?['"`]local\b"""
    r"""|\\?['"`]scope=local\b)"""
)
PARAMS_LOCAL_RE = re.compile(
    r"""\b(?:params|searchParams|query)\\?['"]?\s*[:=]\s*\{[^{}]*?\bscope\\?['"`]?\s*[:=]\s*\\?['"`]local\b"""
)
PLAIN_FETCH_RE = re.compile(r"(?<![\w$.])fetch\s*\([^()]*$")
URL_NONLOCAL_RE = re.compile(r"""scope\\?['"]?\s*(?:==|[=:])\s*\\?['"]?(?:global|others)\b""")

LINE_COMMENT_RE = re.compile(r"(?:^|(?<=\s))(?://|#(?=[ \t!]|$)).*$", re.M)

CODE_SUFFIXES = {
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx",
    ".py", ".pyw", ".ipynb", ".sh", ".bash", ".zsh",
    ".html", ".htm", ".vue", ".svelte", ".astro",
}
SHEBANG_RE = re.compile(
    r"^#!.*\b(?:node|nodejs|deno|bun|tsx|ts-node|python[0-9.]*|sh|bash|zsh)\b"
)

SOURCE_TOP = {
    "src", "app", "apps", "packages", "lib", "libs", "components", "pages",
    "api", "server", "client", "web", "frontend", "backend", "mobile", "ios",
    "android", "services", "modules", "public", "static", "functions",
    "test", "tests", "__tests__", "e2e", "spec", "cypress",
}
ROOT_SOURCE_STEMS = {"middleware", "auth"}
SCRATCH_PARTS = {"scripts", "script", "tools", "rig", "rigs", "scratch", "tmp", "temp", ".tmp"}

# --- shell vocabulary ------------------------------------------------------

KEYWORDS = {"!", "{", "}", "do", "then", "else", "elif", "if", "while", "until",
            "time", "exec", "command", "builtin", "noglob", "nocorrect"}
# wrapper -> flags that take a separate value
WRAPPERS = {
    "env": {"-u", "-S", "-C", "--unset", "--chdir"},
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"},
    "doas": {"-u"},
    "nohup": set(), "stdbuf": set(), "setsid": set(),
    "caffeinate": {"-t", "-w"},
    "nice": {"-n"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "npx": {"-p", "--package", "-c", "--call"},
    "bunx": {"-p", "--package"},
    "pnpx": set(),
    "dotenv": {"-e", "-c", "-v"},
}
TWO_WORD_WRAPPERS = {
    ("npm", "exec"), ("pnpm", "exec"), ("pnpm", "dlx"), ("yarn", "dlx"),
    ("yarn", "exec"), ("uv", "run"), ("poetry", "run"), ("pipenv", "run"),
    ("op", "run"), ("doppler", "run"), ("bun", "x"), ("rye", "run"),
}
NODE_LIKE = {"node", "nodejs", "bun", "tsx", "ts-node", "ts-node-esm", "esno", "esr", "vite-node"}
NODE_VALUE_FLAGS = {"-r", "--require", "--import", "--loader", "--experimental-loader",
                    "-C", "--conditions", "--input-type", "--env-file", "--title",
                    "--tsconfig", "--inspect-port"}
PY_RE = re.compile(r"^(?:python(?:\d+(?:\.\d+)?)?|pypy\d*)$")
PY_VALUE_FLAGS = {"-W", "-X", "-Q"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
NET_TOOLS = {"curl", "wget", "http", "https", "xh", "httpie", "curlie"}
PROSE_HEADS = {
    "grep", "egrep", "fgrep", "zgrep", "rg", "ag", "ack", "ack-grep", "git", "gh",
    "echo", "printf", "cat", "less", "more", "head", "tail", "bat", "wc", "sort",
    "uniq", "diff", "cmp", "jq", "yq", "ls", "tree", "stat", "file",
    "true", "false", "test", "[", "[[", "cd", "pushd", "popd", "read", "printenv",
    "which", "type", "man", "mkdir", "touch", "rm", "cp", "mv", "ln", "chmod",
    "pbcopy", "open", "say", "export", "local", "declare", "set", "unset",
    "tmux", "claude", "codex",
}
WRITERS = {"echo", "printf", "cat"}

HEREDOC_RE = re.compile(r"(?<!<)<<(-?)[ \t]*(?:(['\"])(\w[\w.-]*)\2|\\?(\w[\w.-]*))")
REDIRECT_RE = re.compile(
    r"""(?<![<>&\d])(?:\d*>>?|&>>?|>\|)(?!&)[ \t]*"""
    r"""(?:"([^"]*)"|'([^']*)'|([^\s'";|&<>()`]+))"""
)
SED_S_RE = re.compile(r"(?:^|(?<=[\s;{}]))s([^\w\s\\])((?:\\.|(?!\1).)*)\1")

MAX_DEPTH = 8
MAX_CALLS = 400
SHLEX_MAX = 32768  # above this, words_of uses split_words_linear
MAX_HEREDOCS_PER_LINE = 8


# ---------------------------------------------------------------------------
# detection on a piece of code
# ---------------------------------------------------------------------------

def strip_comments(code):
    # Block comments by str.find, not a lazy regex: an unterminated /* in a
    # large file made the regex quadratic.
    out, i = [], 0
    while True:
        j = code.find("/*", i)
        if j < 0:
            out.append(code[i:])
            break
        k = code.find("*/", j + 2)
        if k < 0:
            out.append(code[i:])
            break
        out.append(code[i:j] + " ")
        i = k + 2
    return LINE_COMMENT_RE.sub("", "".join(out))


def extract_args(text, open_idx):
    """(args, close_idx) for the call whose "(" is at open_idx."""
    depth, j, n = 0, open_idx, len(text)
    limit = min(n, open_idx + 800)
    while j < limit:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c in "'\"`":
            k = j + 1
            while k < limit and text[k] != c:
                k += 2 if text[k] == "\\" else 1
            j = k + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:j], j
        j += 1
    return text[open_idx + 1:limit], None


def split_top(s):
    """s split at commas outside quotes and brackets, each part stripped."""
    parts, depth, start, j, n = [], 0, 0, 0, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c in "'\"`":
            k = j + 1
            while k < n and s[k] != c:
                k += 2 if s[k] == "\\" else 1
            j = k + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(s[start:j].strip())
            start = j + 1
        j += 1
    parts.append(s[start:].strip())
    return parts


def is_local_value(v):
    """True when v, with casts and wrapping parentheses peeled off, is a
    local literal: 'local' as const, <const>'local', ('local')."""
    v = v.strip()
    for _ in range(8):
        before = v
        v = re.split(r"\s+(?:as|satisfies)\s+", v, maxsplit=1)[0].strip()
        v = re.sub(r"^<[\w.\s]+>\s*", "", v)
        if v.startswith("(") and v.endswith(")"):
            v = v[1:-1].strip()
        if v == before:
            break
    return bool(LOCAL_LIT_RE.fullmatch(v))


def options_local(arg):
    """An options object ({ scope: 'local' }, Python {"scope": "local"},
    dict(scope="local"), SignOutOptions(scope="local") or options={...})
    whose scope entry is a local literal, with no spread after it (a later
    ...opts or **opts can override the scope). A cast around the whole
    object ({ ... } as const, satisfies T, <T>{ ... }) is peeled off."""
    a = arg.strip()
    for _ in range(8):
        before = a
        m = re.match(r"^(.*[})])\s+(?:as|satisfies)\s+[^{}()]+$", a, re.S)
        if m:
            a = m.group(1).strip()
        a = re.sub(r"^<[\w.\s]+>\s*(?=[{(])", "", a)
        if a.startswith("(") and a.endswith(")"):
            a = a[1:-1].strip()
        if a == before:
            break
    a = re.sub(r"^\w+\s*=\s*(?=\{|dict\(|\w*Options\()", "", a)
    m = re.match(r"^(?:dict|\w*Options)\((.*)\)$", a, re.S)
    if m:
        entries, entry_re = split_top(m.group(1)), NAMED_SCOPE_RE
    elif a.startswith("{") and a.endswith("}"):
        entries, entry_re = split_top(a[1:-1]), SCOPE_ENTRY_RE
    else:
        return False
    local = False
    for entry in entries:
        m = entry_re.match(entry)
        if m:
            local = is_local_value(m.group(1))
        elif entry.startswith(("...", "**")):
            local = False
    return local


def args_local(args, admin, name):
    """Is the call provably scoped to 'local'? auth-js reads ONE argument
    for the scope: the client form signOut(options) destructures { scope }
    from its FIRST argument (so signOut('local') and signOut(jwt,
    { scope: 'local' }) fall back to 'global'), and the admin form
    signOut(jwt, scope) reads its SECOND. A named argument counts: Swift or
    Dart scope: .local, and for Python sign_out also scope="local". A JS
    signOut(scope = 'local') is an assignment, not a named argument."""
    parts = split_top(args)
    if options_local(parts[0]):
        return True
    named = NAMED_SCOPE_RE if name == "sign_out" else NAMED_COLON_RE
    for p in parts:
        m = named.match(p)
        if m and is_local_value(m.group(1)):
            return True
    return admin and len(parts) >= 2 and is_local_value(parts[1])


def one_line(s, limit=110):
    s = " ".join(s.split())
    return s if len(s) <= limit else s[:limit - 3] + "..."


def find_calls(code):
    """Sign out calls in code that are not provably local: [(snippet, reason)]."""
    if not TRIGGER_RE.search(code):
        return []
    text = strip_comments(code)
    hits = []
    for count, m in enumerate(CALL_RE.finditer(text)):
        if count >= MAX_CALLS:
            hits.append(("(more than %d sign out call shapes)" % MAX_CALLS,
                         "too many to check one by one"))
            break
        name = m.group("name") or m.group("bname")
        open_idx = m.end() - 1
        args, close = extract_args(text, open_idx)
        # A fixed look-behind window, not text[:m.start()]: copying and
        # scanning the whole prefix per call was quadratic on a large file.
        before = text[max(0, m.start() - 300):m.start()]
        if not m.group("bname") and before[-1:] in ("'", '"', "`"):
            continue  # 'signOut()' as a quoted name: a mention, not a call
        member = bool(m.group("bname")) or before.rstrip().endswith(".")
        if not member:
            if re.search(r"(?:\bfunction\s*\*?|\bdef)\s*$", before):
                continue  # a definition, not a call
            if close is not None and name == "signOut":
                after = text[close + 1:close + 40].lstrip()
                if after.startswith(("{", "=>")) or (after.startswith(":") and not after.startswith("::")):
                    continue  # method shorthand, arrow or TS signature
        admin = bool(ADMIN_TAIL_RE.search(before))
        if args_local(args, admin, name) and not NONLOCAL_RE.search(args):
            continue
        end = close + 1 if close is not None else min(len(text), open_idx + 60)
        lo = max(0, m.start() - 200)
        nl = text.rfind("\n", lo, m.start())
        line_start = nl + 1 if nl >= 0 else lo
        prefix = re.split(r"[;{}]", text[line_start:m.start()])[-1].lstrip()[-50:]
        snippet = one_line(prefix + text[m.start():end])
        bare = args.strip()
        parts = split_top(args)
        first = parts[0]
        if bare in ("", "{}", "{ }", "undefined", "None"):
            reason = "no scope given, and the default is 'global'"
        elif not admin and is_local_value(first):
            reason = ("a bare 'local' is not the options object, so the scope falls back"
                      " to 'global'; pass { scope: 'local' }")
        elif re.search(r"""['"`]others['"`]|\.others\b""", args):
            reason = "scope 'others' ends every OTHER session of the account, the owner's included"
        elif re.search(r"""['"`]global['"`]|\.global\b""", args):
            reason = "scope 'global' ends every session of the account"
        elif any(options_local(p) for p in parts[1:]):
            reason = ("the scope sits in the wrong argument: the client form reads only its first,"
                      " signOut({ scope: 'local' }), and the admin form only its second,"
                      " signOut(jwt, 'local'); anywhere else it falls back to 'global'")
        elif name == "signOut" and re.match(r"^scope\s*=[^=]", first):
            reason = ("scope = 'local' inside a JS call is an assignment, not a named argument,"
                      " so the scope falls back to 'global'; pass { scope: 'local' }")
        else:
            reason = "the scope is not a literal 'local', and the default is 'global'"
        hits.append((snippet, reason))
    for m in LOGOUT_RE.finditer(text):
        window = text[m.end():m.end() + 300]
        nxt = [x.start() for x in (LOGOUT_RE.search(window), CALL_RE.search(window)) if x]
        if ";" in window:
            nxt.append(window.index(";"))
        if nxt:
            window = window[:min(nxt)]
        line_start = text.rfind("\n", 0, m.start()) + 1
        # A params / searchParams / query entry is a query param for axios,
        # requests, httpx or ky; a plain fetch() has no such option.
        stmt = re.split(r"[;\n]", text[max(line_start, m.start() - 200):m.start()])[-1]
        local = URL_LOCAL_RE.search(window) or (
            PARAMS_LOCAL_RE.search(window) and not PLAIN_FETCH_RE.search(stmt))
        if local and not URL_NONLOCAL_RE.search(window):
            continue
        snippet = one_line(text[max(line_start, m.start() - 40):m.end() + 30])
        hits.append((snippet, "POST /auth/v1/logout without scope=local; GoTrue defaults to 'global'"))
    return hits


# ---------------------------------------------------------------------------
# where the text is going: the scope rule
# ---------------------------------------------------------------------------

def resolve(path, cwd):
    p = path.strip()
    p = re.sub(r"^\$\{?HOME\}?", HOME, p)
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    try:
        return os.path.realpath(p)
    except (OSError, ValueError):
        return os.path.normpath(p)


def find_repo(real):
    d = os.path.dirname(real)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def is_code_file(real, content):
    ext = os.path.splitext(real)[1].lower()
    if ext in CODE_SUFFIXES:
        return True
    if ext:
        return False
    head = (content or "").lstrip("﻿")[:200]
    if not head.startswith("#!"):
        try:
            with open(real, "r", errors="replace") as fh:
                head = fh.read(200)
        except OSError:
            head = ""
    return bool(SHEBANG_RE.match(head))


def file_scope(path, cwd, content=None):
    """'skip' (not code) | 'exempt' | 'warn' (app source) | 'block'."""
    real = resolve(path, cwd)
    if real in EXEMPT:
        return "exempt"
    if "$" in real and not os.path.splitext(real)[1]:
        return "block"  # an unresolved variable: the target cannot be known
    if not is_code_file(real, content):
        return "skip"
    root = find_repo(real)
    if root is None:
        return "block"
    parts = os.path.relpath(real, root).split(os.sep)
    if any(d.lower() in SCRATCH_PARTS for d in parts[:-1]):
        return "block"
    if len(parts) > 1 and (parts[0] in SOURCE_TOP or parts[:2] == ["supabase", "functions"]):
        return "warn"
    if len(parts) == 1 and os.path.splitext(parts[0])[0] in ROOT_SOURCE_STEMS:
        return "warn"
    return "block"


# ---------------------------------------------------------------------------
# shell parsing
# ---------------------------------------------------------------------------

def split_heredocs(cmd):
    """(skeleton, [(opener_line, body)]). Unterminated heredocs stay inline."""
    lines = cmd.split("\n")
    # Line index by stripped text, so finding a terminator is a lookup: a
    # scan per opener was quadratic on code full of 1<<n. (<<- strips only
    # tabs, and strip() drops them too, so one index serves both forms.)
    where = {}
    for idx, l in enumerate(lines):
        where.setdefault(l.strip(), []).append(idx)
    kept, docs, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for m in list(HEREDOC_RE.finditer(line))[:MAX_HEREDOCS_PER_LINE]:
            delim = m.group(3) or m.group(4)
            hits = where.get(delim, [])
            pos = bisect.bisect_left(hits, i)
            if pos >= len(hits):
                break  # unterminated: not a heredoc as far as we can tell
            j = hits[pos]
            docs.append((line, "\n".join(lines[i:j])))
            i = j + 1
    return "\n".join(kept), docs


def scan_shell(text):
    """Top-level split into pipelines of stage strings, plus the contents of
    every closed OUTERMOST $( ), backtick and ( ) group."""
    pipelines, stages, cur, subs, stack = [], [], [], [], []
    i, n = 0, len(text)

    def close_sub(end):
        # Only the outermost group is recorded; its own nested groups are
        # found when it is analysed. Recording every depth here made the
        # recursion re-scan each level again (exponential on deep nesting).
        start = stack.pop()[1]
        if not any(k in ("$(", "(", "`") for k, _ in stack):
            subs.append(text[start:end])

    def flush_stage():
        s = "".join(cur).strip()
        cur.clear()
        if s:
            stages.append(s)

    def flush_pipeline():
        flush_stage()
        if stages:
            pipelines.append(list(stages))
        stages.clear()

    while i < n:
        c = text[i]
        top = stack[-1][0] if stack else None
        if c == "\\":
            cur.append(text[i:i + 2])
            i += 2
            continue
        if top == '"':
            if c == '"':
                stack.pop()
            elif text.startswith("$(", i):
                stack.append(["$(", i + 2])
                cur.append("$(")
                i += 2
                continue
            elif c == "`":
                stack.append(["`", i + 1])
            cur.append(c)
            i += 1
            continue
        if top == "`":
            if c == "`":
                close_sub(i)
            cur.append(c)
            i += 1
            continue
        if c == "'" or text.startswith("$'", i):
            j = i + (2 if c == "$" else 1)
            while j < n and text[j] != "'":
                j += 2 if (c == "$" and text[j] == "\\") else 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if c == '"':
            stack.append(['"', i + 1])
        elif text.startswith("$(", i):
            stack.append(["$(", i + 2])
            cur.append("$(")
            i += 2
            continue
        elif c == "`":
            stack.append(["`", i + 1])
        elif c == "(":
            stack.append(["(", i + 1])
        elif c == ")" and top in ("$(", "("):
            close_sub(i)
        elif c == "#" and top is None and (i == 0 or text[i - 1] in " \t\n;|&("):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif top is None and c in "\n;":
            flush_pipeline()
            i += 1
            continue
        elif top is None and c == "&":
            if text.startswith("&&", i):
                flush_pipeline()
                i += 2
                continue
            if not (text.startswith("&>", i) or (i > 0 and text[i - 1] in "<>")):
                flush_pipeline()
                i += 1
                continue
        elif top is None and c == "|":
            if text.startswith("||", i):
                flush_pipeline()
                i += 2
                continue
            if not (i > 0 and text[i - 1] == ">"):
                flush_stage()
                i += 2 if text.startswith("|&", i) else 1
                continue
        cur.append(c)
        i += 1
    flush_pipeline()
    return pipelines, subs


def split_words_linear(text):
    """shlex.split(text, posix=True) in linear time. shlex grows each token
    one character at a time, which is quadratic: a 1 MB inline command took
    12 s and a 2 MB commit message 164 s, past the 10 s hook timeout. Same
    rules: whitespace splits, a backslash outside quotes escapes the next
    character, single quotes are literal, and inside double quotes a
    backslash escapes only a double quote or a backslash. Raises ValueError
    on an unclosed quote or a trailing backslash, as shlex does."""
    words, buf, in_word, i, n = [], [], False, 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            if in_word:
                words.append("".join(buf))
                buf, in_word = [], False
            i += 1
            continue
        in_word = True
        if c == "\\":
            if i + 1 >= n:
                raise ValueError("No escaped character")
            buf.append(text[i + 1])
            i += 2
        elif c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                raise ValueError("No closing quotation")
            buf.append(text[i + 1:j])
            i = j + 1
        elif c == '"':
            j = start = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n and text[j + 1] in '"\\':
                    buf.append(text[start:j])
                    buf.append(text[j + 1])
                    j += 2
                    start = j
                elif text[j] == "\\" and j + 1 >= n:
                    raise ValueError("No escaped character")
                else:
                    j += 1
            if j >= n:
                raise ValueError("No closing quotation")
            buf.append(text[start:j])
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n\\'\"":
                j += 1
            buf.append(text[i:j])
            i = j
    if in_word:
        words.append("".join(buf))
    return words


def words_of(text):
    try:
        if len(text) > SHLEX_MAX:
            return split_words_linear(text)
        return shlex.split(text, posix=True)
    except ValueError:
        return None


def strip_prefixes(words):
    # An index walk, not list.pop(0): popping the front per prefix word was
    # quadratic on a long run of VAR=x prefixes.
    w, i, n = words, 0, len(words)
    changed = True
    while i < n and changed:
        changed = False
        if w[i] in KEYWORDS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w[i]):
            i += 1
            changed = True
            continue
        head = os.path.basename(w[i])
        if i + 1 < n and (head, w[i + 1]) in TWO_WORD_WRAPPERS:
            i += 2
            value_flags = set()
        elif head in WRAPPERS:
            value_flags = WRAPPERS[head]
            i += 1
        else:
            break
        changed = True
        while i < n:
            t = w[i]
            if t == "--":
                i += 1
                break
            if t.startswith("-"):
                i += 1
                if t in value_flags and i < n:
                    i += 1
                continue
            if head == "env" and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
                i += 1
                continue
            break
    return list(w[i:])


def first_positional(args, value_flags):
    skip = False
    for t in args:
        if skip:
            skip = False
            continue
        if t == "-":
            return "-"
        if t.startswith("-"):
            if t in value_flags:
                skip = True
            continue
        return t
    return None


def redirect_targets(raw):
    return [m.group(1) or m.group(2) or m.group(3) for m in REDIRECT_RE.finditer(raw)]


def classify(words, raw):
    """What a stage (or a heredoc opener piece) does with text.

    kind: prose | scan | net | embedded | recurse | stdin_code | stdin_shell |
          script | file | tee | group
    """
    if raw.lstrip().startswith("("):
        return {"kind": "group"}
    if words is None:
        return {"kind": "scan", "text": raw}
    herestring, clean = None, []
    it = iter(words)
    for t in it:
        if t == "<<<":
            herestring = next(it, "")
        elif t.startswith("<<<"):
            herestring = t[3:]
        else:
            clean.append(t)
    if herestring is not None:
        info = classify(clean, raw.replace("<<<", " "))
        if info["kind"] in ("stdin_code", "stdin_shell"):
            return {"kind": "scan", "text": herestring}
        return info
    w = strip_prefixes(words)
    if not w:
        return {"kind": "prose", "text": ""}
    head = os.path.basename(w[0])
    args = w[1:]
    joined = "\n".join(args)

    if head in NODE_LIKE:
        for t in args:
            if t in ("-e", "--eval", "-p", "--print") or t.startswith(("--eval=", "--print=")) \
                    or (re.fullmatch(r"-[a-zA-Z]{2,}", t) and set(t[1:]) & {"e", "p"}):
                return {"kind": "scan", "text": joined}
        pos = first_positional(args, NODE_VALUE_FLAGS)
        return {"kind": "stdin_code"} if pos in (None, "-") else {"kind": "script"}
    if head == "deno":
        if args[:1] == ["eval"]:
            return {"kind": "scan", "text": joined}
        rest = args[1:] if args[:1] in (["run"], ["x"]) else args
        pos = first_positional(rest, set())
        return {"kind": "stdin_code"} if pos in (None, "-") else {"kind": "script"}
    if PY_RE.match(head):
        for t in args:
            if t == "-c" or (re.fullmatch(r"-[a-zA-Z]{2,}", t) and "c" in t[1:]):
                return {"kind": "scan", "text": joined}
            if t == "-m":
                return {"kind": "script"}
        pos = first_positional(args, PY_VALUE_FLAGS)
        return {"kind": "stdin_code"} if pos in (None, "-") else {"kind": "script"}
    if head in SHELLS:
        for k, t in enumerate(args):
            if t == "-c" or (re.fullmatch(r"-[a-zA-Z]{2,}", t) and "c" in t[1:]):
                rest = [x for x in args[k + 1:] if not x.startswith("-")]
                return {"kind": "recurse", "cmd": rest[0] if rest else ""}
        pos = first_positional(args, set())
        return {"kind": "stdin_shell"} if pos in (None, "-s", "-") else {"kind": "script"}
    if head == "eval":
        return {"kind": "recurse", "cmd": " ".join(args)}
    if head == "tee":
        return {"kind": "tee", "paths": [a for a in args if not a.startswith("-")]}
    if head in ("sed", "gsed"):
        if any(t.startswith("-i") or t.startswith("--in-place") for t in args):
            script = "\n".join(t for t in args[:-1] if not t.startswith("-"))
            script = SED_S_RE.sub(lambda m: "s" + m.group(1) + m.group(1), script)
            return {"kind": "file", "text": script, "paths": args[-1:]}
        return {"kind": "prose", "text": ""}
    if head in WRITERS:
        targets = redirect_targets(raw)
        if targets:
            return {"kind": "file", "text": joined, "paths": targets}
        return {"kind": "prose", "text": joined}
    if head in NET_TOOLS:
        return {"kind": "net", "text": joined}
    if head in PROSE_HEADS:
        return {"kind": "prose", "text": ""}
    targets = redirect_targets(raw)
    if targets:  # an unknown tool printing into a file: its argv may be the file's code
        return {"kind": "file", "text": joined, "paths": targets}
    # Unknown head. A runner (ssh, docker exec, watch, gtimeout, find -exec,
    # parallel) can wrap a real command: classify from the first interpreter
    # word, and recurse into every multi-word argument as a command. Plain
    # argv text (a test filter, a peer message, a script's options) is data.
    for k in range(1, len(w)):
        if is_command_word(w[k]):
            return classify(w[k:], shlex.join(w[k:]))
    return {"kind": "embedded", "cmds": [a for a in args if re.search(r"\s", a)]}


def is_command_word(word):
    b = os.path.basename(word)
    return (b in NODE_LIKE or b in SHELLS or b in ("deno", "eval") or bool(PY_RE.match(b))
            or b in WRAPPERS or b in ("npm", "pnpm", "yarn", "uv", "poetry", "pipenv", "op",
                                     "doppler", "rye"))


def opener_sink(line, cwd):
    """('code' | 'shell' | 'file' | 'prose', paths) for a heredoc opener line."""
    text = HEREDOC_RE.sub(" ", line)
    kinds, paths = set(), []
    for piece in re.split(r"\$\(|[;&|()`]", text):
        if not piece.strip():
            continue
        ws = words_of(piece)
        if ws is None:
            ws = piece.replace('"', " ").replace("'", " ").split()
        info = classify(ws, piece)
        k = info["kind"]
        if k in ("scan", "stdin_code"):
            kinds.add("code")
        elif k in ("stdin_shell", "recurse"):
            kinds.add("shell")
        elif k == "tee":
            paths += info["paths"]
    paths += redirect_targets(text)
    if "code" in kinds:
        return "code", []
    if "shell" in kinds:
        return "shell", []
    if paths:
        return "file", paths
    return "prose", []


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

class Findings:
    def __init__(self):
        self.blocks, self.warns, self._seen = [], [], set()

    def add(self, level, where, hits):
        for snippet, reason in hits:
            key = (level, snippet, reason)
            if key in self._seen:
                continue
            self._seen.add(key)
            (self.blocks if level == "block" else self.warns).append((where, snippet, reason))

    def scoped(self, where, hits, paths, cwd, content):
        if not hits:
            return
        levels = [file_scope(p, cwd, content) for p in paths if p] or ["block"]
        if "block" in levels:
            self.add("block", where, hits)
        elif "warn" in levels:
            self.add("warn", where, hits)


def analyze_bash(cmd, cwd, out, depth=0):
    if depth > MAX_DEPTH or not TRIGGER_RE.search(cmd):
        return
    skeleton, docs = split_heredocs(cmd)
    for opener, body in docs:
        if not TRIGGER_RE.search(body):
            continue
        kind, paths = opener_sink(opener, cwd)
        if kind == "code":
            out.add("block", "heredoc fed to an interpreter", find_calls(body))
        elif kind == "shell":
            analyze_bash(body, cwd, out, depth + 1)
        elif kind == "file":
            where = "heredoc written to " + ", ".join(paths)
            out.scoped(where, find_calls(body), paths, cwd, body)

    pipelines, subs = scan_shell(skeleton)
    for sub in subs:
        analyze_bash(sub, cwd, out, depth + 1)
    for pipeline in pipelines:
        infos = [classify(words_of(stage), stage) for stage in pipeline]
        # Upstream text is only needed by a stdin or tee stage, and its hits
        # only change when a stage with text is added: cache them, or a long
        # pipeline rebuilt and rescanned it per stage (quadratic).
        texts = [x.get("text", "") for x in infos]
        cached_upto, cached = -1, []

        def upstream_hits(k):
            nonlocal cached_upto, cached
            last = max((i for i in range(cached_upto + 1, k) if texts[i]), default=None)
            if last is not None or cached_upto < 0:
                cached = find_calls("\n".join(texts[:k]))
            cached_upto = k - 1
            return cached

        for k, info in enumerate(infos):
            kind = info["kind"]
            if kind == "scan":
                out.add("block", "Bash command", find_calls(info["text"]))
            elif kind == "net":
                out.add("block", "HTTP call", [h for h in find_calls(info["text"])
                                               if h[1].startswith("POST /auth/v1/logout")])
            elif kind == "embedded":
                for sub in info["cmds"]:
                    analyze_bash(sub, cwd, out, depth + 1)
            elif kind == "recurse":
                analyze_bash(info["cmd"], cwd, out, depth + 1)
            elif kind == "file":
                where = "Bash write to " + ", ".join(info["paths"])
                out.scoped(where, find_calls(info["text"]), info["paths"], cwd, info["text"])
            if k == 0:
                continue
            if kind in ("stdin_code", "stdin_shell"):
                out.add("block", "text piped into an interpreter", upstream_hits(k))
            elif kind == "tee":
                hits = upstream_hits(k)
                if hits:
                    where = "tee to " + ", ".join(info["paths"])
                    out.scoped(where, hits, info["paths"], cwd, "\n".join(texts[:k]))


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

WHY = (
    "Why: a global sign out ends every session of that account, including the owner's.\n"
    "supabase-js signOut(), Python sign_out(), auth.admin.signOut(jwt) and POST\n"
    "/auth/v1/logout all default to scope 'global'. On 2026-09-29 a rig that minted an\n"
    "admin session for the owner's own account ended with signOut() and signed the owner\n"
    "out of Operator Base on the web, in the app and on agents.operatorbase.app at once."
)
FIX = (
    "Fix: use scope: 'local', or just drop the session (a rig session needs no clean\n"
    "up; let the process exit).\n"
    "  JS/TS    await sb.auth.signOut({ scope: 'local' })     (options object FIRST, no jwt)\n"
    "  admin    await admin.auth.admin.signOut(jwt, 'local')  (plain 'local' SECOND)\n"
    "  Python   sb.auth.sign_out({\"scope\": \"local\"})\n"
    "  REST     POST <project url>/auth/v1/logout?scope=local (in the URL; a body scope is ignored)"
)
MENTION = (
    "If this text only MENTIONS the call: searches (grep, rg, git) and prose (echo,\n"
    "git commit, a .md file) are not checked. Make code fixes with the Edit tool, which\n"
    "checks only the new text. There is no override; do not reword the call to get past\n"
    "this guard."
)


def block_message(items):
    lines = ["BLOCKED (supabase-signout-guard): a Supabase sign out without scope 'local'.", ""]
    for where, snippet, reason in items[:6]:
        lines.append(f"  - {where}: {snippet}")
        lines.append(f"    {reason}")
    if len(items) > 6:
        lines.append(f"  - ... and {len(items) - 6} more")
    lines += ["", WHY, "", FIX, "", MENTION]
    return "\n".join(lines) + "\n"


def warn_context(items):
    lines = ["supabase-signout-guard (warning only, app source): a Supabase sign out without scope 'local':"]
    for where, snippet, reason in items[:6]:
        lines.append(f"  - {where}: {snippet} ({reason})")
    lines.append(
        "In app code a logout button signing its own user out is fine. If this code runs as a rig,"
        " script or test against a real account, use scope: 'local' or drop the session: a global"
        " sign out ends every session of that account, including the owner's."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def written_text(ti):
    chunks = []
    for field in ("content", "new_string", "new_source"):
        val = ti.get(field)
        if isinstance(val, str):
            chunks.append(val)
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("new_string"), str):
            chunks.append(e["new_string"])
    return "\n".join(chunks)


def decide(payload):
    """(exit_code, stderr, stdout)."""
    if not isinstance(payload, dict):
        return 0, "", ""
    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        return 0, "", ""
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    out = Findings()

    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or not TRIGGER_RE.search(cmd):
            return 0, "", ""
        analyze_bash(cmd, cwd, out)
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if not isinstance(path, str) or not path:
            return 0, "", ""
        body = written_text(ti)
        if not TRIGGER_RE.search(body):
            return 0, "", ""
        out.scoped(f"{tool} {path}", find_calls(body), [path], cwd,
                   ti.get("content") if isinstance(ti.get("content"), str) else body)
    else:
        return 0, "", ""

    if out.blocks:
        return 2, block_message(out.blocks), ""
    if out.warns:
        ctx = {"hookSpecificOutput": {
            # No permissionDecision: a warn-only hook must not approve the call
            # on the permission system's behalf.
            "hookEventName": "PreToolUse",
            "additionalContext": warn_context(out.warns),
        }}
        return 0, "", json.dumps(ctx)
    return 0, "", ""


def main():
    raw = sys.stdin.read()
    if not raw.strip() or not RAW_TRIGGER_RE.search(raw):
        return 0
    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    code, err, stdout = decide(payload)
    if err:
        sys.stderr.write(err)
        sys.stderr.flush()
    if stdout:
        print(stdout, flush=True)
    return code


if __name__ == "__main__":
    # Fail-open contract: this runs before every Bash, Write and Edit call.
    # Any error exits 0; only a deliberate block exits 2.
    try:
        rc = main()
    except BaseException:
        rc = 0
    sys.exit(2 if rc == 2 else 0)
