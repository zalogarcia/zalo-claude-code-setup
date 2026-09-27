#!/usr/bin/env python3
"""PreToolUse guard: hold migrations and database writes in UNATTENDED runs.

Wired on `Bash|mcp__supabase__apply_migration|mcp__supabase__execute_sql`.

Why this exists (self-audit 2026-09-27, P5; first proposed 09-19)
------------------------------------------------------------------
`~/.claude/CLAUDE.md` (Git and Deployment): "Pushing, deploying and migrations
need Zalo's go-ahead everywhere, including inside skills and commands that run
autonomously." Nothing enforced it. In one week a worker applied two prod
Supabase migrations without a go-ahead for those steps (ef2be2ff), and an
unattended scheduled run carried a rollback WRITE its brief never granted
(742fca75). In an attended run the owner is one message away and sees the
step; in an unattended one nobody is, so that is where this hook holds.

Who is unattended
-----------------
    unattended = $TMUX unset AND (
        $LEASH_TRIGGER == "schedule"                     # a bridge schedule entry run
        OR ($LEASH_LANE empty AND
            $CLAUDE_CODE_ENTRYPOINT == "sdk-cli")        # headless `claude -p` from a
    )                                                    # script or launchd job

Everything else is attended and exits 0 before any parsing: tmux sessions,
the bridge chat lane, a bg.mjs worker the owner asked for through the chat,
an interactive cli. $LEASH_ALLOW_WRITE == "1" (the owner approved writes for
that schedule entry when he scheduled it) allows.

What it holds (exit 2)
----------------------
- every `mcp__supabase__apply_migration`;
- `mcp__supabase__execute_sql` whose query writes: INSERT, UPDATE, DELETE,
  MERGE, UPSERT, TRUNCATE, DROP, ALTER, CREATE, GRANT, REVOKE, COMMENT ON,
  COPY ... FROM, SELECT ... INTO, CALL, DO, REFRESH MATERIALIZED VIEW, DML
  inside a WITH, EXPLAIN ANALYZE of any of those, and a short list of
  side-effecting functions (cron.schedule, vault.create_secret, setval,
  pg_terminate_backend, net.http_post ...). Comments, string literals,
  dollar-quoted bodies and quoted identifiers are stripped first, so a SELECT
  that merely mentions 'delete' passes. SELECT ... FOR UPDATE is a lock and
  passes;
- Bash that runs, at command position (not inside a quoted argument, a
  heredoc body, a grep pattern or a commit message): `supabase db push`,
  `supabase migration up`, `supabase db reset` (any npx/bunx prefix; `--dry-run`
  passes), `prisma migrate deploy|reset`, `prisma db push`, `drizzle-kit
  push|migrate`, `psql` with -c/--command text that writes, `psql` with
  -f/--file, `psql` fed from a file (`<`), `psql` fed a heredoc, here string
  or piped echo/printf whose SQL writes, and pg_dump piped into psql. A file
  that the SAME command wrote from a heredoc (`cat > /tmp/q.sql <<'SQL'`) is
  read from that heredoc, so a read-only query file passes; any other file is
  unknown and held. `bash -c '...'` and `docker exec <container> psql ...` are
  looked through.

Reads (SELECT, EXPLAIN, SHOW, `\\d`) pass.

A Bash write whose target is PROVEN local passes: psql run through `docker
exec` with no remote host or URL, psql or `--db-url` pointed at a loopback
host or a socket, `supabase ... --local`, `supabase db reset` and `supabase
migration up` without `--linked` (both default to the local stack), and
prisma or drizzle with a loopback DATABASE_URL on the same command line. A
target that cannot be read (a `$DATABASE_URL`, a bare psql on this Mac with
no host) is treated as remote. Measured reason (replay of 176,182 Bash calls
over 60 days, every class run as if unattended): the literal list matched
621, every one a genuine write to a LOCAL scratch database; with the local
rule and the heredoc file rule, 0 remain, and none of the 592 local verdicts
has a remote host, URL variable or --linked on its psql line.
HOLD_LOCAL_TARGETS = True restores the literal list.

Pure core: `decide(payload, env)` returns (exit_code, stderr_text) and the
classifiers `sql_write_reason(sql)` and `bash_write_reason(command)` return a
short reason or None. The replay harness and the suite import them.

Fail-open contract: any internal error, malformed stdin or unknown payload
exits 0.

Tests: python3 ~/.claude/hooks/unattended-write-guard.test.py
"""

import json
import os
import re
import sys

APPLY_MIGRATION = "mcp__supabase__apply_migration"
EXECUTE_SQL = "mcp__supabase__execute_sql"


# ===========================================================================
# who is unattended
# ===========================================================================
def is_unattended(env):
    if env.get("TMUX"):
        return False
    if env.get("LEASH_TRIGGER") == "schedule":
        return True
    return not env.get("LEASH_LANE") and env.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli"


def run_kind(env):
    if env.get("LEASH_TRIGGER") == "schedule":
        sid = str(env.get("LEASH_SCHEDULE_ID") or "").strip()
        return f"bridge schedule #{sid}" if sid else "a bridge schedule entry (no id in the env)"
    return "a headless script run (claude -p with no bridge lane, e.g. launchd or a cron script)"


# ===========================================================================
# SQL
# ===========================================================================
_DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def strip_sql(sql):
    """Blank out comments, string literals, dollar-quoted bodies and quoted
    identifiers, keeping statement structure (words, parens, semicolons)."""
    out = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
            continue
        if c == "/" and sql.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth += 1
                    j += 2
                elif sql.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            i = j
            out.append(" ")
            continue
        if c == "'":
            prev = sql[i - 1] if i > 0 else ""
            prev2 = sql[i - 2] if i > 1 else ""
            escapes = prev in "eE" and not (prev2.isalnum() or prev2 == "_")
            j = i + 1
            while j < n:
                if escapes and sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            out.append(" '' ")
            continue
        if c == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            out.append(" qident ")
            continue
        if c == "$":
            prev = sql[i - 1] if i > 0 else ""
            m = _DOLLAR_TAG.match(sql, i)
            if m and not (prev.isalnum() or prev == "_"):
                tag = m.group(0)
                j = sql.find(tag, m.end())
                i = n if j < 0 else j + len(tag)
                out.append(" '' ")
                continue
        out.append(c)
        i += 1
    return "".join(out)


_SQL_TOKEN = re.compile(r"\\[A-Za-z_]+|[A-Za-z_][A-Za-z0-9_$]*|[();.]")
_META_LINE = re.compile(r"\\[A-Za-z_][^\n]*")

WRITE_FIRST = {
    "INSERT": "INSERT", "UPDATE": "UPDATE", "DELETE": "DELETE", "MERGE": "MERGE",
    "UPSERT": "UPSERT", "TRUNCATE": "TRUNCATE", "DROP": "DROP", "ALTER": "ALTER",
    "CREATE": "CREATE", "GRANT": "GRANT", "REVOKE": "REVOKE", "CALL": "CALL",
    "REFRESH": "REFRESH MATERIALIZED VIEW", "DO": "DO (anonymous code block)",
    "COMMENT": "COMMENT ON", "SECURITY": "SECURITY LABEL", "REINDEX": "REINDEX",
    "CLUSTER": "CLUSTER", "VACUUM": "VACUUM", "IMPORT": "IMPORT FOREIGN SCHEMA",
    "REASSIGN": "REASSIGN OWNED",
}
DML = ("INSERT", "UPDATE", "DELETE", "MERGE")
STATEMENT_WORDS = {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "WITH", "VALUES",
                   "TABLE", "CREATE", "EXECUTE", "DECLARE"}
PSQL_FILE_META = {"\\I", "\\IR", "\\INCLUDE", "\\INCLUDE_RELATIVE"}

# Functions whose call from a SELECT changes state. Matched as a call (name
# followed by "("), schema qualified where the function lives in a schema.
MUTATING_FUNCTIONS = {
    "CRON.SCHEDULE", "CRON.UNSCHEDULE", "CRON.ALTER_JOB", "CRON.SCHEDULE_IN_DATABASE",
    "VAULT.CREATE_SECRET", "VAULT.UPDATE_SECRET",
    "SETVAL", "PG_TERMINATE_BACKEND", "PG_CANCEL_BACKEND",
    "NET.HTTP_POST", "NET.HTTP_DELETE", "LO_UNLINK", "DBLINK_EXEC",
}


def _tokens(stripped):
    """[(TOKEN_UPPER, depth)] with depth counted from 0 at the top level."""
    toks, depth = [], 0
    for m in _SQL_TOKEN.finditer(stripped):
        t = m.group(0)
        if t == "(":
            toks.append(("(", depth))
            depth += 1
        elif t == ")":
            depth = max(0, depth - 1)
            toks.append((")", depth))
        else:
            toks.append((t.upper(), depth))
    return toks


def _split_statements(toks):
    stmts, cur = [], []
    for t in toks:
        if t[0] == ";":
            if cur:
                stmts.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        stmts.append(cur)
    return stmts


def _mutating_call(stmt):
    words = [t for t, _ in stmt]
    for i, t in enumerate(words):
        if t in ("(", ")", ".", ";"):
            continue
        name = t
        j = i + 1
        if j + 1 < len(words) and words[j] == "." and words[j + 1] not in ("(", ")", "."):
            if i > 0 and words[i - 1] == ".":
                continue
            name = t + "." + words[j + 1]
            j += 2
        elif i > 0 and words[i - 1] == ".":
            continue
        if j < len(words) and words[j] == "(" and name in MUTATING_FUNCTIONS:
            return f"{name.lower()}() (a side-effecting function)"
    return None


def _classify(stmt):
    """Write reason for one statement's tokens, or None."""
    k = 0
    while k < len(stmt) and stmt[k][0] == "(":
        k += 1
    if k >= len(stmt):
        return None
    base = stmt[k][1]
    body = [(t, d - base) for t, d in stmt[k:]]
    first = body[0][0]

    if first in PSQL_FILE_META:
        return f"psql {first.lower()} (runs a SQL file)"
    if first == "\\COPY":
        first = "COPY"
    if first in WRITE_FIRST:
        return WRITE_FIRST[first]
    if first == "COPY":
        if any(t == "FROM" and d == 0 for t, d in body):
            return "COPY ... FROM"
        return None
    if first == "EXPLAIN":
        analyze = False
        for idx, (t, _) in enumerate(body[1:], start=1):
            if t in ("ANALYZE", "ANALYSE"):
                analyze = True
            if t in STATEMENT_WORDS:
                if not analyze:
                    return None
                inner = _classify(body[idx:])
                return f"EXPLAIN ANALYZE {inner}" if inner else None
        return None
    if first == "PREPARE":
        for idx, (t, d) in enumerate(body):
            if t == "AS" and d == 0:
                return _classify(body[idx + 1:])
        return None
    if first in ("SELECT", "WITH", "VALUES", "TABLE"):
        if first == "WITH":
            for idx, (t, _) in enumerate(body):
                if t in DML:
                    prev = body[idx - 1][0] if idx > 0 else ""
                    if t == "UPDATE" and prev in ("FOR", "KEY"):
                        continue
                    return f"{t} inside WITH"
        for idx, (t, d) in enumerate(body):
            if t == "INTO" and d == 0:
                return "SELECT ... INTO (creates a table)"
        return _mutating_call(body)
    return None


def sql_write_reason(sql):
    """A short reason when the SQL writes or changes schema, else None."""
    if not isinstance(sql, str) or not sql.strip():
        return None
    stripped = strip_sql(sql)
    # A psql meta-command runs to the end of its line and is not ended by a
    # semicolon; it also ends any query before it (`\g`, `\gset`). Make each
    # one its own statement so `\set ...` on line 1 cannot swallow the UPDATE
    # on line 3. Literals are already blanked, so a backslash left here is a
    # meta-command.
    stripped = _META_LINE.sub(lambda m: ";" + m.group(0) + ";", stripped)
    for stmt in _split_statements(_tokens(stripped)):
        reason = _classify(stmt)
        if reason:
            return reason
    return None


# ===========================================================================
# Bash
# ===========================================================================
_OPS = ("&&", "||", "|&", ";;", ";", "|", "&", "(", ")", "`")
_REDIR = re.compile(r"(\d*)(<<<|<<-|<<|&>>|&>|>>|>&|<&|<>|>\||>|<)")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")


def _read_word(cmd, i):
    """(value, quoted, next_index) for the shell word starting at i. `quoted`
    means the word STARTS with a quote: `"then"` is not a keyword, while
    `FOO='x'` is still an assignment."""
    n = len(cmd)
    buf, quoted = [], False
    while i < n:
        c = cmd[i]
        if c in " \t\n;&|()<>`":
            break
        if c == "\\":
            if i + 1 < n:
                if cmd[i + 1] == "\n":
                    i += 2
                    continue
                buf.append(cmd[i + 1])
                i += 2
                continue
            i += 1
            continue
        if c == "'":
            quoted = quoted or not buf
            j = cmd.find("'", i + 1)
            j = n if j < 0 else j
            buf.append(cmd[i + 1:j])
            i = j + 1
            continue
        if c == "$" and i + 1 < n and cmd[i + 1] == "'":
            quoted = quoted or not buf
            j = i + 2
            while j < n and cmd[j] != "'":
                j += 2 if cmd[j] == "\\" else 1
            buf.append(cmd[i + 2:min(j, n)])
            i = j + 1
            continue
        if c == '"':
            quoted = quoted or not buf
            j = i + 1
            part = []
            while j < n and cmd[j] != '"':
                if cmd[j] == "\\" and j + 1 < n and cmd[j + 1] in '"\\$`\n':
                    if cmd[j + 1] != "\n":
                        part.append(cmd[j + 1])
                    j += 2
                    continue
                part.append(cmd[j])
                j += 1
            buf.append("".join(part))
            i = j + 1
            continue
        if c == "$" and i + 1 < n and cmd[i + 1] == "(":
            break  # command substitution starts a new command context
        buf.append(c)
        i += 1
    return "".join(buf), quoted, i


def _scan(cmd):
    """Tokens: ("w", value, quoted) | ("op", op) | ("redir", op, target) |
    ("heredoc", op, body) | ("herestr", op, value)."""
    toks = []
    pending = []  # (delimiter, strip_tabs, index into toks)
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in " \t":
            i += 1
            continue
        if c == "\\" and i + 1 < n and cmd[i + 1] == "\n":
            i += 2
            continue
        if c == "\n":
            toks.append(("op", "\n"))
            i += 1
            for delim, strip_tabs, idx in pending:
                lines = []
                while i < n:
                    j = cmd.find("\n", i)
                    line = cmd[i:] if j < 0 else cmd[i:j]
                    i = n if j < 0 else j + 1
                    if (line.lstrip("\t") if strip_tabs else line) == delim:
                        break
                    lines.append(line)
                toks[idx] = ("heredoc", toks[idx][1], "\n".join(lines))
            pending = []
            continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()"):
            j = cmd.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "$" and i + 1 < n and cmd[i + 1] == "(":
            toks.append(("op", "("))
            i += 2
            continue
        m = _REDIR.match(cmd, i)
        if m:
            op = m.group(2)
            i = m.end()
            while i < n and cmd[i] in " \t":
                i += 1
            if op in (">&", "<&") and i < n and (cmd[i].isdigit() or cmd[i] == "-"):
                i += 1
                continue
            word, _, i = _read_word(cmd, i)
            if op in ("<<", "<<-"):
                toks.append(("heredoc", op, ""))
                pending.append((word, op == "<<-", len(toks) - 1))
            elif op == "<<<":
                toks.append(("herestr", op, word))
            else:
                toks.append(("redir", op, word))
            continue
        matched = False
        for op in _OPS:
            if cmd.startswith(op, i):
                toks.append(("op", op))
                i += len(op)
                matched = True
                break
        if matched:
            continue
        word, quoted, j = _read_word(cmd, i)
        if j == i:  # defensive: never loop in place
            i += 1
            continue
        toks.append(("w", word, quoted))
        i = j
    return toks


def _simple_commands(toks):
    """[{"words": [(value, quoted)], "redirs": [...], "piped_from": prev|None}]"""
    cmds, cur, pipe_next = [], None, False

    def flush():
        nonlocal cur
        if cur and (cur["words"] or cur["redirs"]):
            cmds.append(cur)
        cur = None

    for t in toks:
        if t[0] == "op":
            flush()
            pipe_next = t[1] in ("|", "|&")
            continue
        if cur is None:
            cur = {"words": [], "redirs": [],
                   "piped_from": (cmds[-1] if pipe_next and cmds else None)}
            pipe_next = False
        if t[0] == "w":
            cur["words"].append((t[1], t[2]))
        else:
            cur["redirs"].append(t)
    flush()
    return cmds


_PREFIX_WORDS = {"{", "}", "!", "then", "do", "else", "elif", "if", "while", "until",
                 "time", "exec", "command", "builtin", "nohup", "noglob"}
_FLAGGED_WRAPPERS = {"sudo", "caffeinate", "nice", "stdbuf", "xargs", "env"}
_TIMEOUT_WRAPPERS = {"timeout", "gtimeout"}
_RUNNERS = {"npx", "bunx", "pnpx"}
_TWO_WORD_RUNNERS = {("pnpm", "dlx"), ("pnpm", "exec"), ("yarn", "dlx"), ("yarn", "exec"),
                     ("npm", "exec"), ("bun", "x")}
_DB_TOOLS = {"supabase", "prisma", "drizzle-kit", "psql"}
_SHELLS = {"bash", "sh", "zsh", "dash"}
_DOCKER_VALUE_FLAGS = {"-u", "--user", "-e", "--env", "-w", "--workdir", "--env-file",
                       "--detach-keys"}

# Local targets. The 60-day replay (2026-09-27) ran this pattern over every Bash
# command in every class as if unattended: 621 matches, every one a genuine
# write, and every one a LOCAL scratch database (611 psql calls through
# `docker exec` into the local Supabase container, the rest `--local` resets
# and loopback URLs). Not one reached a remote database. The rule this hook
# enforces is about shared infrastructure, so a target proven local passes.
# Set HOLD_LOCAL_TARGETS = True to hold them too (the literal 09-27 list).
HOLD_LOCAL_TARGETS = False
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
_URI = re.compile(r"postgres(?:ql)?://(?:[^@/]*@)?(\[[^\]]*\]|[^:/?,]*)", re.I)
_CONNINFO_HOST = re.compile(r"(?:^|\s)host\s*=\s*'?([^\s']*)", re.I)
_BARE_VAR = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_URL_VAR = re.compile(r"URL|URI|DSN|CONN", re.I)


def _name(word):
    base = word.rsplit("/", 1)[-1]
    if "@" in base[1:]:
        base = base[: base.index("@", 1)]
    return base


def _conn_host(value):
    """Host a connection value names: "" for none (a plain database name or a
    socket URI), the host string, or None when it cannot be known (a
    variable that may hold a URL, or any other expansion)."""
    v = (value or "").strip()
    bare = _BARE_VAR.fullmatch(v)
    if bare:
        return None if _URL_VAR.search(bare.group(1)) else ""
    if "$" in v or "`" in v:
        return None
    m = _URI.match(v)
    if m:
        return m.group(1).strip("[]").lower()
    m = _CONNINFO_HOST.search(v)
    if m:
        return m.group(1).lower()
    return ""


def _host_is_local(host):
    if host is None:
        return False
    if "$" in host or "`" in host:
        return False
    return host.lower() in LOCAL_HOSTS or host.startswith("/")


def _argv(words):
    """Strip env assignments, shell keywords and wrappers. Returns (argv, env):
    argv is the program that actually runs, a list of (value, quoted); env is
    the NAME=value assignments seen on the way."""
    env = {}
    i = 0
    while i < len(words):
        w, q = words[i]
        if q:
            break
        if _ASSIGN.match(w):
            name, _, val = w.partition("=")
            env[name.rstrip("+")] = val
            i += 1
            continue
        if w in _PREFIX_WORDS:
            i += 1
            continue
        if w in _FLAGGED_WRAPPERS:
            i += 1
            while i < len(words) and not words[i][1] and (
                words[i][0].startswith("-") or (w == "env" and _ASSIGN.match(words[i][0]))
            ):
                if _ASSIGN.match(words[i][0]):
                    name, _, val = words[i][0].partition("=")
                    env[name] = val
                i += 1
            continue
        if w in _TIMEOUT_WRAPPERS:
            i += 1
            while i < len(words) and words[i][0].startswith("-"):
                i += 1
            i += 1  # the duration
            continue
        break
    argv = words[i:]
    # package runners: npx [-y] [-p pkg] tool ..., pnpm dlx tool ..., yarn tool ...
    if argv and not argv[0][1]:
        head = argv[0][0]
        if head in _RUNNERS:
            argv = argv[1:]
            while argv and argv[0][0].startswith("-"):
                flag = argv[0][0]
                argv = argv[1:]
                if flag in ("-p", "--package") and argv:
                    argv = argv[1:]
        elif len(argv) > 1 and (head, argv[1][0]) in _TWO_WORD_RUNNERS:
            argv = argv[2:]
            while argv and argv[0][0].startswith("-"):
                argv = argv[1:]
        elif head in ("yarn", "pnpm", "bun") and len(argv) > 1 and _name(argv[1][0]) in _DB_TOOLS:
            argv = argv[1:]
        if argv and argv[0][0] == "--":
            argv = argv[1:]
    return argv, env


def _docker_exec_inner(argv):
    """(argv, env) of the command a `docker exec` / `docker compose exec` runs
    inside the container, or None."""
    rest = argv[1:]
    if rest and rest[0][0] == "compose":
        rest = rest[1:]
        while rest and rest[0][0].startswith("-"):
            rest = rest[1:]
    if not rest or rest[0][0] != "exec":
        return None
    rest = rest[1:]
    env = {}
    while rest and rest[0][0].startswith("-"):
        flag, _, inline = rest[0][0].partition("=")
        rest = rest[1:]
        if flag in _DOCKER_VALUE_FLAGS:
            val = inline
            if not inline and rest:
                val = rest[0][0]
                rest = rest[1:]
            if flag in ("-e", "--env") and "=" in val:
                name, _, v = val.partition("=")
                env[name] = v
    if not rest:
        return None
    inner, inner_env = _argv(rest[1:])  # skip the container / service name
    env.update(inner_env)
    return inner, env


def _nonflag(args, limit=3):
    return [a for a, _ in args if not a.startswith("-")][:limit]


def _flag_value(vals, flag):
    """Value of `--flag=x` or `--flag x`, or None when the flag is absent."""
    for k, a in enumerate(vals):
        if a == flag:
            return vals[k + 1] if k + 1 < len(vals) else ""
        if a.startswith(flag + "="):
            return a[len(flag) + 1:]
    return None


def _supabase_reason(args):
    """(reason, target_is_local) or (None, False)."""
    vals = [a for a, _ in args]
    if "--dry-run" in vals:
        return None, False
    nf = _nonflag(args)
    for a, b in zip(nf, nf[1:]):
        if (a, b) in (("db", "push"), ("db", "reset"), ("migration", "up")):
            db_url = _flag_value(vals, "--db-url")
            if db_url is not None:
                local = _host_is_local(_conn_host(db_url))
            elif "--linked" in vals:
                local = False
            elif "--local" in vals:
                local = True
            else:
                # `db reset` and `migration up` default to the local stack;
                # `db push` defaults to the linked (remote) project.
                local = (a, b) != ("db", "push")
            return f"supabase {a} {b}", local
    return None, False


def _database_url_local(env):
    url = env.get("DATABASE_URL")
    return url is not None and _host_is_local(_conn_host(url))


def _prisma_reason(args, env):
    nf = _nonflag(args, 2)
    if tuple(nf) in (("migrate", "deploy"), ("migrate", "reset"), ("db", "push")):
        return "prisma " + " ".join(nf), _database_url_local(env)
    return None, False


def _drizzle_reason(args, env):
    nf = _nonflag(args, 1)
    if nf and (nf[0] in ("push", "migrate") or nf[0].startswith("push:")):
        return f"drizzle-kit {nf[0]}", _database_url_local(env)
    return None, False


_PSQL_SHORT_VALUE = set("cdfFhLopPRTUv")
_PSQL_LONG_VALUE = {"--command", "--dbname", "--file", "--field-separator", "--host",
                    "--log-file", "--output", "--port", "--pset", "--record-separator",
                    "--table-attr", "--username", "--set", "--variable"}


def _psql_args(args):
    """commands, files, hosts, conns (dbname values and positionals)."""
    commands, files, hosts, conns = [], [], [], []
    vals = [a for a, _ in args]
    k = 0
    while k < len(vals):
        a = vals[k]
        if a.startswith("--"):
            name, eq, val = a.partition("=")
            if name in _PSQL_LONG_VALUE:
                if not eq:
                    k += 1
                    val = vals[k] if k < len(vals) else ""
                if name == "--command":
                    commands.append(val)
                elif name == "--file":
                    files.append(val)
                elif name == "--host":
                    hosts.append(val)
                elif name == "--dbname":
                    conns.append(val)
        elif a.startswith("-") and len(a) > 1:
            for pos, ch in enumerate(a[1:], start=1):
                if ch in _PSQL_SHORT_VALUE:
                    val = a[pos + 1:]
                    if not val:
                        k += 1
                        val = vals[k] if k < len(vals) else ""
                    if ch == "c":
                        commands.append(val)
                    elif ch == "f":
                        files.append(val)
                    elif ch == "h":
                        hosts.append(val)
                    elif ch == "d":
                        conns.append(val)
                    break
        else:
            conns.append(a)  # psql [OPTION]... [DBNAME [USERNAME]]
        k += 1
    return commands, files, hosts, conns


def _psql_target_local(hosts, conns, env, in_container):
    """True only when every host psql could reach is provably local."""
    named = list(hosts)
    if env.get("PGHOST") is not None:
        named.append(env["PGHOST"])
    for c in conns:
        h = _conn_host(c)
        if h is None:
            return False
        if h:
            named.append(h)
    if named:
        return all(_host_is_local(h) for h in named)
    # No host anywhere: inside a container that is the container's own server;
    # on this Mac it is whatever $PGHOST the session inherited, so unknown.
    return in_container


def _written_body(path, written):
    """The SQL this same command wrote to `path` from a heredoc, else None.
    A basename match covers `docker cp /tmp/x.sql box:/tmp/x.sql`."""
    if not path or not written:
        return None
    if path in written:
        return written[path]
    base = path.rsplit("/", 1)[-1]
    hits = [body for p, body in written.items() if p.rsplit("/", 1)[-1] == base]
    return hits[0] if len(hits) == 1 else None


def _file_reason(label, path, written):
    """Reason for psql reading `path`: its heredoc body when this command wrote
    it (so a read-only file passes), otherwise the file itself (unknown)."""
    body = _written_body(path, written)
    if body is None:
        return f"{label} {path}"
    reason = sql_write_reason(body)
    return f"{label} {path} (written above, {reason})" if reason else None


def _psql_reason(args, cmd, env, in_container, written):
    """(reason, target_is_local) or (None, False)."""
    commands, files, hosts, conns = _psql_args(args)
    local = _psql_target_local(hosts, conns, env, in_container)
    for sql in commands:
        r = sql_write_reason(sql)
        if r:
            return f"psql -c {r}", local
    real_files = [f for f in files if f and f != "-"]
    for f in real_files:
        r = _file_reason("psql -f", f, written)
        if r:
            return r, local
    if commands or real_files:
        return None, False
    # stdin is read only when there is no -c and no -f
    for r in cmd["redirs"]:
        if r[0] == "redir" and r[1] == "<" and r[2]:
            reason = _file_reason("psql <", r[2], written)
            return (reason, local) if reason else (None, False)
        if r[0] in ("heredoc", "herestr"):
            reason = sql_write_reason(r[2])
            if reason:
                return f"psql fed SQL that writes: {reason}", local
    src = cmd.get("piped_from")
    if src:
        sargv, _ = _argv(src["words"])
        if sargv:
            prog = _name(sargv[0][0])
            if prog in ("echo", "printf"):
                reason = sql_write_reason(" ".join(a for a, _ in sargv[1:]))
                if reason:
                    return f"psql fed SQL that writes: {reason}", local
            elif prog == "pg_dump":
                return "pg_dump piped into psql (a restore)", local
            elif prog == "cat":
                for r in src["redirs"]:
                    if r[0] in ("heredoc", "herestr"):
                        reason = sql_write_reason(r[2])
                        if reason:
                            return f"psql fed SQL that writes: {reason}", local
                    elif r[0] == "redir" and r[1] == "<" and r[2]:
                        reason = _file_reason("psql <", r[2], written)
                        return (reason, local) if reason else (None, False)
                files = [a for a, _ in sargv[1:] if not a.startswith("-")]
                for f in files:
                    reason = _file_reason("psql <", f, written)
                    if reason:
                        return reason, local
                if files:
                    return None, False
    return None, False


def _command_reason(cmd, depth, in_container, written):
    argv, env = _argv(cmd["words"])
    if not argv:
        return None
    prog = _name(argv[0][0])
    if prog == "docker":
        inner = _docker_exec_inner(argv)
        if not inner:
            return None
        argv, env = inner
        in_container = True
        if not argv:
            return None
        prog = _name(argv[0][0])
    if prog in _SHELLS or prog == "eval":
        if depth >= 3:
            return None
        if prog == "eval":
            return bash_write_reason(" ".join(a for a, _ in argv[1:]), depth + 1,
                                     in_container, written)
        for idx, (a, _) in enumerate(argv[1:], start=1):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                if idx + 1 < len(argv):
                    return bash_write_reason(argv[idx + 1][0], depth + 1, in_container,
                                             written)
                return None
        return None
    args = argv[1:]
    if prog == "supabase":
        reason, local = _supabase_reason(args)
    elif prog == "prisma":
        reason, local = _prisma_reason(args, env)
    elif prog == "drizzle-kit":
        reason, local = _drizzle_reason(args, env)
    elif prog == "psql":
        reason, local = _psql_reason(args, cmd, env, in_container, written)
    else:
        return None
    if reason and local and not HOLD_LOCAL_TARGETS:
        return None
    return reason


def _heredoc_files(cmds):
    """{path: body} for every `cat > path <<EOF ... EOF` (or `>>`, or tee) in
    this command, so psql -f of a file written right above can be read."""
    out = {}
    for cmd in cmds:
        argv, _ = _argv(cmd["words"])
        if not argv:
            continue
        prog = _name(argv[0][0])
        bodies = [r[2] for r in cmd["redirs"] if r[0] == "heredoc"]
        if not bodies:
            continue
        targets = [r[2] for r in cmd["redirs"] if r[0] == "redir" and r[1] in (">", ">>", ">|")]
        if prog == "tee":
            targets += [a for a, _ in argv[1:] if not a.startswith("-")]
        elif prog != "cat":
            continue
        for t in targets:
            if t:
                out[t] = bodies[-1]
    return out


def bash_write_reason(command, depth=0, in_container=False, written=None):
    """A short reason when the command runs a migration or a database write
    against a target not proven local, else None."""
    if not isinstance(command, str) or not command.strip():
        return None
    cmds = _simple_commands(_scan(command))
    files = dict(written or {})
    files.update(_heredoc_files(cmds))
    for cmd in cmds:
        reason = _command_reason(cmd, depth, in_container, files)
        if reason:
            return reason
    return None


# ===========================================================================
# decision
# ===========================================================================
def _message(env, tool, reason):
    return (
        f"HELD (unattended-write-guard): {reason}\n"
        "\n"
        f"This run is unattended: {run_kind(env)}. Nobody is watching it, and\n"
        "migrations and database writes need Zalo's explicit go for THIS change\n"
        "(~/.claude/CLAUDE.md, Git and Deployment: \"Pushing, deploying and\n"
        "migrations need Zalo's go-ahead everywhere\").\n"
        "\n"
        "Do this instead:\n"
        "  1. Write the SQL or the migration to a file.\n"
        "  2. Put its path and what it is for in your report.\n"
        "  3. Stop there. Zalo can apply it himself, or re-schedule this job with\n"
        "     `node ~/dev/claude-telegram-bridge/schedule.mjs ... --run --allow-write`.\n"
        "\n"
        "Never retry the write through another route (psql, the REST API, a\n"
        "different MCP tool, a script): the hold is about the change, not the tool.\n"
        f"  tool: {tool}\n"
    )


def decide(payload, env):
    """(exit_code, stderr_text) for one PreToolUse payload."""
    if not is_unattended(env):
        return 0, ""
    if env.get("LEASH_ALLOW_WRITE") == "1":
        return 0, ""
    if not isinstance(payload, dict):
        return 0, ""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    reason = None
    if tool == APPLY_MIGRATION:
        name = tool_input.get("name") if isinstance(tool_input, dict) else None
        reason = f"apply_migration {name}" if isinstance(name, str) and name else "apply_migration"
    elif tool == EXECUTE_SQL:
        if isinstance(tool_input, dict):
            r = sql_write_reason(tool_input.get("query"))
            if r:
                reason = f"execute_sql {r}"
    elif tool == "Bash":
        if isinstance(tool_input, dict):
            reason = bash_write_reason(tool_input.get("command"))
    if not reason:
        return 0, ""
    return 2, _message(env, tool, reason)


def main():
    raw = sys.stdin.read()
    env = os.environ
    if not is_unattended(env):
        return 0  # attended: no parsing at all
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    code, err = decide(payload, env)
    if err:
        sys.stderr.write(err)
    return code


if __name__ == "__main__":
    try:
        rc = main()
    except BaseException:
        rc = 0
    sys.exit(rc)
