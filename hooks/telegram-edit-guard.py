#!/usr/bin/env python3
r"""PreToolUse guard (Bash): two Telegram Bot API traps.

  1. an edit call (editMessage*) used to "check" a message exists;
  2. curl -F / --form on a free-text field (caption, text, question,
     explanation), which cuts the text at the first ";". See "The -F trap"
     below; everything above it is about the edit trap.

Why this exists
---------------
A bot has no way to read a message back by id, so agents kept "checking"
that a message they sent still exists by EDITING it: the same content
answers "message is not modified", a missing id answers "message to edit not
found". The trap: an edit with DIFFERENT content is not a probe. It replaces
what the owner sees on his phone, and there is no undo.

  * message 21104: M probed it with editMessageText carrying another text,
    overwrote the intro, and had to restore it by hand.
  * 2026-10-02: worker bg64 re-sent the same caption with editMessageCaption
    on 21231 to "probe" it, and the qa-agent verifier of bg72 wrote
    /tmp/qa-thumbs/tg-probe.py and tg-probe.sh and called
    editMessageReplyMarkup on 21318 to 21322. Both answered "message is not
    modified"; the next one with different content overwrites a real message.

The standing prose rule failed three times (a memory note even taught the
probe). This hook is the mechanism.

What it BLOCKS (exit 2, message on stderr)
------------------------------------------
A Bash command whose EXECUTED text holds both
  * a Bot API signal: the host api.telegram.org, a bot token literal,
    TELEGRAM_BOT_TOKEN, or a /bot<token>/ URL path ($TOK, ${TOK}, {tok},
    ' + tok); and
  * an edit method: editMessageText, editMessageCaption, editMessageMedia,
    editMessageReplyMarkup, editMessageLiveLocation (any editMessage*, in any
    case, because the Bot API matches method names case-insensitively), or
    the snake_case library names (edit_message_text and friends).
The two need not sit in the same word or the same segment, so all of these
count: a method in a variable (M=editMessageText; curl "$API/$M"), a -d / -F
/ --data-urlencode field, a URL path, inline code (node -e, python3 -c,
bash -c, eval), a heredoc fed to an interpreter or a shell, text piped into
one, a for loop or xargs over ids, and a script FILE written by a heredoc,
echo, printf or tee (.py .js .mjs .sh ..., or a #! body: the bg72 shape).

What is NOT checked (prose)
---------------------------
  * searches, VCS and filters: grep, rg, ag, ack, git, gh, sed, awk, jq,
    head, tail, find without -exec, tmux, claude, codex;
  * echo / printf / cat / tee with no redirect into a code file and no pipe
    into an interpreter or shell; a heredoc into a .md / .txt / .json, or
    into a git commit message;
  * the value of a text or caption field (text=..., "caption": "...",
    --data-urlencode "text=..."): a send whose text MENTIONS an edit method
    is a send;
  * shell comments.

The override
------------
A deliberate edit of a message YOU sent in this run: start the command with
TG_EDIT_OK=1 (leading comment lines may come first) and give the reason in a
shell comment of at least two words. TG_EDIT_OK=1 with no reason comment is
still blocked.

LIMITS, stated plainly
----------------------
  * A script that already exists is opaque: `python3 /tmp/x.py` shows only a
    path. The heredoc or echo that WRITES it is the catch point. A file made
    with the Write tool is not seen: this hook is Bash only, which also keeps
    the bridge daemon's own source (it edits its live bubbles from node) out
    of scope.
  * Indirection defeats it: a method or host built from pieces
    ('edit' + 'MessageText'), base64, a token and host both read from a file
    inside a script the command does not show.
  * A heredoc written to a path held in a variable is resolved only from an
    assignment in the same command (B=/tmp/x.md; cat > $B <<EOF); an
    unresolved extensionless target counts as prose unless the body starts
    with #!.
  * Fail closed on the rest: a file path or a non text/caption argument that
    merely contains a method name, or an inline analysis script that
    mentions both a method and the host, is blocked. Search with grep or rg
    instead.

The -F trap
-----------
curl -F reads a ";" inside a value as the start of a field parameter
(;type=, ;filename=) and silently drops the rest: exit 0, "ok":true, a cut
message. On 2026-10-02 a worker sent -F "caption=... (web live; probe
passed ...)" and message 21478 arrived ending "(web live". A local replay
(curl 8.7.1, bash and zsh, a capture server, no Telegram) measured:

  -F "caption=a (web live; probe passed)"    sent "a (web live"
  --form 'text=web live; probe passed'       sent "web live"
  --form-string 'caption=...; ... $5'        sent verbatim
  --form-string "caption=cost $5; x"         sent "cost ; x" (the SHELL ate $5)
  -F "caption=<cap.txt"                      sent the file verbatim, ; and $ kept
  -F caption=<cap.txt  (unquoted)            sent an EMPTY caption (a redirect)
  -F "caption=@cap.txt"                      sent a file part, not text

So it BLOCKS, when the command's executed text carries a Bot API signal (as
above) and a curl: a -F / --form (also -Fcaption=..., bundled -sSF, a
"-F", "caption=..." list in inline code) on caption=, text=, question= or
explanation=, with or without a ";" today, because the next text may have
one. Allowed: --form-string, and a QUOTED <file (-F "caption=<f",
-F caption="<f", -F caption=\<f). File and other fields (photo=@,
document=@, media=, thumbnail=@, chat_id=, parse_mode=, reply_markup=,
caption_entities=) are left alone. TG_EDIT_OK=1 does not cover this check,
and there is no override: the two allowed forms are the fix.
Limits: a field name held in a variable (-F "$FIELD") is not seen; a ";"
inside media= or reply_markup= JSON is cut too, but Telegram then rejects
the broken JSON loudly, so those stay on -F. The Bot API signal and the curl
are looked for across the whole command (a helper function defined in it
counts), so a -F text= to ANOTHER host in a command that also calls
Telegram is blocked too: split it into two Bash calls.

Exit 0 = allow. Exit 2 = block. Fails open: a malformed payload or any
internal error exits 0.
Tests: python3 ~/.claude/hooks/telegram-edit-guard.test.py
"""

import bisect
import json
import os
import re
import shlex
import sys

# Cheap prefilter on the raw payload: nearly every Bash call exits here.
RAW_TRIGGER_RE = re.compile(r"edit_?message", re.I)
RAW_FORM_TRIGGER_RE = re.compile(r"-[\w#:]*F|--form")

# The -F trap. The flag (-F, --form but not --form-string, or F closing a
# bundle of curl's boolean short flags: -sSF), then whitespace, a line
# continuation, nothing (-Fcaption=), or a "-F", "caption=" list separator,
# then a free-text field. q is the quote opening the field, val the value's
# first characters.
FORM_FIELD_RE = re.compile(
    r"(?<![\w-])(?:-[0-6#:sSfLkvigGIjJlnNOqRZ]*F|--form(?![\w-]))"
    r"(?:['\"]\s*,\s*|(?:[ \t]|\\\n)*)"
    r"(?P<q>\$?['\"]?)"
    r"(?P<key>(?i:caption|text|question|explanation))="
    r"(?P<val>.{0,2})",
    re.S,
)
CURL_RE = re.compile(r"(?<![\w-])curl(?![\w-])", re.I)
# no \b: a token sits right after "bot" in a URL, with no word boundary
TOKEN_LITERAL_RE = re.compile(r"(?<!\d)\d{6,12}:[A-Za-z0-9_-]{30,}")

EDIT_RE = re.compile(r"(?<![A-Za-z0-9])edit(?:Message[A-Za-z]*|_message_[a-z_]+)", re.I)
TG_RE = re.compile(
    r"api\.telegram\.org"
    r"|\b\d{6,12}:[A-Za-z0-9_-]{30,}"
    r"|TELEGRAM_BOT_TOKEN"
    r"|/bot(?=[$`'\"{+]|\d+:)",
    re.I,
)

# TG_EDIT_OK=1 as the first word of the command (comment lines may precede).
OVERRIDE_RE = re.compile(r"\A(?:[ \t]*(?:#[^\n]*)?\n)*[ \t]*(?:export[ \t]+)?TG_EDIT_OK=1(?=[\s;&]|\Z)")

# A text / caption field whose VALUE is free text, not a method position.
FREE_KEY_RE = re.compile(r"""(?<![\w.-])(['"`]?)(?:text|caption)(['"`]?)\s*(?:=(?!=)|:)\s*""", re.I)

CODE_EXT = {
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx",
    ".sh", ".bash", ".zsh", ".command", ".rb", ".pl", ".php", ".applescript", ".scpt",
}

KEYWORDS = {"!", "{", "}", "do", "then", "else", "elif", "if", "while", "until",
            "time", "exec", "command", "builtin", "noglob", "nocorrect"}
# wrapper -> flags that take a separate value
WRAPPERS = {
    "env": {"-u", "-S", "-C", "--unset", "--chdir"},
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"},
    "nohup": set(), "stdbuf": set(), "setsid": set(), "arch": set(),
    "caffeinate": {"-t", "-w"},
    "nice": {"-n"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "npx": {"-p", "--package", "-c", "--call"},
    "bunx": {"-p", "--package"},
    "dotenv": {"-e", "-c", "-v"},
}
TWO_WORD_WRAPPERS = {
    ("npm", "exec"), ("pnpm", "exec"), ("pnpm", "dlx"), ("yarn", "dlx"),
    ("yarn", "exec"), ("uv", "run"), ("poetry", "run"), ("pipenv", "run"),
    ("op", "run"), ("doppler", "run"), ("bun", "x"), ("rye", "run"),
}
INTERPRETERS = {"node", "nodejs", "bun", "deno", "tsx", "ts-node", "esno", "vite-node",
                "ruby", "perl", "php", "osascript", "swift"}
PY_RE = re.compile(r"^(?:python(?:\d+(?:\.\d+)?)?|pypy\d*)$")
INLINE_FLAGS = {"-e", "-c", "-p", "--eval", "--print", "eval"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
WRITERS = {"echo", "printf", "cat", "tee"}
PROSE_HEADS = {
    "grep", "egrep", "fgrep", "zgrep", "rg", "ag", "ack", "ack-grep", "git", "gh",
    "sed", "gsed", "awk", "gawk", "jq", "yq", "head", "tail", "less", "more", "bat",
    "wc", "sort", "uniq", "diff", "cmp", "cut", "tr", "column", "ls", "tree", "stat",
    "file", "test", "[", "[[", "cd", "pushd", "popd", "read", "printenv", "which",
    "type", "whence", "man", "mkdir", "touch", "rm", "cp", "mv", "ln", "chmod",
    "pbcopy", "open", "say", "true", "false", "sleep", "date", "basename", "dirname",
    "realpath", "readlink", "tmux", "claude", "codex",
}

HEREDOC_RE = re.compile(r"(?<!<)<<(-?)[ \t]*(?:(['\"])(\w[\w.-]*)\2|\\?(\w[\w.-]*))")
REDIRECT_RE = re.compile(
    r"""(?<![<>&\d])(?:\d*>>?|&>>?|>\|)(?!&)[ \t]*"""
    r"""(?:"([^"]*)"|'([^']*)'|([^\s'";|&<>()`]+))"""
)
ASSIGN_RE = re.compile(r"""(?:^|[\s;&|(])([A-Za-z_]\w*)=("[^"\n]*"|'[^'\n]*'|[^\s;&|()]+)""")

MAX_DEPTH = 8
SHLEX_MAX = 32768  # above this, words_of uses split_words_linear
MAX_HEREDOCS_PER_LINE = 8


# ---------------------------------------------------------------------------
# shell parsing (trimmed from supabase-signout-guard.py, where it is tested)
# ---------------------------------------------------------------------------

def split_heredocs(cmd):
    """(skeleton, [(opener_line, marker_start, marker_end, body)]).
    Unterminated heredocs stay inline."""
    lines = cmd.split("\n")
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
            docs.append((line, m.start(), m.end(), "\n".join(lines[i:j])))
            i = j + 1
    return "\n".join(kept), docs


def scan_shell(text):
    """(pipelines of stage strings, contents of every closed OUTERMOST $( ),
    backtick and ( ) group, top-level comments)."""
    pipelines, stages, cur, subs, comments, stack = [], [], [], [], [], []
    i, n = 0, len(text)

    def close_sub(end):
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
            j = n if j < 0 else j
            comments.append(text[i:j])
            i = j
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
    return pipelines, subs, comments


def split_words_linear(text):
    """shlex.split(text, posix=True) in linear time (shlex is quadratic on a
    huge word, which a long commit message is)."""
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
        # Unbalanced quotes (a heredoc opener inside "$( ): keep the words.
        return text.replace('"', " ").replace("'", " ").split()


def strip_prefixes(w):
    i, n = 0, len(w)
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
    return w[i:]


def resolve_target(path, assigns):
    def sub(m):
        return assigns.get(m.group(1) or m.group(2), m.group(0))
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", sub, path)


def is_code_target(path, assigns, body):
    p = resolve_target(path, assigns)
    ext = os.path.splitext(p)[1].lower()
    if ext in CODE_EXT:
        return True
    if not ext:
        return (body or "").lstrip().startswith("#!")
    return False


# ---------------------------------------------------------------------------
# what runs and what is prose
# ---------------------------------------------------------------------------

def classify(raw, assigns, body=None):
    """('prose',) | ('exec',) | ('feed',) code read from stdin |
    ('shell',) commands read from stdin | ('recurse', cmd) | ('skip',)."""
    if raw.lstrip().startswith("("):
        return ("skip",)  # a ( ) group: its contents are analysed as a sub
    w = strip_prefixes(words_of(raw))
    if not w:
        return ("exec",)  # assignments only: M=editMessageText
    head = os.path.basename(w[0])
    args = w[1:]
    if head in SHELLS:
        for k, t in enumerate(args):
            if t == "-c" or (re.fullmatch(r"-[a-zA-Z]{2,}", t) and "c" in t[1:]):
                rest = [x for x in args[k + 1:] if not x.startswith("-")]
                return ("recurse", rest[0] if rest else "")
        pos = next((a for a in args if a == "-" or not a.startswith("-")), None)
        return ("shell",) if pos in (None, "-") else ("exec",)
    if head == "eval":
        return ("recurse", " ".join(args))
    if head in INTERPRETERS or PY_RE.match(head):
        if any(a in INLINE_FLAGS or a.startswith(("--eval=", "--print=")) for a in args):
            return ("exec",)
        pos = next((a for a in args if a == "-" or not a.startswith("-")), None)
        return ("feed",) if pos in (None, "-") else ("exec",)
    if head == "find":
        return ("exec",) if any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in args) else ("prose",)
    if head in WRITERS:
        targets = [m.group(1) or m.group(2) or m.group(3) for m in REDIRECT_RE.finditer(raw)]
        if head == "tee":
            targets += [a for a in args if not a.startswith("-")]
        if any(is_code_target(t, assigns, body) for t in targets):
            return ("exec",)
        return ("prose",)
    if head in PROSE_HEADS:
        return ("prose",)
    return ("exec",)  # unknown head (curl, ssh, a function, a loop): fail closed


def heredoc_sink(line, ms, me, body, assigns):
    """'exec' | 'shell' | 'prose' for the heredoc whose marker is line[ms:me]."""
    before, after = line[:ms], line[me:]
    head_part = re.split(r"\$\(|[;&|(`]", before)[-1]
    tail_chunk = re.split(r"[;&)`]", after)[0]
    stages = [s for s in tail_chunk.split("|")]
    first = (head_part + " " + (stages[0] if stages else "")).strip()
    k0 = classify(first, assigns, body)[0] if first else "prose"
    later = [classify(s, assigns, body)[0] for s in stages[1:] if s.strip()]
    if k0 == "shell" or (k0 == "prose" and "shell" in later):
        return "shell"
    if k0 in ("exec", "feed", "recurse"):
        return "exec"
    if k0 == "prose" and any(k in ("exec", "feed") for k in later):
        return "exec"
    return "prose"


def exec_texts(cmd, assigns=None, depth=0):
    """Every piece of cmd's text that will run (or be written as a script)."""
    if depth > MAX_DEPTH:
        return [cmd]  # absurd nesting: fail closed
    if assigns is None:
        assigns = {}
    for m in ASSIGN_RE.finditer(cmd):
        assigns.setdefault(m.group(1), m.group(2).strip("'\""))
    skeleton, docs = split_heredocs(cmd)
    out = []
    for line, ms, me, body in docs:
        sink = heredoc_sink(line, ms, me, body, assigns)
        if sink == "exec":
            out.append(body)
        elif sink == "shell":
            out += exec_texts(body, assigns, depth + 1)
    pipelines, subs, _ = scan_shell(skeleton)
    for sub in subs:
        out += exec_texts(sub, assigns, depth + 1)
    for pipeline in pipelines:
        kinds = [classify(stage, assigns) for stage in pipeline]
        for k, (stage, kind) in enumerate(zip(pipeline, kinds)):
            tag = kind[0]
            if tag == "recurse":
                out += exec_texts(kind[1], assigns, depth + 1)
            elif tag in ("exec", "feed", "shell"):
                out.append(stage)
            elif tag == "prose" and any(x[0] in ("feed", "shell") for x in kinds[k + 1:]):
                out.append(stage)  # echo '...' | node, cat x | bash
    return out


def blank_free_text(s):
    """Blank the value of every text / caption field: free text, not a method."""
    out, i, n = [], 0, len(s)
    while True:
        m = FREE_KEY_RE.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.end()])
        j = m.end()
        pre, kq = m.group(1), m.group(2)
        if j < n and s[j] in "'\"`":
            q, k = s[j], j + 1
            while k < n and s[k] != q:
                k += 2 if s[k] == "\\" else 1
            end = min(k + 1, n)
        elif pre and not kq:
            # "text=free words": the value runs to the shell word's close quote
            k = j
            while k < n and s[k] != pre:
                k += 2 if s[k] == "\\" else 1
            end = min(k, n)
        else:
            k = j
            while k < n and not s[k].isspace() and s[k] not in ",;&|)}":
                k += 1
            end = k
        out.append(" ")
        i = end
    return "".join(out)


_EXEC_CACHE = {}


def executed(cmd):
    """exec_texts(cmd), computed once per command for both checks."""
    if cmd not in _EXEC_CACHE:
        _EXEC_CACHE.clear()
        _EXEC_CACHE[cmd] = exec_texts(cmd)
    return _EXEC_CACHE[cmd]


def find_edit(cmd):
    """(method, signal) when cmd's executed text calls a Bot API edit method."""
    if not RAW_TRIGGER_RE.search(cmd) or not TG_RE.search(cmd):
        return None
    method = signal = None
    for text in executed(cmd):
        # \"text\": \"...\" inside a double-quoted shell word (the telegram
        # skill's JSON send) is a text field too: unescape before blanking.
        t = blank_free_text(text.replace('\\"', '"'))
        method = method or (EDIT_RE.search(t) and EDIT_RE.search(t).group(0))
        signal = signal or (TG_RE.search(t) and TG_RE.search(t).group(0))
        if method and signal:
            return method, signal
    return None


def form_kind(m):
    """None when the matched -F field sends its text verbatim, else why not."""
    q, val = m.group("q"), m.group("val")
    if val.startswith("<"):
        # "caption=<f" reads the file; a bare caption=<f is a shell redirect
        return None if q.strip("$") else "redirect"
    if val.startswith("\\<") or (val[:1] in "'\"" and val[1:2] == "<"):
        return None  # caption=\<f, caption="<f"
    if val.startswith("@"):
        return "file"
    return "semicolon"


def find_form_fields(cmd):
    """[(kind, excerpt)] for every curl -F / --form on a free-text field in
    cmd's executed text, when that text also calls the Bot API."""
    if not RAW_FORM_TRIGGER_RE.search(cmd) or not TG_RE.search(cmd):
        return []
    texts = [t.replace('\\"', '"') for t in executed(cmd)]
    # Both command-wide, not per text: send() { curl ... "$@"; } puts curl in
    # one stage and send -F "caption=..." in another.
    if not any(TG_RE.search(t) for t in texts) or not any(CURL_RE.search(t) for t in texts):
        return []
    hits = []
    for text in texts:
        for m in FORM_FIELD_RE.finditer(text):
            kind = form_kind(m)
            if kind:
                # redact the whole line first: a cut could leave half a token
                line = TOKEN_LITERAL_RE.sub("<token>", text[m.start():].split("\n")[0])
                hits.append((kind, line[:m.end() - m.start() + 48]))
    return hits


def has_reason_comment(cmd):
    skeleton, _ = split_heredocs(cmd)
    _, _, comments = scan_shell(skeleton)
    for c in comments:
        words = re.findall(r"[A-Za-z0-9']+", c.lstrip("#"))
        if len(words) >= 2 and sum(len(x) for x in words) >= 8:
            return True
    return False


# ---------------------------------------------------------------------------
# message
# ---------------------------------------------------------------------------

BODY = """Telegram has no read-by-id method, so an edit is never a safe way to check
that a message exists. The same content answers "message is not modified";
DIFFERENT content (text, caption, media or buttons) replaces what Zalo sees,
and there is no undo. M overwrote message 21104 this way and had to restore
it, and on 2026-10-02 worker bg64 (editMessageCaption on 21231) and the bg72
qa-agent verifier (editMessageReplyMarkup on 21318 to 21322) did it again.

The proof a send landed is the send response itself: "ok":true plus
result.message_id. Save it when you send (curl ... -o send.json, then
jq '{ok, id: .result.message_id}' send.json) and cite it. A verifier cites
the worker's saved response or message_id; it never probes the chat.
Never edit a message to test that it exists.

A deliberate edit of a message YOU sent in this run (a typo in your own
caption, a preview you are replacing) is allowed: start the command with
TG_EDIT_OK=1 and give the reason in a shell comment:

  TG_EDIT_OK=1 curl -sS "https://api.telegram.org/bot$TOK/editMessageCaption" -F chat_id="$CID" -F message_id=21400 -F "caption=<cap.txt"  # fixing the typo in my own caption, sent earlier in this run

Not checked: searches (grep, rg, git, gh), prose (echo or cat with no pipe
into an interpreter, a heredoc into a .md file) and the text or caption
value of a send. If this command only MENTIONS an edit method, move the
mention into one of those (a bg.mjs brief: write it to a file, pass --file).
There is no other override; do not reword the call to get past this guard."""


def block_message(method, signal, override_without_reason):
    head = f"BLOCKED (telegram-edit-guard): a Telegram Bot API edit call ({method}, with {signal})."
    lines = [head, ""]
    if override_without_reason:
        lines += [
            "TG_EDIT_OK=1 is set, but the command has no comment giving the reason.",
            "Add one: which message, why it needs the edit, and that you sent it in this run.",
            "",
        ]
    return "\n".join(lines) + "\n" + BODY + "\n"


FORM_BODY = """curl -F reads a ";" inside a value as the start of a field parameter
(;type=, ;filename=) and silently drops everything after it: curl exits 0,
Telegram answers "ok":true, and the message arrives cut. On 2026-10-02
message 21478 arrived ending "(web live" and Zalo never saw "probe passed,
cleaned up". Every -F or --form on caption, text, question or explanation is
blocked, with or without a ";" today, because the next text may have one.

Send the text verbatim one of two ways (both replayed against a local
capture server, curl 8.7.1, bash and zsh: ";" and "$" arrive intact):

  --form-string 'caption=PR #166 merged (web live; probe passed), $5 saved'
  -F "caption=<cap.txt"    (the file's content, verbatim; keep the quotes)

Single-quote a --form-string value or take it from a file
(--form-string "caption=$(cat cap.txt)" works too): inside double quotes the
shell turns $5 into nothing before curl runs. An UNQUOTED -F caption=<cap.txt
is a shell redirect and sends an empty caption, and -F "caption=@cap.txt"
uploads a file part instead of text.

File and other fields stay on -F: photo=@, document=@, video=@, media=,
chat_id=, parse_mode=, reply_markup=. After the send, compare result.caption
(or result.text) in the response with what you meant to send. There is no
override (TG_EDIT_OK=1 does not cover this check): the two forms above are
the fix."""

FORM_WHY = {
    "redirect": "Unquoted, that < is a shell redirect: curl gets the field with nothing in it.",
    "file": "That @ uploads a file part, not text.",
    "semicolon": None,
}


def form_block_message(hits):
    lines = ["BLOCKED (telegram-edit-guard): curl -F / --form on a Telegram text field.", ""]
    for kind, excerpt in hits[:5]:
        lines.append(f"  {excerpt}")
        if FORM_WHY[kind]:
            lines.append(f"    {FORM_WHY[kind]}")
    return "\n".join(lines) + "\n\n" + FORM_BODY + "\n"


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def decide(payload):
    """(exit_code, stderr)."""
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0, ""
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        return 0, ""
    cmd = ti.get("command")
    if not isinstance(cmd, str):
        return 0, ""
    parts = []
    hit = find_edit(cmd)
    if hit:
        override = bool(OVERRIDE_RE.match(cmd))
        if not (override and has_reason_comment(cmd)):
            parts.append(block_message(hit[0], hit[1], override))
    forms = find_form_fields(cmd)
    if forms:
        parts.append(form_block_message(forms))
    if not parts:
        return 0, ""
    return 2, "\n".join(parts)


def main():
    raw = sys.stdin.read()
    if not raw.strip() or not (RAW_TRIGGER_RE.search(raw) or RAW_FORM_TRIGGER_RE.search(raw)):
        return 0
    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    code, err = decide(payload)
    if err:
        sys.stderr.write(err)
        sys.stderr.flush()
    return code


if __name__ == "__main__":
    # Fail-open contract: this runs before every Bash call. Any error exits
    # 0; only a deliberate block exits 2.
    try:
        rc = main()
    except BaseException:
        rc = 0
    sys.exit(2 if rc == 2 else 0)
