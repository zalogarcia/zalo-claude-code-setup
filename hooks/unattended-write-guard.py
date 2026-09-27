#!/usr/bin/env python3
"""PreToolUse guard: hold migrations and database writes in UNATTENDED runs.

Wired on `Bash|mcp__supabase__apply_migration|mcp__supabase__execute_sql|Write|Edit|MultiEdit`.
Attended runs exit 0 before reading stdin's payload, so the file tools cost
nothing outside an unattended run.

KNOWN PARTIAL (2026-09-27): the bridge passes the scheduled run mark
(LEASH_TRIGGER) to Claude workers only. A scheduled `--run` job routed to
Codex (the bg lane switched with `/engine bg codex`, or a `codex:` prefix)
carries no mark, and Codex's projected hooks predate this guard, so such a
run is NOT held. Until the bridge passes the mark to Codex children and the
Codex projection is regenerated, route scheduled jobs that may write to Claude.

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
  or piped echo/printf whose SQL writes, pg_dump piped into psql, and a
  package script whose NAME says it migrates or pushes a database (`npm run
  db:push`, `yarn migrate:deploy`). A file that the SAME command wrote from a
  heredoc (`cat > /tmp/q.sql <<'SQL'`) is read from that heredoc, so a
  read-only query file passes; any other file is unknown and held. `bash -c
  '...'`, `eval`, `docker exec <container> psql ...`, `ssh host cmd` and the
  wrappers nice, sudo, xargs, caffeinate, env, timeout and the perl alarm line
  (`perl -e 'alarm shift; exec @ARGV' N cmd`) are looked through.

Reads (SELECT, EXPLAIN, SHOW, `\\d`) pass.

The owner's write approval is also guarded (QA 2026-09-27): `schedule.mjs
--allow-write`, and any write to the bridge's schedules.json, bg-queue.json
or bg-held.json (Bash redirect, tee, cp, mv, sed -i, or Write/Edit), are held
in an unattended run, so the run cannot approve itself.

A Bash write whose target is PROVEN local passes: psql run through `docker
exec` with no remote host or URL, psql or `--db-url` pointed at a loopback
host or a socket, `supabase ... --local`, `supabase db reset` and `supabase
migration up` without `--linked` (both default to the local stack), and
prisma or drizzle with a loopback DATABASE_URL on the same command line. A
target that cannot be read (a `$DATABASE_URL`, a bare psql on this Mac with
no host) is treated as remote. A variable is read from an assignment in the
same command when there is one; otherwise a variable in a URL-only slot
(`--db-url`, DATABASE_URL) or with a target-like name (URL, DSN, PROD, REMOTE,
POOLER ...) is unknown, and only a plain `-d $DB` inside a local container is
taken as a database name. Anything run over ssh or through a remote docker
daemon (-H, --context, $DOCKER_HOST) is never local. Measured reason (replay of 176,182 Bash calls
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
FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
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


# The comma is a token so an alias before a parenthesised expression
# (`AS charge_count, (SELECT ...)`) never reads as a call `charge_count(`.
_SQL_TOKEN = re.compile(r"\\[A-Za-z_]+|[A-Za-z_][A-Za-z0-9_$]*|[();.,]|[=<>!+*/|%^~&:-]+")
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
    "NET.HTTP_POST", "NET.HTTP_DELETE", "NET.HTTP_GET", "LO_UNLINK", "DBLINK_EXEC",
    "LO_IMPORT", "LO_CREATE", "LO_FROM_BYTEA", "LO_PUT",
}
# The unqualified names above also match when schema qualified
# (`pg_catalog.setval(...)`, found by QA 2026-09-27).
_UNQUALIFIED_MUTATING = {f for f in MUTATING_FUNCTIONS if "." not in f}

# A project's own functions called from a SELECT: the 60-day replay found 15
# writes shaped `SELECT public.set_user_plan_service(...)`, `...ingest()`,
# `...sweep_...()`, `...reconcile_...()` (QA 2026-09-27). A function whose name
# carries one of these verbs is held: any word of the name when it is schema
# qualified outside the system schemas, the FIRST word when unqualified (so the
# builtins jsonb_set, array_remove, ... pass; the few builtins that start with
# one are listed).
WRITE_VERBS = {
    "SET", "INSERT", "UPDATE", "DELETE", "UPSERT", "CREATE", "DROP", "INGEST", "SWEEP",
    "RECONCILE", "APPLY", "GRANT", "REVOKE", "RESET", "PURGE", "BACKFILL", "SYNC", "MARK",
    "RECORD", "ENQUEUE", "DEQUEUE", "CLAIM", "ASSIGN", "ARCHIVE", "ROTATE", "REFRESH",
    "REBUILD", "MIGRATE", "SEED", "IMPORT", "MERGE", "CLEANUP", "PRUNE", "EXPIRE", "CANCEL",
    "APPROVE", "REJECT", "SEND", "NOTIFY", "BUMP", "INCREMENT", "DECREMENT", "AWARD",
    "CREDIT", "DEBIT", "CHARGE", "REFUND", "PROVISION", "DEPROVISION", "ENROLL", "UNENROLL",
    "ATTACH", "DETACH", "LINK", "UNLINK", "ADD", "REMOVE", "SAVE", "STORE", "WRITE", "PUT",
    "TOUCH", "TRIGGER", "PROCESS", "HANDLE", "RELEASE", "CONSUME", "REGISTER", "UNREGISTER",
    "SUBSCRIBE", "UNSUBSCRIBE", "TRANSFER", "SETTLE", "RESTORE", "TRUNCATE", "ALTER",
    "EXECUTE", "RUN", "INVOKE", "DISPATCH", "ACTIVATE", "DEACTIVATE", "ENABLE", "DISABLE",
    "BLOCK", "UNBLOCK", "BAN", "UNBAN", "CONFIRM", "COMPLETE", "FINALIZE", "FLUSH", "CLEAR",
    "EVICT", "REPAIR", "FIX", "REASSIGN", "UPGRADE", "DOWNGRADE",
}
_SYSTEM_SCHEMAS = {"PG_CATALOG", "INFORMATION_SCHEMA", "EXTENSIONS", "PG_TEMP", "PG_TOAST"}
_READ_BUILTINS_WITH_VERB = {"SET_CONFIG", "SET_BIT", "SET_BYTE", "SET_MASKLEN", "SETSEED",
                            "CLOCK_TIMESTAMP"}


def _write_verb_function(name):
    """True when a called function's name says it writes (see WRITE_VERBS)."""
    schema, dot, fn = name.rpartition(".")
    if fn in _READ_BUILTINS_WITH_VERB or schema in _SYSTEM_SCHEMAS:
        return False
    words = [w for w in fn.split("_") if w]
    if not words:
        return False
    # The verb leads (set_user_plan_service) or closes (sales_challenge_ingest)
    # a function's name; a verb in the middle is usually a noun
    # (hourly_send_governor_status). Qualified names get both ends, unqualified
    # ones the first word only, so builtins like jsonb_set pass.
    if dot:
        return words[0] in WRITE_VERBS or words[-1] in WRITE_VERBS
    return words[0] in WRITE_VERBS


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


def _is_cte_head(words, i, j):
    """`WITH sync_rows(id) AS (` names a CTE and its columns, it calls
    nothing: the name follows WITH, RECURSIVE or a comma, and its parenthesis
    closes into `AS (` (a table function's alias is `AS name`, not `AS (`)."""
    if i == 0 or words[i - 1] not in ("WITH", "RECURSIVE", ","):
        return False
    depth, k = 0, j
    while k < len(words):
        if words[k] == "(":
            depth += 1
        elif words[k] == ")":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return k + 2 < len(words) and words[k + 1] == "AS" and words[k + 2] == "("


def _mutating_call(stmt):
    words = [t for t, _ in stmt]
    for i, t in enumerate(words):
        if t in ("(", ")", ".", ";", ","):
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
        if j < len(words) and words[j] == "(" and (
            name in MUTATING_FUNCTIONS or name.rsplit(".", 1)[-1] in _UNQUALIFIED_MUTATING
        ):
            return f"{name.lower()}() (a side-effecting function)"
        if j < len(words) and words[j] == "(" and _write_verb_function(name) and not _is_cte_head(words, i, j):
            return f"{name.lower()}() (a function whose name says it writes)"
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
    if first == "\\GEXEC":
        return "psql \\gexec (runs the SQL a query generates)"
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
_OPS = ("&&", "||", "|&", ";;", ";", "|", "&", "(", ")")
_REDIR = re.compile(r"(\d*)(<<<|<<-|<<|&>>|&>|>>|>&|<&|<>|>\||>|<)")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")


# The delimiter is a whole shell word (`'END-MSG'`, `"EOF"`, `END_OF.SQL`).
_HEREDOC_OPEN = re.compile(r"""<<(-?)[ \t]*(?:'([^'\n]+)'|"([^"\n]+)"|([^\s;&|<>()'"]+))""")


def _subst_end(cmd, i):
    """Index just past the `$(...)` (or `$((...))`) starting at i, counting
    parentheses and skipping quoted text, comments and heredoc bodies (a
    commit message `"$(cat <<'EOF' ... Zalo's ... EOF)"` must not read its
    apostrophe as a quote and swallow the rest of the command, QA
    2026-09-27); len(cmd) when unterminated."""
    n = len(cmd)
    depth, j = 0, i + 1
    pending = []  # heredoc delimiters whose bodies start at the next newline
    while j < n:
        c = cmd[j]
        if c == "\n" and pending:
            j += 1
            for strip_tabs, delim in pending:
                while j < n:
                    k = cmd.find("\n", j)
                    line = cmd[j:] if k < 0 else cmd[j:k]
                    j = n if k < 0 else k + 1
                    if (line.lstrip("\t") if strip_tabs else line) == delim:
                        break
            pending = []
            continue
        if c == "<" and cmd.startswith("<<", j) and not cmd.startswith("<<<", j):
            m = _HEREDOC_OPEN.match(cmd, j)
            if m:
                pending.append((m.group(1) == "-", m.group(2) or m.group(3) or m.group(4)))
                j = m.end()
                continue
        if c == "#" and cmd[j - 1] in " \t\n;(|&":
            k = cmd.find("\n", j)
            j = n if k < 0 else k
            continue
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = cmd.find("'", j + 1)
            j = n if k < 0 else k + 1
            continue
        if c == '"':
            k = j + 1
            while k < n and cmd[k] != '"':
                k += 2 if cmd[k] == "\\" else 1
            j = k + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _backtick_end(cmd, i):
    """Index just past the backtick substitution starting at i."""
    n = len(cmd)
    j = i + 1
    while j < n and cmd[j] != "`":
        j += 2 if cmd[j] == "\\" else 1
    return min(j + 1, n)


def _take_subst(cmd, i, subs):
    """(raw text, next index) of the substitution at i, recording the command
    text inside it in `subs` so it is read as a command in its own right."""
    if cmd[i] == "`":
        end = _backtick_end(cmd, i)
        inner = cmd[i + 1:end - 1]
    else:
        end = _subst_end(cmd, i)
        arith = cmd.startswith("$((", i)
        inner = "" if arith else cmd[i + 2:end - 1]
    if subs is not None and inner.strip():
        subs.append(inner)
    return cmd[i:end], end


def _read_word(cmd, i, subs=None):
    """(value, quoted, next_index) for the shell word starting at i. `quoted`
    means the word STARTS with a quote: `"then"` is not a keyword, while
    `FOO='x'` is still an assignment. A `$(...)` or backtick substitution is
    PART of the word (its raw text stays in the value, so a value built from
    one reads as unknown), and the command inside it goes to `subs` (QA
    2026-09-27: splitting the command at `$(` let `psql -h $(cat f) -c
    'delete ...'` orphan its -c)."""
    n = len(cmd)
    buf, quoted = [], False
    while i < n:
        c = cmd[i]
        if c == "`" or (c == "$" and i + 1 < n and cmd[i + 1] == "("):
            raw, i = _take_subst(cmd, i, subs)
            buf.append(raw)
            continue
        if c in " \t\n;&|()<>":
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
                if cmd[j] == "`" or (cmd[j] == "$" and j + 1 < n and cmd[j + 1] == "("):
                    raw, j = _take_subst(cmd, j, subs)
                    part.append(raw)
                    continue
                part.append(cmd[j])
                j += 1
            buf.append("".join(part))
            i = j + 1
            continue
        buf.append(c)
        i += 1
    return "".join(buf), quoted, i


def _scan(cmd, subs=None):
    """Tokens: ("w", value, quoted) | ("op", op) | ("redir", op, target) |
    ("heredoc", op, body) | ("herestr", op, value). The command text inside
    every substitution goes to `subs`."""
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
        if c in "<>" and i + 1 < n and cmd[i + 1] == "(":
            # a process substitution `<(cmd)` is a WORD (a file name psql can
            # read), and the command inside it runs too
            end = _subst_end(cmd, i)
            if subs is not None and cmd[i + 2:end - 1].strip():
                subs.append(cmd[i + 2:end - 1])
            toks.append(("w", cmd[i:end], False))
            i = end
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
            if cmd.startswith("<(", i) or cmd.startswith(">(", i):
                # `psql < <(cmd)`: the target is a process substitution
                end = _subst_end(cmd, i)
                if subs is not None and cmd[i + 2:end - 1].strip():
                    subs.append(cmd[i + 2:end - 1])
                word, _, i = cmd[i:end], False, end
            else:
                word, _, i = _read_word(cmd, i, subs)
            if op in ("<<", "<<-"):
                # op carries whether the delimiter was quoted (no expansion)
                toks.append(("heredoc", op + ("'" if _ else ""), ""))
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
        word, quoted, j = _read_word(cmd, i, subs)
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
_FLAGGED_WRAPPERS = {"sudo", "caffeinate", "nice", "stdbuf", "xargs", "env", "doas",
                     "ionice", "chronic", "arch", "taskpolicy", "script"}
_TIMEOUT_WRAPPERS = {"timeout", "gtimeout"}
_RUNNERS = {"npx", "bunx", "pnpx"}
_TWO_WORD_RUNNERS = {("pnpm", "dlx"), ("pnpm", "exec"), ("yarn", "dlx"), ("yarn", "exec"),
                     ("npm", "exec"), ("bun", "x")}
_DB_TOOLS = {"supabase", "prisma", "drizzle-kit", "psql", "pg_restore"}
_SHELLS = {"bash", "sh", "zsh", "dash"}
_DOCKER_VALUE_FLAGS = {"-u", "--user", "-e", "--env", "-w", "--workdir", "--env-file",
                       "--detach-keys"}
# docker's own global flags, before the subcommand. -H/--host/--context/-c pick
# the daemon: a remote daemon means the container is not this Mac's.
_DOCKER_GLOBAL_VALUE_FLAGS = {"-H", "--host", "--context", "-c", "--config", "-l",
                              "--log-level", "--tlscacert", "--tlscert", "--tlskey"}
_DOCKER_REMOTE_FLAGS = {"-H", "--host", "--context", "-c"}
_SSH_VALUE_FLAGS = set("bcDEeFIiJLlmOopQRSWw")
# What a wrapper (nice, sudo, xargs, the perl alarm line ...) may be running:
# the first of these after it is the real program.
_WRAPPED_TARGETS = ({"supabase", "prisma", "drizzle-kit", "psql", "pg_restore", "docker", "ssh", "eval",
                     "npm", "pnpm", "yarn", "bun", "node", "deno"} | {"npx", "bunx", "pnpx"}
                    | {"bash", "sh", "zsh", "dash"})
# Package scripts whose NAME says they migrate or push a database: a
# migrate/migration segment, or db with push/reset/deploy/seed/apply/up, and no
# read-only segment (the replay held 53 `npm run lint:migrations` before this).
_SCRIPT_SPLIT = re.compile(r"[:_./\s-]+")
_SCRIPT_READONLY = {"lint", "test", "tests", "check", "status", "list", "ls", "diff", "generate",
                    "gen", "create", "new", "dry", "dryrun", "validate", "verify", "print",
                    "show", "types", "typecheck", "squash", "info", "help", "format", "fmt"}
_SCRIPT_MIGRATE = {"migrate", "migration", "migrations", "dbpush", "dbreset", "dbmigrate", "dbseed"}
# not "up": `db:up` starts a local database container
_SCRIPT_DB_VERBS = {"push", "reset", "deploy", "seed", "apply"}


def _db_script(name):
    segs = {x for x in _SCRIPT_SPLIT.split(name.lower()) if x}
    if segs & _SCRIPT_READONLY:
        return False
    return bool(segs & _SCRIPT_MIGRATE) or ("db" in segs and bool(segs & _SCRIPT_DB_VERBS))

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
_CONNINFO_HOST = re.compile(r"(?:^|\s)host(?:addr)?\s*=\s*'?([^\s']*)", re.I)
_URI_QUERY_HOST = re.compile(r"[?&]host(?:addr)?=([^&]*)", re.I)
_BARE_VAR = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
# A variable whose NAME says it holds a connection target, not a database name.
_URL_VAR = re.compile(r"URL|URI|DSN|CONN|PROD|REMOTE|POOLER|UPSTREAM|LIVE", re.I)


def _name(word):
    base = word.rsplit("/", 1)[-1]
    if "@" in base[1:]:
        base = base[: base.index("@", 1)]
    return base


def _conn_host(value, assigned=None, url_only=False, _depth=0):
    """Host a connection value names: "" for none (a plain database name or a
    socket URI), the host string, or None when it cannot be known (a
    variable that may hold a URL, or any other expansion).

    `assigned` holds NAME=value pairs this same command set, so
    `PROD=postgresql://...; psql "$PROD"` is read, not guessed. `url_only`
    marks a slot that only ever holds a URL (--db-url, DATABASE_URL): there
    an unread variable is unknown whatever its name (QA 2026-09-27: `--db-url
    "$PROD_DB"` passed as a database name)."""
    v = (value or "").strip()
    bare = _BARE_VAR.fullmatch(v)
    if bare:
        name = bare.group(1)
        if assigned and name in assigned and _depth < 3:
            host = _conn_host(assigned[name], assigned, url_only, _depth + 1)
            if host is not None:
                return host
            # The assignment is itself unreadable (`DB="qa_$$"`): judge the
            # variable by its slot and its name, as if it were not assigned.
        if url_only or _URL_VAR.search(name):
            return None
        return ""
    m = _URI.match(v)
    if m:
        q = _URI_QUERY_HOST.search(v)
        host = q.group(1) if q else m.group(1).strip("[]")
        # a host read literally is known even when the password is `$PW`
        return None if ("$" in host or "`" in host) else host.lower()
    if "$" in v or "`" in v:
        return None
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


def _perl_exec_wrapper(words, i):
    """`perl -e '... exec @ARGV ...' N cmd ...`: the timeout rewrite that
    shell-mechanics-guard prescribes. A perl one-liner that does not exec its
    arguments is just perl."""
    for w, _ in words[i + 1:i + 5]:
        if "exec" in w and "@ARGV" in w:
            return True
    return False


# Flags that take a value, per wrapper, so the value is not read as the program
# (`sudo -u zalo supabase`, `xargs -I {} psql`). Other flags are switches.
_WRAPPER_VALUE_FLAGS = {
    "sudo": {"-u", "-g", "-U", "-C", "-h", "-p", "-r", "-t", "-D", "-R", "-T", "--user",
             "--group", "--other-user", "--close-from", "--host", "--prompt", "--role",
             "--type", "--chdir", "--chroot", "--command-timeout"},
    "doas": {"-u", "-C"},
    "xargs": {"-I", "-J", "-L", "-n", "-P", "-R", "-S", "-s", "-E", "-d", "-a", "--max-args",
              "--max-procs", "--replace", "--delimiter", "--arg-file", "--max-lines", "--eof",
              "--max-chars"},
    "nice": {"-n", "--adjustment"},
    "caffeinate": {"-t", "-w"},
    "stdbuf": {"-i", "-o", "-e"},
    "env": {"-u", "-S", "-P", "-C", "--unset", "--chdir", "--split-string"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "gtimeout": {"-s", "-k", "--signal", "--kill-after"},
    "ionice": {"-c", "-n", "-p"},
    "taskpolicy": {"-c", "-b", "-t", "-l"},
    "arch": {"-arch"},
    "script": {"-t", "-F"},
}
_WRAPPER_WORDS = _FLAGGED_WRAPPERS | _TIMEOUT_WRAPPERS | {"perl"}


def _find_wrapped(words, start, env, wrapper=""):
    """Index of the program a wrapper runs: the first word at or after
    `start` that is not one of the wrapper's own flags, flag values,
    durations or NAME=value assignments (recorded into `env`), provided it is
    a program this hook reads or another wrapper. None otherwise, and then
    the wrapper runs something this hook does not read (QA 2026-09-27: a
    forward scan that jumped over words read `xargs grep -l psql` as psql)."""
    value_flags = _WRAPPER_VALUE_FLAGS.get(wrapper, set())
    k = start
    # `script [-q] FILE cmd ...`: its first plain word is the typescript file
    file_arg = wrapper == "script"
    while k < len(words):
        w, q = words[k]
        if q:
            k += 1  # the perl alarm line's script, a quoted flag value
            continue
        if w in value_flags:
            k += 2
            continue
        if w.startswith("-") or w.isdigit() or w == "{}" or re.fullmatch(r"\d+[smhd]?", w):
            k += 1
            continue
        if _ASSIGN.match(w):
            name, _, val = w.partition("=")
            env[name.rstrip("+")] = val
            k += 1
            continue
        if _name(w) in _WRAPPED_TARGETS or w in _WRAPPER_WORDS or w in _PREFIX_WORDS:
            return k
        if file_arg:
            file_arg = False
            k += 1
            continue
        return None
    return None


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
        if w in _FLAGGED_WRAPPERS or w in _TIMEOUT_WRAPPERS or (
            w == "perl" and _perl_exec_wrapper(words, i)
        ):
            # The wrapped program is the first known one after the wrapper;
            # its own flags and values (`nice -n 10`, `sudo -u zalo`, `xargs
            # -n 1`, the perl alarm line's script and seconds) are skipped
            # whatever they are (QA 2026-09-27: `nice -n 10 supabase db push`
            # read `10` as the program).
            j = _find_wrapped(words, i + 1, env, w)
            if j is not None:
                i = j
                continue
            if w == "perl":
                break
            i += 1
            while i < len(words) and not words[i][1] and (
                words[i][0].startswith("-") or (w == "env" and _ASSIGN.match(words[i][0]))
            ):
                if _ASSIGN.match(words[i][0]):
                    name, _, val = words[i][0].partition("=")
                    env[name] = val
                i += 1
            if w in _TIMEOUT_WRAPPERS:
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


# `docker run` options that take a value (the rest are switches).
_DOCKER_RUN_VALUE_FLAGS = {
    "-e", "--env", "--env-file", "-v", "--volume", "--name", "--network", "--net", "-p",
    "--publish", "-w", "--workdir", "-u", "--user", "--entrypoint", "--platform", "-m",
    "--memory", "--add-host", "--mount", "-l", "--label", "--label-file", "--cpus", "--pull",
    "--restart", "-h", "--hostname", "--cidfile", "--log-driver", "--log-opt", "--gpus",
    "--shm-size", "--ulimit", "--tmpfs", "--device", "--dns", "--ipc", "--pid", "--cap-add",
    "--cap-drop", "--security-opt", "--stop-signal", "--stop-timeout", "--expose", "--link",
    "--volumes-from", "--runtime", "--memory-swap", "--cpuset-cpus", "--health-cmd",
    "--detach-keys", "--attach", "-a",
}
_UNKNOWN_HOST = "$UNKNOWN_HOST"


def _docker_exec_inner(argv, outer_env=None):
    """(argv, env, remote_daemon, in_container) of the command a `docker
    exec`, `docker compose exec` or `docker run IMAGE cmd` runs, or None.
    `remote_daemon` is True when -H/--host/--context/-c or $DOCKER_HOST /
    $DOCKER_CONTEXT pick another daemon: that container is not on this Mac.
    `in_container` is False for `docker run`: a fresh container has no
    database of its own, so its psql reaches whatever host it names (psql is
    not installed on this Mac and briefs prescribe `docker run ... psql`)."""
    words = argv
    n = len(words)
    k = 1
    oe = outer_env or {}
    remote = bool(oe.get("DOCKER_HOST") or oe.get("DOCKER_CONTEXT"))
    while k < n and words[k][0].startswith("-"):
        flag, eq, _ = words[k][0].partition("=")
        k += 1
        if flag in _DOCKER_REMOTE_FLAGS:
            remote = True
        if flag in _DOCKER_GLOBAL_VALUE_FLAGS and not eq and k < n:
            k += 1
    if k < n and words[k][0] == "compose":
        k += 1
        while k < n and words[k][0].startswith("-"):
            k += 1
    if k >= n or words[k][0] not in ("exec", "run"):
        return None
    is_run = words[k][0] == "run"
    value_flags = _DOCKER_RUN_VALUE_FLAGS if is_run else _DOCKER_VALUE_FLAGS
    k += 1
    env = {}
    entrypoint = None
    while k < n and words[k][0].startswith("-"):
        raw = words[k][0]
        flag, has_eq, inline = raw.partition("=")
        if flag.startswith("-e") and not flag.startswith("--") and len(flag) > 2:
            # attached short form: -ePGHOST=db.x (flag "-ePGHOST", inline "db.x")
            inline = flag[2:] + ("=" + inline if has_eq else "")
            flag = "-e"
        k += 1
        if flag in value_flags:
            val = inline
            if not inline and k < n:
                val = words[k][0]
                k += 1
            if flag in ("-e", "--env"):
                if "=" in val:
                    name, _, v = val.partition("=")
                    env[name] = v
                elif val:
                    # `-e PGHOST` passes this shell's own value: unknown here.
                    env[val] = _UNKNOWN_HOST
            elif flag == "--env-file":
                # The file can set PGHOST or DATABASE_URL: unknown targets.
                env.setdefault("PGHOST", _UNKNOWN_HOST)
                env.setdefault("DATABASE_URL", _UNKNOWN_HOST)
            elif flag == "--entrypoint":
                entrypoint = val
    if k >= n:
        return None
    rest = words[k + 1:]  # past the container / service name, or the image
    if entrypoint:
        rest = [(entrypoint, False)] + rest
    inner, inner_env = _argv(rest)
    env.update(inner_env)
    return inner, env, remote, not is_run


def _ssh_remote_command(argv):
    """The command text `ssh [opts] host cmd...` runs on the remote host, or
    None (an interactive login runs nothing this hook can read)."""
    k, n = 1, len(argv)
    while k < n and argv[k][0].startswith("-") and argv[k][0] != "-":
        flag = argv[k][0]
        k += 1
        if len(flag) == 2 and flag[1] in _SSH_VALUE_FLAGS and k < n:
            k += 1
    if n - k < 2:
        return None
    return " ".join(a for a, _ in argv[k + 1:])


def _package_script(argv):
    """The script name `npm run X` / `pnpm run X` / `yarn X` / `bun run X`
    runs, or None."""
    prog = _name(argv[0][0])
    args = [a for a, _ in argv[1:] if not a.startswith("-")]
    if not args:
        return None
    if args[0] in ("run", "run-script"):
        return args[1] if len(args) > 1 else None
    # yarn and pnpm run a package script without `run` (`pnpm db:push`)
    if prog in ("yarn", "pnpm") and args[0] not in (
        "add", "install", "i", "remove", "rm", "upgrade", "update", "up", "dlx", "exec",
        "global", "init", "why", "info", "config", "cache", "link", "unlink", "list", "ls",
        "outdated", "audit", "store", "import", "publish", "pack", "create", "test", "start",
        "build", "dev", "lint", "x", "help", "version", "setup", "env", "fetch", "prune",
    ):
        return args[0]
    return None


def _nonflag(args, limit=3):
    return [a for a, _ in args if not a.startswith("-")][:limit]


# supabase subcommand pairs that change a database, and whether each targets the
# local stack when neither --linked, --local nor --db-url says otherwise
_SUPABASE_WRITES = {
    ("db", "push"): False,
    ("db", "reset"): True,
    ("migration", "up"): True,
    ("migration", "down"): True,
    ("migration", "repair"): False,
}


def _flag_value(vals, flag):
    """Value of `--flag=x` or `--flag x`, or None when the flag is absent."""
    for k, a in enumerate(vals):
        if a == flag:
            return vals[k + 1] if k + 1 < len(vals) else ""
        if a.startswith(flag + "="):
            return a[len(flag) + 1:]
    return None


def _supabase_reason(args, assigned=None):
    """(reason, target_is_local) or (None, False)."""
    vals = [a for a, _ in args]
    if "--dry-run" in vals:
        return None, False
    # Every non-flag word, not the first three: global value flags come first
    # (`supabase --workdir /a --profile b db push`, QA 2026-09-27).
    nf = _nonflag(args, limit=len(args))
    for a, b in zip(nf, nf[1:]):
        if (a, b) in _SUPABASE_WRITES:
            db_url = _flag_value(vals, "--db-url")
            linked = _flag_value(vals, "--linked")
            local_flag = _flag_value(vals, "--local")
            if db_url is not None:
                local = _host_is_local(_conn_host(db_url, assigned, url_only=True))
            elif linked is not None and linked.lower() not in ("false", "0"):
                local = False  # --linked or --linked=true (QA 2026-09-27)
            elif local_flag is not None and local_flag.lower() not in ("false", "0"):
                local = True
            else:
                # `db reset` and `migration up|down` default to the local
                # stack; `db push` and `migration repair` to the linked
                # (remote) project.
                local = _SUPABASE_WRITES[(a, b)]
            return f"supabase {a} {b}", local
    return None, False


def _database_url_local(env, assigned=None):
    url = env.get("DATABASE_URL")
    return url is not None and _host_is_local(_conn_host(url, assigned, url_only=True))


def _prisma_reason(args, env, assigned=None):
    nf = _nonflag(args, 2)
    if tuple(nf) in (("migrate", "deploy"), ("migrate", "reset"), ("migrate", "dev"),
                     ("db", "push"), ("db", "execute"), ("db", "seed")):
        return "prisma " + " ".join(nf), _database_url_local(env, assigned)
    return None, False


def _drizzle_reason(args, env, assigned=None):
    nf = _nonflag(args, 1)
    if nf and (nf[0] in ("push", "migrate") or nf[0].startswith("push:")):
        return f"drizzle-kit {nf[0]}", _database_url_local(env, assigned)
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


def _psql_target_local(hosts, conns, env, in_container, assigned=None):
    """True only when every host psql could reach is provably local."""
    named = list(hosts)
    if env.get("PGHOST") is not None:
        named.append(env["PGHOST"])
    if env.get("PGHOSTADDR") is not None:
        named.append(env["PGHOSTADDR"])
    for c in conns:
        h = _conn_host(c, assigned)
        if h is None:
            return False
        if h:
            named.append(h)
    if named:
        return all(_host_is_local(h) for h in named)
    # No host anywhere: inside a container that is the container's own server;
    # on this Mac it is whatever $PGHOST the session inherited, so unknown.
    return in_container


def _body_of(entry):
    return entry[0] if isinstance(entry, tuple) else entry


def _written_body(path, written, in_container=False):
    """The SQL this same command wrote to `path` from a heredoc, else None.
    A basename match covers `docker cp /tmp/x.sql box:/tmp/x.sql`, so it is
    taken only for a psql inside a container: on this Mac `/tmp/q.sql` must
    not vouch for `~/migrations/q.sql` (QA 2026-09-27)."""
    if not path or not written:
        return None
    if path in written:
        return _body_of(written[path])
    if not in_container:
        return None
    base = path.rsplit("/", 1)[-1]
    hits = [_body_of(body) for p, body in written.items() if p.rsplit("/", 1)[-1] == base]
    return hits[0] if len(hits) == 1 else None


def _file_reason(label, path, written, in_container=False):
    """Reason for psql reading `path`: its heredoc body when this command wrote
    it (so a read-only file passes), otherwise the file itself (unknown)."""
    body = _written_body(path, written, in_container)
    if body is None:
        return f"{label} {path}"
    reason = sql_write_reason(body)
    return f"{label} {path} (written above, {reason})" if reason else None


def _unread_sql(text, assigned=None, expands=True):
    """A reason when SQL text reaching psql cannot be read here: only a
    variable (not assigned in this command), or built by a substitution.
    `expands` is False for a quoted heredoc, whose body is literal."""
    if not expands:
        return None
    t = (text or "").strip()
    bare = _BARE_VAR.fullmatch(t)
    if bare and not (assigned and bare.group(1) in assigned):
        return f"SQL from ${bare.group(1)}, a variable this hook cannot read"
    if "$(" in t or "`" in t:
        return "SQL from a command substitution (unknown)"
    return None


def _resolve_sql(text, assigned=None):
    t = (text or "").strip()
    bare = _BARE_VAR.fullmatch(t)
    if bare and assigned and bare.group(1) in assigned:
        return assigned[bare.group(1)]
    return text


def _psql_reason(args, cmd, env, in_container, written, assigned=None):
    """(reason, target_is_local) or (None, False)."""
    commands, files, hosts, conns = _psql_args(args)
    local = _psql_target_local(hosts, conns, env, in_container, assigned)
    for sql in commands:
        # SQL text that is only a variable, or comes from a substitution,
        # cannot be read here unless this command assigned it (QA 2026-09-27:
        # `psql -h <remote> -c "$SQL"` passed as a read).
        bare = _BARE_VAR.fullmatch(sql.strip())
        if bare and assigned and bare.group(1) in assigned:
            sql = assigned[bare.group(1)]
            bare = _BARE_VAR.fullmatch(sql.strip())
        if bare:
            return f"psql -c ${bare.group(1)} (SQL from a variable this hook cannot read)", local
        if "$(" in sql or "`" in sql:
            return "psql -c with SQL from a command substitution (unknown)", local
        r = sql_write_reason(sql)
        if r:
            return f"psql -c {r}", local
    real_files = [f for f in files if f and f != "-"]
    for f in real_files:
        r = _file_reason("psql -f", f, written, in_container)
        if r:
            return r, local
    if commands or real_files:
        return None, False
    # stdin is read only when there is no -c and no -f
    for r in cmd["redirs"]:
        if r[0] == "redir" and r[1] == "<" and r[2]:
            reason = _file_reason("psql <", r[2], written, in_container)
            return (reason, local) if reason else (None, False)
        if r[0] in ("heredoc", "herestr"):
            expands = not (r[0] == "heredoc" and r[1].endswith("'"))
            unread = _unread_sql(r[2], assigned, expands)
            if unread:
                return f"psql fed {unread}", local
            reason = sql_write_reason(_resolve_sql(r[2], assigned) if expands else r[2])
            if reason:
                return f"psql fed SQL that writes: {reason}", local
    src = cmd.get("piped_from")
    if src:
        sargv, _ = _argv(src["words"])
        if sargv:
            prog = _name(sargv[0][0])
            if prog in ("echo", "printf"):
                words = [a for a, _ in sargv[1:] if not (prog == "echo" and a in ("-e", "-n", "-E"))]
                if prog == "printf" and len(words) > 1 and "%" in words[0]:
                    words = words[1:]  # the format string is not the SQL
                text = " ".join(words)
                unread = _unread_sql(text, assigned)
                if unread:
                    return f"psql fed {unread}", local
                reason = sql_write_reason(_resolve_sql(text, assigned))
                if reason:
                    return f"psql fed SQL that writes: {reason}", local
            elif prog in ("pg_dump", "pg_dumpall"):
                return f"{prog} piped into psql (a restore)", local
            elif prog == "cat":
                for r in src["redirs"]:
                    if r[0] in ("heredoc", "herestr"):
                        expands = not (r[0] == "heredoc" and r[1].endswith("'"))
                        unread = _unread_sql(r[2], assigned, expands)
                        if unread:
                            return f"psql fed {unread}", local
                        reason = sql_write_reason(r[2])
                        if reason:
                            return f"psql fed SQL that writes: {reason}", local
                    elif r[0] == "redir" and r[1] == "<" and r[2]:
                        reason = _file_reason("psql <", r[2], written, in_container)
                        return (reason, local) if reason else (None, False)
                files = [a for a, _ in sargv[1:] if not a.startswith("-")]
                for f in files:
                    reason = _file_reason("psql <", f, written, in_container)
                    if reason:
                        return reason, local
                if files:
                    return None, False
            else:
                # Any other producer (gunzip, python, sed, a script) feeds SQL
                # this hook cannot read: a restore is exactly this shape.
                return f"psql fed by {prog} (SQL this hook cannot read)", local
    return None, False


def _pg_restore_reason(args, env, in_container, assigned=None):
    """pg_restore writes into its target database unless it only lists."""
    vals = [a for a, _ in args]
    if any(v in ("-l", "--list") for v in vals):
        return None, False
    if not any(v in ("-d", "--dbname") or v.startswith("--dbname=") or
               (v.startswith("-d") and len(v) > 2) for v in vals):
        return None, False  # no -d: it prints SQL to stdout, writes nothing
    _, _, hosts, conns = _psql_args(args)
    # _psql_args reads positionals as connections; for pg_restore the
    # positional is the dump file, so keep only -d values and hosts.
    dbnames = []
    for k, v in enumerate(vals):
        if v in ("-d", "--dbname") and k + 1 < len(vals):
            dbnames.append(vals[k + 1])
        elif v.startswith("--dbname="):
            dbnames.append(v[len("--dbname="):])
        elif v.startswith("-d") and len(v) > 2:
            dbnames.append(v[2:])
    return "pg_restore (a restore)", _psql_target_local(hosts, dbnames, env, in_container, assigned)


# The bridge's schedule and queue files: the write approval lives in the first,
# and a queued job's mark in the other two. An unattended run that edits them
# directly could approve itself (QA 2026-09-27), so they are held like a write.
BRIDGE_STATE_FILES = {"schedules.json", "bg-queue.json", "bg-held.json"}
BRIDGE_DIR_MARK = "claude-telegram-bridge"


def _is_bridge_state(path):
    """A bridge state file by name, in a path that names the bridge's
    directory (a scratch copy in /tmp/sched-audit is a test, not the queue)."""
    p = str(path or "")
    return p.rsplit("/", 1)[-1] in BRIDGE_STATE_FILES and BRIDGE_DIR_MARK in p


def _grants_write_approval(args):
    vals = [a for a, _ in args]
    if not any(v.rsplit("/", 1)[-1] == "schedule.mjs" for v in vals):
        return False
    for k, v in enumerate(vals):
        if v == "--allow-write":
            nxt = vals[k + 1] if k + 1 < len(vals) else ""
            return nxt != "false"
        if v.startswith("--allow-write="):
            return v.split("=", 1)[1] != "false"
    return False


_INTERPRETERS = {"python", "python3", "node", "perl", "ruby", "deno", "bun", "osascript"}
_STATE_PATH_RE = re.compile(r"claude-telegram-bridge[^'\"\s]*/(?:schedules|bg-queue|bg-held)\.json")
_SCRIPT_WRITE_RE = re.compile(
    r"open\([^)]*['\"][wax+]|writeFile|appendFile|json\.dump\(|write_text\(|\.write\(|os\.replace\(|"
    r"os\.rename\(|renameSync\(|shutil\.(?:copy|move)|File\.write|IO\.write|>\s*\$")


def _interpreter_state_write(cmd):
    """An interpreter (python, node, perl ...) whose inline code or heredoc
    names a bridge state file and writes something (QA 2026-09-27: a `python3
    -c "json.dump(..., open('.../schedules.json','w'))"` approved itself)."""
    argv, _ = _argv(cmd["words"])
    if not argv or _name(argv[0][0]).rstrip("0123456789.") not in _INTERPRETERS:
        return None
    text = " ".join(a for a, _ in argv[1:]) + "\n" + "\n".join(
        r[2] for r in cmd["redirs"] if r[0] in ("heredoc", "herestr"))
    m = _STATE_PATH_RE.search(text)
    if m and _SCRIPT_WRITE_RE.search(text):
        return m.group(0)
    return None


def _bridge_state_target(cmd, in_bridge=False):
    """The bridge state file this simple command writes by redirect, tee, cp,
    mv, sed -i or an interpreter's inline code, or None. `in_bridge`: an
    earlier `cd` in this command entered the bridge directory, so a relative
    `schedules.json` is the real one."""
    script = _interpreter_state_write(cmd)
    if script:
        return script
    targets = [r[2] for r in cmd["redirs"] if r[0] == "redir" and r[1] in (">", ">>", ">|", "&>", "&>>")]
    argv, _ = _argv(cmd["words"])
    if argv:
        prog = _name(argv[0][0])
        plain = [a for a, _ in argv[1:] if not a.startswith("-")]
        if prog == "tee":
            targets += plain
        elif prog in ("cp", "mv", "install", "ln", "rsync") and plain:
            targets.append(plain[-1])
        elif prog in ("sed", "gsed", "perl") and any(a.startswith("-i") or a.startswith("-pi") for a, _ in argv[1:]):
            targets += plain
    for t in targets:
        if t and (_is_bridge_state(t) or (
                in_bridge and "/" not in t and t in BRIDGE_STATE_FILES)):
            return t
    return None


def _command_reason(cmd, depth, in_container, written, assigned=None, remote=False):
    argv, env = _argv(cmd["words"])
    if not argv:
        return None
    prog = _name(argv[0][0])
    if prog == "docker":
        inner = _docker_exec_inner(argv, env)
        if not inner:
            return None
        argv, env, remote_daemon, in_container = inner
        remote = remote or remote_daemon
        if not argv:
            return None
        prog = _name(argv[0][0])
    if prog == "ssh":
        # Whatever runs over ssh runs on another machine: never local.
        text = _ssh_remote_command(argv)
        if text is None or depth >= 3:
            return None
        return bash_write_reason(text, depth + 1, False, written, assigned, remote=True)
    if prog in _SHELLS or prog == "eval":
        if depth >= 3:
            return None
        if prog == "eval":
            return bash_write_reason(" ".join(a for a, _ in argv[1:]), depth + 1,
                                     in_container, written, assigned, remote)
        for idx, (a, _) in enumerate(argv[1:], start=1):
            if a.startswith("-") and not a.startswith("--") and "c" in a[1:]:
                if idx + 1 < len(argv):
                    return bash_write_reason(argv[idx + 1][0], depth + 1, in_container,
                                             written, assigned, remote)
                return None
        return None
    args = argv[1:]
    if prog == "supabase":
        reason, local = _supabase_reason(args, assigned)
    elif prog == "prisma":
        reason, local = _prisma_reason(args, env, assigned)
    elif prog == "drizzle-kit":
        reason, local = _drizzle_reason(args, env, assigned)
    elif prog == "psql":
        reason, local = _psql_reason(args, cmd, env, in_container, written, assigned)
    elif prog == "pg_restore":
        reason, local = _pg_restore_reason(args, env, in_container, assigned)
    elif prog in ("node", "bun", "deno") and _grants_write_approval(args):
        return "schedule.mjs --allow-write (the owner's write approval; an unattended run cannot grant it)"
    elif prog in ("npm", "pnpm", "yarn", "bun"):
        # A package script cannot be read from here; hold only the ones whose
        # NAME says they migrate or push a database (QA 2026-09-27).
        script = _package_script(argv)
        if script and _db_script(script):
            return f"{prog} run {script} (a package script named as a database migration or push)"
        return None
    else:
        return None
    if reason and local and not remote and not HOLD_LOCAL_TARGETS:
        return None
    return reason


def _heredoc_files(cmds, base=0):
    """{path: (body, index)} for every `cat > path <<EOF ... EOF` (or tee) in
    this command, so a psql -f of a file written ABOVE it can be read. A path
    written any other way too (`>>`, a second `>`, `tee -a`, `sed -i`, a
    cp/mv/install target) holds more than this heredoc and is dropped
    (QA 2026-09-27: `cat > f <<SQL select SQL; cat >> f <<SQL delete SQL`)."""
    vouched, dropped, seen = {}, set(), {}
    for idx, cmd in enumerate(cmds):
        argv, _ = _argv(cmd["words"])
        prog = _name(argv[0][0]) if argv else ""
        args = [a for a, _ in argv[1:]]
        bodies = [r[2] for r in cmd["redirs"] if r[0] == "heredoc"]
        full = [r[2] for r in cmd["redirs"] if r[0] == "redir" and r[1] in (">", ">|", "&>")]
        other = [r[2] for r in cmd["redirs"] if r[0] == "redir" and r[1] in (">>", "&>>")]
        if prog == "tee":
            if any(a in ("-a", "--append") for a in args):
                other += [a for a in args if not a.startswith("-")]
            else:
                full += [a for a in args if not a.startswith("-")]
        elif prog in ("sed", "perl", "gsed") and any(a.startswith("-i") or a.startswith("-pi") for a in args):
            other += [a for a in args if not a.startswith("-")]
        elif prog in ("cp", "mv", "install", "rsync", "ln", "dd"):
            plain = [a for a in args if not a.startswith("-")]
            if plain:
                other.append(plain[-1])
            other += [a[3:] for a in args if a.startswith("of=")]
        vouch = bool(bodies) and prog in ("cat", "tee")
        for t in full:
            if not t:
                continue
            seen[t] = seen.get(t, 0) + 1
            if vouch and seen[t] == 1:
                vouched[t] = (bodies[-1], base + idx)
            else:
                dropped.add(t)
        for t in other:
            if t:
                dropped.add(t)
    return {p: v for p, v in vouched.items() if p not in dropped}


_DECLARE_WORDS = {"export", "declare", "typeset", "local", "readonly"}


def _assignments(cmds):
    """{NAME: value} for every plain assignment in this command: a
    standalone `NAME=value`, or `export NAME=value` and its kin."""
    out = {}
    for cmd in cmds:
        words = cmd["words"]
        argv, env = _argv(words)
        if not argv:
            out.update(env)
            continue
        if not argv[0][1] and argv[0][0] in _DECLARE_WORDS:
            for w, _ in argv[1:]:
                if _ASSIGN.match(w):
                    name, _, val = w.partition("=")
                    out[name.rstrip("+")] = val
    return out


def bash_write_reason(command, depth=0, in_container=False, written=None, assigned=None,
                      remote=False):
    """A short reason when the command runs a migration or a database write
    against a target not proven local, else None. `remote` marks text that
    runs on another machine (over ssh or a remote docker daemon)."""
    if not isinstance(command, str) or not command.strip():
        return None
    subs = []
    cmds = _simple_commands(_scan(command, subs))
    outer = {p: (_body_of(v), -1) for p, v in (written or {}).items()}
    mine = _heredoc_files(cmds)
    names = dict(assigned or {})
    names.update(_assignments(cmds))
    in_bridge = False
    for cmd in cmds:
        argv, _ = _argv(cmd["words"])
        if argv and argv[0][0] in ("cd", "pushd") and len(argv) > 1:
            in_bridge = BRIDGE_DIR_MARK in argv[1][0]
        state = _bridge_state_target(cmd, in_bridge)
        if state:
            return f"a direct write to {state} (the bridge's schedule or queue, where the write approval lives)"
    for idx, cmd in enumerate(cmds):
        # A heredoc vouches only for commands AFTER the one that wrote it.
        files = dict(outer)
        files.update({p: v for p, v in mine.items() if v[1] < idx})
        reason = _command_reason(cmd, depth, in_container, files, names, remote)
        if reason:
            return reason
    files = dict(outer)
    files.update(mine)
    # The commands inside `$(...)` and backticks run too, on this machine
    # (or on the remote one, for text an ssh runs).
    if depth < 3:
        for inner in subs:
            reason = bash_write_reason(inner, depth + 1, False, files, names, remote)
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
        "  3. Stop there. Only Zalo can approve it: he applies it himself, or\n"
        "     re-schedules the job with `schedule.mjs ... --run --allow-write` from\n"
        "     his own chat. That approval is his alone: never pass --allow-write,\n"
        "     edit schedules.json or set LEASH_ALLOW_WRITE yourself to get past\n"
        "     this hold (schedule.mjs refuses --allow-write from a worker).\n"
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
    elif tool in FILE_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") if isinstance(tool_input, dict) else None
        if isinstance(path, str) and _is_bridge_state(path):
            reason = f"{tool} {path} (the bridge's schedule or queue, where the write approval lives)"
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
