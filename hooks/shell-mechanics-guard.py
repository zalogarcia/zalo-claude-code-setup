#!/usr/bin/env python3
"""PreToolUse (Bash): shell mechanics that fail or destroy evidence in this
setup. Two tiers: a WARN class (once per class per session) and a BLOCK class
(exit 2, every time).

Why the WARN class exists (14-day audit 2026-08-28, P8; ~30 instances)
---------------------------------------------------------------------
Both shapes are already QUIRKS.md lines 1 and 3, front-loaded into every
session by session-start.sh. They were read at minute 0 and violated at minute
40 anyway: front-loading does not survive session momentum, only
point-of-use enforcement does.

A) LOST EXIT CODE: `$?` read after piping into a pager/filter (`| tail`,
   `| head`, `| grep`). `$?` is the FILTER's status; `tail` succeeds even when
   the build it is summarising failed. Each miss forced a full multi-minute
   gate re-run. (`${PIPESTATUS[0]}` used to be warned here too; it is now in
   the BLOCK class, see 4 below.)

B) RELATIVE cd / relative paths (~22 events). The Bash tool resets cwd between
   calls, so `cd src && npm test` runs from wherever the harness put you, not
   from where the previous call ended.

The warn tier exits 0 ALWAYS and injects a one-time-per-class-per-session nudge
carrying the canonical replacement: too many legitimate shapes exist to block.

Why the BLOCK class exists (60-day audit 2026-09-27, P4; 54 instances in 45 of
80 sampled sessions)
---------------------------------------------------------------------------
The Bash tool runs every command through `eval` in zsh (EQUALS and NOMATCH on,
SH_WORD_SPLIT off) on a BSD (macOS) userland. These shapes are bash or GNU
habits that fail EVERY time in that shell, so letting them run only buys a
wasted round trip (or, for PIPESTATUS, an invented exit code):

  1. equals:     an unquoted word starting with `==` (or `=~`, `=-`...):
                 zsh `=cmd` expansion fails with `(eval):1: == not found`.
                 `echo ===`, `[ "$a" == "$b" ]`.
  2. timeout:    `timeout` / `gtimeout` as a command word: neither exists here.
  3. glob_opt:   an unquoted `*` / `?` inside `--option=value`: zsh globs the
                 whole word and aborts with `no matches found`.
  4. pipestatus: `$PIPESTATUS` / `${PIPESTATUS[..]}` in text zsh expands: it is
                 bash only, so it is ALWAYS empty (zsh has `$pipestatus`).
  5. for_scalar: `for x in $VAR` where this command assigned VAR a multi-word
                 scalar: zsh does not word-split, the loop runs once.

Not blocked, on purpose: GNU sed `N,+M` addresses. The audit listed them, but
/usr/bin/sed on macOS 26 accepts `sed -n '10,+5p'` (probed 2026-09-27; ~550
of 582 such commands in the 60-day corpus succeeded; the failures came from an
empty or multi-line `$(grep -n .. | cut -d: -f1)` start address, which no
static check can see).

The detector is a small zsh-aware lexer: single quotes, `$'..'`, double quotes
(for the quote-sensitive shapes), backslash escapes, heredoc bodies (`<<EOF`,
`<<'EOF'`, `<<"EOF"`, `<<-EOF`), comments, `$(..)`, backticks, `$((..))`,
`((..))`, `[[ .. ]]` and case patterns. It never blocks on anything it cannot
parse (fail open), costs no subprocess, and a cheap precompiled prefilter
skips the lexer for almost every command.

Tests: python3 ~/.claude/hooks/shell-mechanics-guard.test.py
Replay: the pure function `find_blocks(command)` is what the replay harness
imports (it never raises; [] means allow).
"""

import json
import os
import re
import sys
import tempfile

STATE_DIR = os.environ.get("SHELL_MECH_STATE_DIR") or os.path.join(
    tempfile.gettempdir(), "claude-shell-mech-%d" % os.getuid()
)

# Filters that swallow the status of what feeds them.
FILTERS = (
    "tail", "head", "grep", "egrep", "rg", "sed", "awk", "less", "more",
    "jq", "tee", "wc", "sort", "uniq", "cut", "column", "tr", "cat",
)
_FILTER_RE = re.compile(r"\|\s*(?:[\w./-]*/)?(%s)\b" % "|".join(FILTERS))
_DOLLAR_Q_RE = re.compile(r"\$\?")
_LEADING_CD_RE = re.compile(r"^\s*cd\s+(?!-\s*$)([^\s;&|]+)")

EXIT_MSG = (
    "⚠ shell-mechanics-guard (warn only, once per session): this command reads "
    "an exit status that will not be the one you want.\n"
    "  • `$?` after `| tail` / `| head` / `| grep` is the FILTER's status: "
    "`tail` exits 0 for a build that failed.\n"
    "  • `${PIPESTATUS[...]}` is bash only and always empty under zsh (this "
    "hook blocks it); zsh's form is `${pipestatus[1]}`.\n"
    "Canonical shape that survives both (QUIRKS.md line 1):\n"
    "    <cmd> > /tmp/out.log 2>&1; echo EXIT=$?; tail -40 /tmp/out.log\n"
    "Run the command, capture EXIT immediately, THEN look at the log. "
    "(8 gate re-runs in the last 14 days were caused by this.)"
)

CD_MSG = (
    "⚠ shell-mechanics-guard (warn only, once per session): this command starts "
    "with a RELATIVE `cd`. The Bash tool resets the working directory between "
    "calls, so it does not start where your previous call ended; the same "
    "relative path resolved to a different repo ~22 times in the last 14 days "
    "(one of them made sql-guard reject real tables by loading the wrong "
    "repo's schema snapshot).\n"
    "Use an absolute path: `cd /Users/zalo/dev/<repo> && ...`, or pass the "
    "path to the tool directly (`git -C /abs/path status`, `npm --prefix "
    "/abs/path test`)."
)


def _strip_quoted(command):
    """Neutralise string literals so a `|` or `$?` inside one is not read as
    shell mechanics, while preserving what the shell would really expand.

    Single quotes suppress expansion entirely, so they are blanked whole.
    Double quotes DO expand `$?`, so only the structural characters inside
    them are blanked.
    """

    def _sub(m):
        span = m.group(0)
        if span.startswith("'"):
            return " " * len(span)
        return re.sub(r"[|;&\n]", " ", span)

    return re.sub(r"'[^']*'|\"[^\"]*\"", _sub, command)


def classify(command):
    """Set of WARN classes this command earns. Conservative by design:
    anything ambiguous returns nothing. (PIPESTATUS is a BLOCK now, see
    find_blocks, so it is deliberately not a warn trigger any more.)"""
    hits = set()
    if not command or not command.strip():
        return hits
    bare = _strip_quoted(command)
    low = bare.lower()

    # `set -o pipefail` / `set -eo pipefail` makes $?-after-pipe meaningful.
    pipefail = "pipefail" in low

    if not pipefail:
        for q in _DOLLAR_Q_RE.finditer(bare):
            before = bare[: q.start()]
            # $? must belong to a LATER statement than the pipeline, otherwise
            # it is just the (correct) status of a non-piped command.
            sep = max(before.rfind(";"), before.rfind("&&"), before.rfind("\n"))
            if sep == -1:
                continue
            if _FILTER_RE.search(before[:sep]):
                hits.add("exit")
                break

    cd = _LEADING_CD_RE.match(command)
    if cd:
        target = cd.group(1).strip("'\"")
        if target and target[0] not in "/~$" and not target.startswith("%("):
            hits.add("cd")

    return hits


# ---------------------------------------------------------------------------
# BLOCK class: a zsh-aware lexer and five shape checks.
# ---------------------------------------------------------------------------

_Q = "\x00"  # a quoted or escaped literal character in Word.plain
_X = "\x01"  # one expansion ($v, ${..}, $(..), `..`, $((..))) in plain/val

# Cheap gate: the lexer only runs when one of these substrings is present.
_PREFILTER = re.compile(
    r"==|(?:^|[\s;&|(`{])=[^\s(]|timeout|--[\w.-]+=\S*[*?]|PIPESTATUS"
    r"|\bfor\s+[A-Za-z_]\w*\s+in\b[^;\n]*\$"
)
_NAME_RE = re.compile(r"[A-Za-z_]\w*")
_BRACE_NAME_RE = re.compile(r"(?:\([^)]*\))?[#!^=~+]*([A-Za-z_]\w*)")
_ASSIGN_RE = re.compile(r"([A-Za-z_]\w*)(?:\[[^\]]*\])?(\+?)=")
_ARRAY_HEAD_RE = re.compile(r"[A-Za-z_]\w*(?:\[[^\]]*\])?\+?=\Z")
_GLOB_OPT_RE = re.compile(r"(--[A-Za-z0-9][\w.-]*)=(.*)\Z", re.S)
_PARAM_WORD_RE = re.compile(r"\$(?:([A-Za-z_]\w*)|\{([A-Za-z_]\w*)\})\Z")
_TIMEOUT_DEF_RE = re.compile(
    r"(?:^|[\s;&|({])(?:function\s+g?timeout\b|g?timeout\s*\(\s*\))|\balias\s+g?timeout="
)
# the command checks for timeout itself, or already carries the perl fallback
_TIMEOUT_GUARDED_RE = re.compile(
    r"\b(?:command\s+-[vV]|which|type|hash|whence)\s+(?:-\w+\s+)*g?timeout\b"
    r"|\bperl\s+(?:-\w+\s+)*-e\s*['\"][^'\"]*\balarm\b"
)
# a command substitution that yields one line, so `for x in $VAR` loops once
# over the right thing: `$(... | head -1)`, `$(... | wc -l)`
_ONE_LINE_SUBST_RE = re.compile(
    r"\|\s*(?:(?:head|tail)\s+-(?:n\s*)?1|wc\s+-[lcwm])\s*\)\s*\"?\Z"
)
# a command substitution whose whole output is one word by construction
# (QA 2026-09-27 replay: `START=$(date +%s)`, `SHA=$(git rev-parse HEAD)`,
# `IPH=$(cat /tmp/verify-sim-iphone.id)` were blocked and would have worked)
_ONE_WORD_SUBST_RE = re.compile(
    r"\$\(\s*(?:date|pwd|basename|dirname|mktemp|uuidgen|whoami|hostname|uname"
    r"|id\s+-[ug]|git\s+rev-parse|git\s+branch\s+--show-current|git\s+rev-list\s+--count"
    r"|cat\s+[^\s|;&()`]+\.(?:id|pid|sha))(?![\w.-])[^|;&()`]*\)\s*\"?\Z"
)
# The option lists are bounded ({0,300}): an unbounded lazy span re-scanned the
# rest of the line from every `setopt`, and 20,000 of them took 63 s (QA
# 2026-09-27). No real setopt line is longer.
_NOMATCH_OFF_RE = re.compile(
    r"\b(?:setopt\s+[^;\n&|]{0,300}?\b(?:no_?nomatch|null_?glob|csh_?null_?glob)\b"
    r"|unsetopt\s+[^;\n&|]*?\bno_?match\b"
    r"|set\s+\+o\s+no_?match\b"
    r"|emulate\s+(?:-\w+\s+)*(?:sh|ksh|bash)\b)",
    re.I,
)
_WORDSPLIT_ON_RE = re.compile(
    r"\b(?:setopt\s+[^;\n&|]{0,300}?\bsh_?word_?split\b|set\s+-o\s+sh_?word_?split\b"
    r"|emulate\s+(?:-\w+\s+)*(?:sh|ksh|bash)\b)",
    re.I,
)

_SEPARATORS = frozenset(
    ["\n", ";", "&&", "||", "|", "|&", "&", "&!", "&|", ";;", ";&", ";|", "(", ")", "(("]
)
_REDIRECTS = frozenset(
    ["<", ">", ">>", ">|", ">!", ">&", "<&", "<>", "&>", "&>>", "<<<", ">>|", "&>|"]
)
_OPS3 = ("&>>", "<<<", "<<-", ">>|", "&>|")
_OPS2 = ("&&", "||", "|&", ";;", ";&", ";|", "&!", "&|", "&>", ">>", ">|", ">!",
         ">&", "<&", "<>", "<<")
_PREFIX_KEYWORDS = frozenset(
    ["!", "{", "}", "if", "then", "else", "elif", "do", "done", "fi", "while",
     "until", "time", "noglob", "nocorrect", "coproc", "esac"]
)
_WRAPPERS = frozenset(
    ["exec", "command", "builtin", "nohup", "sudo", "env", "xargs", "nice", "caffeinate"]
)
_DECLARERS = frozenset(["export", "local", "typeset", "declare", "readonly", "integer", "float"])
_WORD_END = frozenset(" \t\r\n;&|)")
_BLANKS_RE = re.compile(r"[ \t\r]+")
_WORD_RUN_RE = re.compile(r"[^\s;&|()<>\\'\"$`]+")
_DQ_RUN_RE = re.compile(r'[^"\\$`]+')
_FUNC_HDR_RE = re.compile(r"[\w.:+@-]+\(\)\Z")


def _keeps_cmd_pos(p):
    """A word after which the next word is still at command position:
    `if`, `then`, `{`, `!`, ..., or a function header `name()`."""
    return p in _PREFIX_KEYWORDS or _FUNC_HDR_RE.match(p) is not None


class _Unterminated(Exception):
    """Unbalanced quote/substitution: the shell would not run it as written."""


class _Word(object):
    __slots__ = ("raw", "plain", "val", "subst", "array", "in_dbr")

    def __init__(self):
        self.raw = self.plain = self.val = ""
        self.subst = self.array = self.in_dbr = False


class _Lexer(object):
    """Linear zsh-ish lexer. Produces one token list per command context (the
    top level, each $(..), `..`, <(..), =(..)); tokens are _Word objects or
    operator strings. Heredoc bodies and comments produce nothing."""

    def __init__(self, s):
        self.s = s
        self.n = len(s)
        self.i = 0
        self.lists = []
        self.pipestatus = None
        self.heredocs = []
        self.ctx = []  # closers of the open command contexts: ")" or "`"

    def run(self):
        self.lex_list(None)
        return self

    # -- command lists ------------------------------------------------------
    def lex_list(self, end):
        s, n = self.s, self.n
        toks = []
        self.lists.append(toks)
        self.ctx.append(end)
        depth = 0
        argpos = False  # a plain argument word was seen since the last separator
        redir = False  # the previous token was a redirection operator
        while True:
            i = self.i
            if i >= n:
                if end is not None:
                    raise _Unterminated()
                self.ctx.pop()
                return toks
            c = s[i]
            if c in " \t\r":
                self.i = _BLANKS_RE.match(s, i).end()
                continue
            if c == "\\" and i + 1 < n and s[i + 1] == "\n":
                self.i = i + 2
                continue
            if c == "\n":
                self.i = i + 1
                toks.append("\n")
                argpos = redir = False
                if self.heredocs:
                    self._read_heredocs()
                continue
            if c == "`" and end == "`":
                self.i = i + 1
                self.ctx.pop()
                return toks
            if c == "#":
                j = s.find("\n", i)
                self.i = n if j < 0 else j
                continue
            if c == ")":
                self.i = i + 1
                argpos = redir = False
                if depth > 0:
                    depth -= 1
                    toks.append(")")
                    continue
                if end == ")":
                    self.ctx.pop()
                    return toks
                toks.append(")")  # unmatched: the end of a case pattern
                continue
            if c == "(":
                if argpos:
                    # after an argument zsh reads `( .. )` as ONE pattern word,
                    # spaces included: `grep -n x (a === b)` globs it
                    j = self._skip_parens(i + 1, 1)
                    w = _Word()
                    w.raw = w.plain = w.val = s[i:j]
                    self.i = j
                    toks.append(w)
                    continue
                if s.startswith("((", i):
                    self.i = self._skip_parens(i + 2, 2)
                    toks.append("((")
                    continue
                self.i = i + 1
                depth += 1
                toks.append("(")
                continue
            if c in ";&|<>":
                if c in "<>" and i + 1 < n and s[i + 1] == "(":
                    toks.append(self._word())
                    continue
                op = self._op(i)
                self.i = i + len(op)
                if op == "<<" or op == "<<-":
                    self._heredoc_start(op == "<<-")
                    continue
                toks.append(op)
                if op in _REDIRECTS:
                    redir = True
                else:
                    argpos = redir = False
                continue
            w = self._word()
            if w is None:
                continue
            # an fd number glued to a redirection (`2>&1`) is not an argument
            if self.i < n and s[self.i] in "<>" and w.raw.isdigit():
                continue
            toks.append(w)
            if redir:
                redir = False
            elif not argpos and not _keeps_cmd_pos(w.plain):
                argpos = True

    def _op(self, i):
        s = self.s
        for op in _OPS3:
            if s.startswith(op, i):
                return op
        for op in _OPS2:
            if s.startswith(op, i):
                return op
        return s[i]

    # -- heredocs -----------------------------------------------------------
    def _heredoc_start(self, strip_tabs):
        s, n = self.s, self.n
        while self.i < n and s[self.i] in " \t":
            self.i += 1
        if self.i >= n or s[self.i] in "\n;&|()<>":
            return
        w = self._word()
        if w is not None:
            self.heredocs.append((w.val, strip_tabs))

    def _read_heredocs(self):
        s, n = self.s, self.n
        i = self.i
        for delim, strip_tabs in self.heredocs:
            while i < n:
                j = s.find("\n", i)
                line = s[i:] if j < 0 else s[i:j]
                i = n if j < 0 else j + 1
                if (line.lstrip("\t") if strip_tabs else line) == delim:
                    break
        self.i = i
        self.heredocs = []

    # -- skipping helpers ---------------------------------------------------
    def _skip_sq(self, k):
        e = self.s.find("'", k)
        if e < 0:
            raise _Unterminated()
        return e + 1

    def _skip_dq(self, k):
        s, n = self.s, self.n
        while k < n:
            c = s[k]
            if c == "\\":
                k += 2
                continue
            if c == '"':
                return k + 1
            k += 1
        raise _Unterminated()

    def _skip_parens(self, k, depth):
        """k is just past `depth` opening parens; returns the index after the
        parens that close them. Quote aware."""
        s, n = self.s, self.n
        while k < n:
            c = s[k]
            if c == "\\":
                k += 2
                continue
            if c == "'":
                k = self._skip_sq(k + 1)
                continue
            if c == '"':
                k = self._skip_dq(k + 1)
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return k + 1
            k += 1
        raise _Unterminated()

    def _skip_braces(self, k):
        s, n = self.s, self.n
        depth = 1
        while k < n:
            c = s[k]
            if c == "\\":
                k += 2
                continue
            if c == "'":
                k = self._skip_sq(k + 1)
                continue
            if c == '"':
                k = self._skip_dq(k + 1)
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return k + 1
            k += 1
        raise _Unterminated()

    # -- words --------------------------------------------------------------
    def _word(self):
        s, n = self.s, self.n
        start = i = self.i
        plain = []
        val = []
        w = _Word()
        # process substitution at the start of a word: <(..) >(..) =(..)
        if i + 1 < n and s[i] in "<>=" and s[i + 1] == "(":
            self.i = i + 2
            self.lex_list(")")
            i = self.i
            plain.append(_X)
            val.append(_X)
            w.subst = True
        while i < n:
            c = s[i]
            if c in _WORD_END or c in "<>":
                break
            if c == "(":
                head = s[start:i]
                if i == start:
                    break
                if _ARRAY_HEAD_RE.match(head):
                    i = self._skip_parens(i + 1, 1)
                    w.array = True
                    plain.append(_X)
                    val.append(_X)
                    continue
                j = self._skip_parens(i + 1, 1)  # zsh glob group / qualifier
                plain.append(s[i:j])
                val.append(s[i:j])
                i = j
                continue
            if c == "\\":
                if i + 1 < n:
                    if s[i + 1] == "\n":
                        i += 2
                        continue
                    plain.append(_Q)
                    val.append(s[i + 1])
                    i += 2
                    continue
                plain.append(c)
                val.append(c)
                i += 1
                continue
            if c == "'":
                j = self._skip_sq(i + 1)
                content = s[i + 1:j - 1]
                plain.append(_Q * len(content))
                val.append(content)
                i = j
                continue
            if c == '"':
                i = self._dquote(i + 1, plain, val, w)
                continue
            if c == "$":
                i = self._dollar(i, plain, val, w, False)
                continue
            if c == "`":
                if self.ctx[-1] == "`":
                    break  # closes the enclosing `..`
                self.i = i + 1
                self.lex_list("`")
                i = self.i
                plain.append(_X)
                val.append(_X)
                w.subst = True
                continue
            m = _WORD_RUN_RE.match(s, i)
            if m:
                plain.append(m.group(0))
                val.append(m.group(0))
                i = m.end()
                continue
            plain.append(c)
            val.append(c)
            i += 1
        if i == start:
            self.i = i + 1  # never loop on a character nothing consumes
            return None
        self.i = i
        w.raw = s[start:i]
        w.plain = "".join(plain)
        w.val = "".join(val)
        return w

    def _dquote(self, i, plain, val, w):
        s, n = self.s, self.n
        while i < n:
            c = s[i]
            if c == '"':
                return i + 1
            if c == "\\" and i + 1 < n:
                nxt = s[i + 1]
                if nxt == "\n":
                    i += 2
                    continue
                if nxt in '$`"\\':
                    plain.append(_Q)
                    val.append(nxt)
                else:
                    plain.append(_Q + _Q)
                    val.append(c + nxt)
                i += 2
                continue
            if c == "$":
                i = self._dollar(i, plain, val, w, True)
                continue
            if c == "`":
                if self.ctx[-1] == "`":
                    raise _Unterminated()  # nested unescaped backticks: give up
                self.i = i + 1
                self.lex_list("`")
                i = self.i
                plain.append(_X)
                val.append(_X)
                w.subst = True
                continue
            m = _DQ_RUN_RE.match(s, i)
            if m:
                run = m.group(0)
                plain.append(_Q * len(run))
                val.append(run)
                i = m.end()
                continue
            plain.append(_Q)
            val.append(c)
            i += 1
        raise _Unterminated()

    def _dollar(self, i, plain, val, w, dq):
        s, n = self.s, self.n
        j = i + 1
        c = s[j] if j < n else ""
        if c == "(":
            if s.startswith("((", j):
                k = self._skip_parens(j + 2, 2)
            else:
                self.i = j + 1
                self.lex_list(")")
                k = self.i
                w.subst = True
            plain.append(_X)
            val.append(_X)
            return k
        if c == "{":
            k = self._skip_braces(j + 1)
            m = _BRACE_NAME_RE.match(s, j + 1)
            if (m and m.group(1) == "PIPESTATUS" and self.pipestatus is None
                    and "pipestatus" not in s[i:k]):  # `${PIPESTATUS[0]:-${pipestatus[1]}}` works
                self.pipestatus = s[i:k]
            plain.append(_X)
            val.append(_X)
            return k
        if c == "'" and not dq:  # $'..' (ANSI C quoting): never expands
            k = j + 1
            while k < n and s[k] != "'":
                k += 2 if s[k] == "\\" else 1
            if k >= n:
                raise _Unterminated()
            content = s[j + 1:k]
            plain.append(_Q * len(content))
            val.append(content)
            return k + 1
        if c == '"' and not dq:  # $".." behaves like ".."
            return self._dquote(j + 1, plain, val, w)
        m = _NAME_RE.match(s, j) if c else None
        if m:
            if m.group(0) == "PIPESTATUS" and self.pipestatus is None:
                self.pipestatus = s[i:m.end()]
            plain.append(_X)
            val.append(_X)
            return m.end()
        if c and c in "?#*@$!-0123456789":
            plain.append(_X)
            val.append(_X)
            return j + 1
        plain.append(_Q if dq else "$")
        val.append("$")
        return j


def _segments(toks):
    """Split one token list into simple commands: [(words, is_case_pattern)].
    Redirect targets are dropped; words inside [[ ]] are flagged in_dbr."""
    segs = []
    cur = []
    depth = 0
    dbr = False
    target = False
    for t in toks:
        if t.__class__ is _Word:
            if target:
                target = False
                continue
            p = t.plain
            if dbr:
                t.in_dbr = True
                if p == "]]":
                    dbr = False
            elif p == "[[" and all(_keeps_cmd_pos(x.plain) for x in cur):
                dbr = True
                t.in_dbr = True
            cur.append(t)
            continue
        if dbr:
            continue  # `&&`, `<`, `(` inside [[ ]] are test syntax
        if t in _REDIRECTS:
            target = True
            continue
        pattern = t == ")" and depth == 0
        if cur:
            segs.append((cur, pattern))
            cur = []
        if t == "(":
            depth += 1
        elif t == ")" and depth > 0:
            depth -= 1
        target = False
    if cur:
        segs.append((cur, False))
    return segs


def _head(words):
    """-> (prefix assignment words, command-position words, noglob, index of
    the first command word). Behind a wrapper (`xargs -n1 timeout ..`) the
    wrapped command is at command position too."""
    i, n = 0, len(words)
    noglob = False
    assigns = []
    while i < n:
        p = words[i].plain
        if _keeps_cmd_pos(p):
            noglob = noglob or p == "noglob"
            i += 1
            continue
        if p == "function" and i + 1 < n:
            i += 2  # `function name [()] {`
            if i < n and words[i].plain == "()":
                i += 1
            continue
        if _ASSIGN_RE.match(p):
            assigns.append(words[i])
            i += 1
            continue
        break
    first = i
    cmds = []
    while i < n:
        w = words[i]
        cmds.append(w)
        if w.plain not in _WRAPPERS:
            break
        i += 1
        if w.plain == "command" and i < n and words[i].plain in ("-v", "-V"):
            break  # `command -v timeout` only asks whether it exists
        while i < n:
            q = words[i].plain
            if q.startswith("-") or q.isdigit() or q == "{}" or _ASSIGN_RE.match(q):
                i += 1
                continue
            if q in ("noglob", "nocorrect"):
                noglob = noglob or q == "noglob"
                i += 1
                continue
            break
    return assigns, cmds, noglob, first


def _equals_bad(p):
    """True for an unquoted word zsh will `=`-expand and fail on."""
    if len(p) < 2 or p[0] != "=":
        return False
    r = p[1]
    if r == "=":
        return True
    # `=name` / `=/path` / `=$var` may resolve to a real command: fail open.
    # `=[` is left literal by zsh (probed 2026-09-27).
    return not (r.isalnum() or r in "_./[" or r == _Q or r == _X)


def _installed(name):
    import shutil  # only on a timeout hit: keeps the every-call import cost flat

    if shutil.which(name):
        return True
    for d in ("/opt/homebrew/bin", "/usr/local/bin",
              "/opt/homebrew/opt/coreutils/libexec/gnubin",
              "/usr/local/opt/coreutils/libexec/gnubin"):
        if os.access(os.path.join(d, name), os.X_OK):
            return True
    return False


def _classify_value(word):
    """Kind of the value an assignment word gives its variable."""
    if word.array:
        return "array"
    m = _ASSIGN_RE.match(word.plain)
    if m.group(2):
        return "other"  # `+=`: appends, kind unknown
    value = word.val[m.end():]
    if word.subst:
        if _ONE_LINE_SUBST_RE.search(word.raw) or _ONE_WORD_SUBST_RE.search(word.raw):
            return "single"
        return "multi"
    if any(ch in value for ch in " \t\n"):
        return "multi"
    return "single"


def _analyse(command, lx):
    hits = {}
    timeout_defined = (_TIMEOUT_DEF_RE.search(command) is not None
                       or _TIMEOUT_GUARDED_RE.search(command) is not None)
    nomatch_off = _NOMATCH_OFF_RE.search(command) is not None
    wordsplit_on = _WORDSPLIT_ON_RE.search(command) is not None
    for toks in lx.lists:
        kinds = {}
        for words, pattern in _segments(toks):
            if pattern:
                continue
            assigns, cmds, noglob, first = _head(words)
            cmd = cmds[0].plain if cmds else ""

            # 1. equals: any word, plus the value of a real assignment
            if "equals" not in hits:
                for w in words:
                    if not w.in_dbr and _equals_bad(w.plain):
                        hits["equals"] = w.raw
                        break
                if "equals" not in hits:
                    decl = words[first + 1:] if cmd in _DECLARERS else []
                    for w in assigns + decl:
                        m = _ASSIGN_RE.match(w.plain)
                        if m and _equals_bad(w.plain[m.end():]):
                            hits["equals"] = w.raw[m.end():]
                            break

            # 2. timeout at command position
            if "timeout" not in hits and not timeout_defined:
                for w in cmds:
                    if w.plain in ("timeout", "gtimeout") and not _installed(w.plain):
                        hits["timeout"] = w.plain
                        break

            # 3. unquoted * or ? in --option=value
            if "glob_opt" not in hits and not noglob and not nomatch_off:
                for w in words:
                    if w.in_dbr:
                        continue
                    m = _GLOB_OPT_RE.match(w.plain)
                    if m and ("*" in m.group(2) or "?" in m.group(2)):
                        hits["glob_opt"] = w.raw
                        break

            # 5. for x in $SCALAR (bookkeeping of assignments in source order)
            if cmd == "" and first == len(words):
                for w in assigns:
                    kinds[_ASSIGN_RE.match(w.plain).group(1)] = _classify_value(w)
            elif cmd in _DECLARERS:
                flags = "".join(x.plain for x in words[first + 1:] if x.plain.startswith("-"))
                for w in words[first + 1:]:
                    m = _ASSIGN_RE.match(w.plain)
                    if m:
                        kinds[m.group(1)] = (
                            "array" if ("a" in flags or "A" in flags) else _classify_value(w)
                        )
                    elif _NAME_RE.fullmatch(w.plain):
                        kinds[w.plain] = "array" if ("a" in flags or "A" in flags) else "other"
            elif cmd == "read":
                for w in words[first + 1:]:
                    if _NAME_RE.fullmatch(w.plain):
                        kinds[w.plain] = "other"
            elif cmd == "for" and len(words) > first + 2 and words[first + 2].plain == "in":
                var = words[first + 1].plain
                items = [w for w in words[first + 3:] if w.plain != "do"]
                # Two or more items (`for S in $IPH $IPD`) is an enumeration of
                # one value per variable: the replay's only certain false
                # blocks had that shape (QA 2026-09-27).
                if "for_scalar" not in hits and not wordsplit_on and len(items) == 1:
                    for w in items:
                        m = _PARAM_WORD_RE.match(w.raw)
                        if not m:
                            continue
                        name = m.group(1) or m.group(2)
                        if kinds.get(name) == "multi":
                            hits["for_scalar"] = (var, name, w.raw)
                            break
                kinds[var] = "other"

    # 4. PIPESTATUS in text zsh expands (the lexer saw it outside '..',
    #    heredoc bodies, comments and backslash escapes)
    if lx.pipestatus is not None:
        hits["pipestatus"] = lx.pipestatus
    return hits


_ORDER = ("equals", "timeout", "glob_opt", "pipestatus", "for_scalar")


def find_blocks(command):
    """PURE. All BLOCK shapes in `command`, as [(shape, evidence)] in a fixed
    order. [] means allow. Never raises: any parse or internal error is an
    allow (fail open), because this runs before every Bash call."""
    try:
        if not isinstance(command, str) or not _PREFILTER.search(command):
            return []
        lx = _Lexer(command).run()
        hits = _analyse(command, lx)
        return [(k, hits[k]) for k in _ORDER if k in hits]
    except Exception:
        return []


def find_block(command):
    """PURE. The first BLOCK shape as (shape, evidence), or None."""
    hits = find_blocks(command)
    return hits[0] if hits else None


def _quote_rewrite(word):
    m = re.match(r"(--[\w.-]+=)(.*)\Z", word, re.S)
    if m and "'" not in m.group(2):
        return "%s'%s'" % (m.group(1), m.group(2))
    return "--include='*.tsx'"


def _shape_message(shape, ev):
    if shape == "equals":
        return (
            "[equals] `%s` is an unquoted word starting with `=`. zsh expands "
            "`=name` to the path of the command `name`, so this fails with "
            "`(eval):1: %s not found` and ABORTS everything after it in the "
            "command (the same trap as `echo ===` and `[ \"$a\" == \"$b\" ]`).\n"
            "  Rewrite: quote it (`echo '==='`, `echo \"== done ==\"`), or compare "
            "with a single `=` or inside `[[ ]]`: `[ \"$a\" = \"$b\" ]`, "
            "`[[ \"$a\" == \"$b\" ]]`." % (ev, ev[1:])
        )
    if shape == "timeout":
        return (
            "[timeout] `%s` is not installed on this Mac, and neither is "
            "`gtimeout` (no coreutils), so this fails with `command not found: "
            "%s` (exit 127).\n"
            "  Rewrite with perl, which ships with macOS (verified here):\n"
            "      perl -e 'alarm shift; exec @ARGV or die \"exec: $!\"' 300 <cmd> <args>\n"
            "  Exit 142 means it timed out (SIGALRM); otherwise you get <cmd>'s own "
            "exit status. The alarm hits <cmd> itself, so point it at the real "
            "process rather than a `sh -c` wrapper. For long jobs, "
            "`run_in_background` is usually the better tool." % (ev, ev)
        )
    if shape == "glob_opt":
        return (
            "[glob_opt] `%s` has an unquoted `*` or `?`. zsh globs the WHOLE word, "
            "finds no file named like it, and aborts with `no matches found: %s` "
            "before the command runs.\n"
            "  Rewrite: quote the word: %s (or \"%s\"); for a URL, quote the "
            "whole URL." % (ev, ev, _quote_rewrite(ev), ev)
        )
    if shape == "pipestatus":
        return (
            "[pipestatus] `%s`: PIPESTATUS is bash only. The Bash tool runs zsh, "
            "where it does not exist, so it is ALWAYS EMPTY and any exit code "
            "read from it is invented.\n"
            "  Rewrite: `$pipestatus` (zsh, lowercase, 1-indexed: "
            "`${pipestatus[1]}` is the first command of the last pipeline), or "
            "drop the pipe and read `$?` (QUIRKS.md line 1):\n"
            "      <cmd> > /tmp/out.log 2>&1; echo EXIT=$?; tail -40 /tmp/out.log\n"
            "  In a script bash will run, single-quote it or escape it as "
            "`\\${PIPESTATUS[0]}`." % ev
        )
    if shape == "for_scalar":
        var, name, raw = ev
        return (
            "[for_scalar] `for %s in %s` loops over `%s`, which this command "
            "assigned a SCALAR that can hold several words (a string with spaces "
            "or a command's output). zsh does not word-split unquoted scalars "
            "(SH_WORD_SPLIT is off), so when it holds several words the loop "
            "runs ONCE with the whole string.\n"
            "  Rewrite: `for %s in ${=%s}` (split on whitespace; also correct "
            "when it holds one word, so it is always safe), make it an array "
            "(`%s=(a b c)`, or `%s=(${(f)\"$(cmd)\"})` for lines), or loop over "
            "the command directly: `for %s in $(cmd)`."
            % (var, raw, name, var, name, name, name, var)
        )
    return "[%s] %s" % (shape, ev)


def block_message(hits):
    """Stderr text for one hit (shape, evidence) or a list of them."""
    if isinstance(hits, tuple):
        hits = [hits]
    parts = [
        "BLOCKED by shell-mechanics-guard: this command contains a shape that "
        "fails EVERY time in this shell (the Bash tool runs `eval` in zsh with "
        "EQUALS and NOMATCH on, on a BSD/macOS userland). Nothing ran; rewrite "
        "and run again."
    ]
    for shape, ev in hits:
        parts.append(_shape_message(shape, ev))
    return "\n\n".join(parts) + "\n"


def _state_path(session_id):
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id or "")) or "unknown"
    return os.path.join(STATE_DIR, sid + ".json")


def _load(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return set(x for x in data if isinstance(x, str)) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save(path, fired):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".sm-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(sorted(fired), f)
        os.replace(tmp, path)
    except Exception:
        pass


def main():
    """Returns the process exit code: 2 = block (message on stderr), 0 = allow."""
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    payload = json.loads(raw)
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return 0

    # BLOCK first. A blocked command never reaches the warn path, so it
    # cannot also emit a warning or spend a warn class's once-per-session budget.
    blocks = find_blocks(command)
    if blocks:
        sys.stderr.write(block_message(blocks))
        sys.stderr.flush()
        return 2

    hits = classify(command)
    if not hits:
        return 0

    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(payload.get("session_id"))
    fired = _load(path)
    new = [h for h in ("exit", "cd") if h in hits and h not in fired]
    if not new:
        return 0
    fired.update(new)
    _save(path, fired)

    msg = "\n\n".join(EXIT_MSG if h == "exit" else CD_MSG for h in new)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "additionalContext": msg,
                }
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    # Fail-open contract: this runs before EVERY Bash call on this machine.
    # Any error, malformed payload, or signal exits 0 and allows; only a
    # deliberate block (main returned 2 after writing stderr) exits 2.
    code = 0
    try:
        code = main()
    except BaseException:
        code = 0
    sys.exit(2 if code == 2 else 0)
