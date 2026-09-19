#!/usr/bin/env python3
"""PreToolUse guard for mcp__supabase__execute_sql (+ a PostToolUse note on
mcp__supabase__apply_migration).

v1 (2026-07-11) mechanized two prose rules a 60-session audit showed were
routinely skipped under momentum:
  1. Multi-statement SQL is always blocked — execute_sql returns only the
     LAST statement's result, so earlier output is silently lost.
  2. Schema-first: the first data query of a session is held once, pointing
     at the schema snapshot, to kill column-name guessing.

v2 (2026-07-19 weekly audit, P3): the one-time hold worked 4/4 on first
queries, but guessing resumed on LATER queries. Added:
  3. Per-query table validation against docs/SCHEMA-PROD.md.
  4. Snapshot staleness: >7 days old holds the first query once.

v3 (2026-09-19, making sql-guard.test.py green). The suite is the spec; every
change below is a test it asserts:
  5. Snapshot resolution is by PROJECT REF, not by walking up from cwd. Each
     snapshot declares its project in the header ("Supabase prod project `X`",
     where X may be a $VAR resolved from settings.local.json); a snapshot is
     used only when its ref equals the call's project_id. THE 2026-08-28 BUG
     this fixes: cwd-relative resolution validated project B's query against
     project A's snapshot. An unmatched ref now disables validation entirely
     rather than validating against the wrong file. `-- schema-repo: <dir>`
     in the query overrides. Several snapshots claiming one ref (repo +
     worktrees, the normal state of ~/dev) pick one and say so in the hold.
  6. Column validation, in its most conservative possible form: a name is an
     offender only when it appears NOWHERE in the resolved snapshot document
     (so a column of another table, or one named only in a drift note, always
     passes), and only when attribution is unambiguous — a qualified
     alias.column whose alias resolves to a snapshot table, or a bare name in
     a query matching SIMPLE_SELECT, a closed grammar covering exactly
     `select a, b from t [where a = 'x'] [limit n]`. The grammar replaced a
     token blacklist after two QA passes found four false-positive classes in
     the blacklist in one hour; a whitelist of shapes cannot drift that way.
  7. apply_migration on PostToolUse prints a "snapshot now stale" note and
     re-arms the once-per-session hold, citing the migration.
  8. Malformed payloads ALWAYS exit 0. A top-level JSON list, a non-string
     `query` and a non-string `cwd` all crashed v2 with AttributeError/TypeError,
     i.e. exit 1 — a hook that exits 1 is a hook that broke. Every field read
     off the payload is now type-checked before use. Never block on input that
     could not be parsed.

The bias, from the suite's header: FALSE NEGATIVES ARE ACCEPTABLE, FALSE
POSITIVES ARE NOT. Every rule here fails open on any parse uncertainty.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import datetime
import difflib
import glob
import json
import os
import re
import sys

SNAPSHOT_RELPATH = os.path.join("docs", "SCHEMA-PROD.md")
SNAPSHOT_MAX_STALE_DAYS = 7
HEADER_LINES = 20          # header region scanned for the project ref + date
PROBE_BYTES = 8192         # bytes read per candidate when probing that header

DEV_ROOT = os.environ.get("SQL_GUARD_DEV_ROOT") or os.path.expanduser("~/dev")
SETTINGS = os.environ.get("SQL_GUARD_SETTINGS") or os.path.expanduser(
    "~/.claude/settings.local.json")
STATE_DIR = os.environ.get("SQL_GUARD_STATE_DIR") or os.path.join(
    "/tmp", f"claude-sql-guard-{os.getuid()}")

# Words that are never a column reference. Only used to SUPPRESS blocking, so
# an omission here can cost a false positive — when in doubt, add the word.
SQL_NOISE = frozenset("""
select from where group by having order limit offset fetch first next rows row only
join left right full inner outer cross lateral natural on using as and or not
in is null true false unknown distinct all any some exists case when then else end
asc desc nulls last union intersect except with recursive materialized
insert into values update set delete returning conflict do nothing
array cast collate similar to like ilike between symmetric escape
current_date current_time current_timestamp localtime localtimestamp now
count sum avg min max coalesce nullif greatest least abs round length lower upper
explain analyze verbose costs settings buffers format begin commit rollback savepoint
table tablesample repeatable window partition over range groups preceding following
unbounded current filter within of share no wait skip locked for nowait ties key
at zone local isnull notnull epoch century millennium quarter dow doy
ctid xmin xmax cmin cmax tableoid
day hour minute second millisecond microsecond week month year decade timezone
text integer int int2 int4 int8 bigint smallint numeric decimal real float
double precision boolean bool date timestamp timestamptz time timetz interval
uuid json jsonb varchar character char bytea serial bigserial inet cidr macaddr
money xml tsvector tsquery point line lseg box path polygon circle citext vector
""".split())


# The ONLY query shape the bare-column scan will look at:
#   select [distinct] a, b from [public.]t [where a = 'x' and b > 3] [limit 5] [;]
# Literals are already collapsed to '' by strip_sql. No functions, casts,
# aliases, joins, commas after the table, subqueries, CTEs, ORDER BY, GROUP BY,
# locking clauses or operator keywords can appear: any of them and the query
# simply does not match, so nothing in it is validated as a column.
_NAME = r"[a-z_]\w*"
_PRED = (rf"{_NAME}\s*(?:=|<>|!=|<=|>=|<|>)\s*(?:''|\d+(?:\.\d+)?)")
SIMPLE_SELECT = re.compile(
    rf"^select\s+(?:distinct\s+)?(?P<cols>{_NAME}(?:\s*,\s*{_NAME})*)"
    rf"\s+from\s+(?P<tbl>[a-z_][\w.]*)"
    rf"(?:\s+where\s+(?P<pred>{_PRED}(?:\s+(?:and|or)\s+{_PRED})*))?"
    rf"(?:\s+limit\s+\d+)?\s*;?\s*$"
)


def strip_sql(q: str) -> str:
    """Remove string literals, dollar-quoted bodies, and comments so structural
    checks don't false-positive.

    Single left-to-right pass: strings/dollar-bodies/comments are consumed by ONE
    alternation, so a `--` inside a quoted region can never be eaten as a comment.
    (Sequential re.sub passes with comments first false-blocked legit single
    statements AND false-passed real multi-statement SQL — QA finding 2026-07-11.)
    """
    return re.sub(
        r"'(?:[^']|'')*'"  # standard string literal ('' = escaped quote)
        r'|"(?:[^"]|"")*"'  # double-quoted identifier / COLLATE "C" (QA 2026-09-19)
        r"|\$([A-Za-z_][A-Za-z0-9_]*|)\$.*?\$\1\$"  # dollar-quoted body, tag may have digits or be empty
        r"|--[^\n]*"  # line comment
        r"|/\*.*?\*/",  # block comment
        # strings/dollar-bodies collapse to a placeholder token; comments must
        # vanish entirely — replacing a trailing "-- comment" with '' made
        # "SELECT 1; -- done" look multi-statement (QA iteration-2 finding)
        lambda m: "" if m.group(0).startswith("--") or m.group(0).startswith("/*") else "''",
        q,
        flags=re.S,
    )


def neutralize_from_operators(s: str) -> str:
    """Blank keywords that look like a clause but are not: the FROM of IS [NOT]
    DISTINCT FROM and of EXTRACT/SUBSTRING/TRIM/OVERLAY/POSITION, and the UPDATE
    of the FOR UPDATE row-locking clause.

    Without this, `WHERE slug IS DISTINCT FROM created_at` and
    `trim(both ' ' FROM slug)` read "created_at"/"slug" as tables and block a
    perfectly legal query (the suite's alias/keyword group, 4 of its 13 cases).
    """
    s = re.sub(r"\bis\s+(?:not\s+)?distinct\s+from\b", " <> ", s)
    # FOR UPDATE / FOR SHARE is a row-locking clause; without this the UPDATE
    # pattern reads "SELECT ... FOR UPDATE SKIP LOCKED" as UPDATE of a table
    # named "skip" (QA 2026-09-19: 237 of 2370 real-schema queries, v2 and v3).
    s = re.sub(r"\bfor\s+(?:no\s+key\s+|key\s+)?(?:update|share)\b", " ", s)
    s = re.sub(
        r"\b(extract|substring|substr|trim|overlay|position)\s*\(([^()]*?)\bfrom\b",
        lambda m: f"{m.group(1)}({m.group(2)} ", s)
    return s


# ---------------------------------------------------------------- snapshots --

def settings_env() -> dict:
    """The `env` map from settings.local.json, used to resolve a $VAR ref."""
    try:
        with open(SETTINGS, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        env = data.get("env") if isinstance(data, dict) else None
        return {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {}
    except Exception:
        return {}


def declared_ref(header: str):
    """The project ref a snapshot's header declares, $VARs resolved. None if
    the header declares none (such a snapshot is never matched to a call)."""
    m = re.search(r"project\s+`([^`]+)`", header, re.I)
    if not m:
        return None
    ref = m.group(1).strip()
    if ref.startswith("$"):
        return settings_env().get(ref[1:].lstrip("{").rstrip("}")) or None
    return ref or None


def header_of(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "\n".join(f.read(PROBE_BYTES).splitlines()[:HEADER_LINES])
    except Exception:
        return ""


def snapshot_age_days(text: str):
    """Age in days from the first YYYY-MM-DD in the header lines; None if
    no parseable date (fail open — absence of a date never blocks)."""
    for line in text.splitlines()[:HEADER_LINES]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if m:
            try:
                gen = datetime.date.fromisoformat(m.group(1))
            except ValueError:
                continue
            return (datetime.date.today() - gen).days
    return None


def resolve_snapshot(project_id, cwd: str, raw_query: str):
    """Pick the snapshot for THIS call. Returns (path, others, reason) where
    `path` is None when nothing resolved, `others` are the also-claiming
    candidates, and `reason` is 'ok' | 'hint' | 'ambiguous' | 'unmatched'."""
    candidates = sorted(glob.glob(os.path.join(DEV_ROOT, "*", SNAPSHOT_RELPATH)))

    hint = re.search(r"--\s*schema-repo:\s*([\w.@-]+)", raw_query or "")
    if hint:
        want = os.path.join(DEV_ROOT, hint.group(1), SNAPSHOT_RELPATH)
        if want in candidates:
            return want, [], "hint"

    if not isinstance(project_id, str) or not project_id.strip():
        return None, [], "unmatched"

    matches = [p for p in candidates if declared_ref(header_of(p)) == project_id.strip()]
    if not matches:
        return None, [], "unmatched"
    if len(matches) == 1:
        return matches[0], [], "ok"

    # Several repos/worktrees hold a snapshot for one project — the normal state
    # of ~/dev. Prefer the one in the repo cwd is inside, else the freshest.
    here = os.path.abspath(cwd) if isinstance(cwd, str) and cwd else ""
    for p in matches:
        repo = os.path.dirname(os.path.dirname(p))
        if here == repo or here.startswith(repo + os.sep):
            return p, [m for m in matches if m != p], "ambiguous"
    ranked = sorted(matches, key=lambda p: (snapshot_age_days(header_of(p)) is None,
                                            snapshot_age_days(header_of(p)) or 0, p))
    return ranked[0], ranked[1:], "ambiguous"


def read_snapshot(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def snapshot_tables(text: str):
    """Table inventory from markdown headers (## table / ### table). Returns
    a set, or None when the format is unrecognized (fewer than 3 headers) —
    None means membership can't be judged, so validation is skipped."""
    tables = {
        m.group(1).lower()
        for m in re.finditer(r"^#{2,4}\s+`?([A-Za-z_][\w]*)`?\s*$", text, re.M)
    }
    return tables if len(tables) >= 3 else None


def snapshot_columns(text: str):
    """table -> set(column names), read from each section's markdown table.
    Used only to word the block message; membership decisions use
    snapshot_tokens (see validate_columns)."""
    out, cur = {}, None
    hdr = re.compile(r"^#{2,4}\s+`?([A-Za-z_][\w]*)`?\s*$")
    row = re.compile(r"^\|\s*`?([A-Za-z_]\w*)`?\s*\|")
    for line in text.splitlines():
        m = hdr.match(line)
        if m:
            cur = m.group(1).lower()
            out.setdefault(cur, set())
            continue
        if cur:
            r = row.match(line)
            if r and r.group(1).lower() not in ("column", "columns", "name"):
                out[cur].add(r.group(1).lower())
    return out


def snapshot_tokens(text: str):
    """EVERY word token in the snapshot, prose and drift notes included. A name
    found here is never an offender — that is deliberate: it makes a column of
    another table, a name mentioned only in a drift note, and anything the
    document merely talks about all pass. Maximum false negatives, minimum
    false positives."""
    return set(re.findall(r"[a-z_][a-z0-9_]*", text.lower()))


def snapshot_section(text: str, table: str) -> str:
    """The snapshot's section for `table` (up to 20 lines), or ''. Best effort."""
    lines = text.splitlines()
    start = None
    header = re.compile(r"^#{2,4}\s+`?" + re.escape(table) + r"`?\s*$", re.I)
    any_header = re.compile(r"^#{2,4}\s+\S")
    for i, line in enumerate(lines):
        if header.match(line):
            start = i
            break
    if start is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1:start + 21]:
        if any_header.match(line):
            break
        out.append(line)
    return "\n".join(out).strip()


# ------------------------------------------------------------ query reading --

def cte_names(s: str):
    """Names bound by a WITH clause, including `x (a, b) AS (` and
    `x AS MATERIALIZED (`. A CTE is never validated as a table."""
    names = set()
    for m in re.finditer(r"(?:\bwith\s+(?:recursive\s+)?|,\s*)"
                         r"([a-z_]\w*)\s*(?:\([^()]*\)\s*)?as\s+(?:not\s+)?"
                         r"(?:materialized\s+)?\(", s):
        names.add(m.group(1))
    return names


def extract_tables(stripped: str):
    """Physical tables referenced by the query, lowercased, schema prefix
    dropped. CTE names and set-returning function calls are excluded.
    Deliberately dumb; anything it can't see simply isn't validated."""
    s = neutralize_from_operators(stripped.lower())
    ctes = cte_names(s)
    refs = set()
    for pat in (
        # \b before the lookahead prevents backtracking one char to defeat it
        # (without it, "unnest(" matched as table "unnes" — caught in testing).
        # LATERAL/ONLY are consumed as optional keywords so "JOIN LATERAL fn(...)"
        # validates fn (excluded by the paren lookahead), not the keyword itself
        # (QA 2026-07-19: 'lateral'/'only' were captured as phantom tables).
        r"\b(?:from|join)\s+(?:lateral\s+|only\s+)?([a-z_][\w.]*)\b(?!\s*\()",
        r"\bupdate\s+(?:only\s+)?([a-z_][\w.]*)",
        r"\binsert\s+into\s+([a-z_][\w.]*)",
        r"\bdelete\s+from\s+(?:only\s+)?([a-z_][\w.]*)",
    ):
        refs |= set(re.findall(pat, s))
    refs -= {"lateral", "only"}  # belt-and-braces: never validate SQL keywords
    out = set()
    for r in refs:
        parts = r.split(".")
        name = parts[-1]
        # The snapshot covers the `public` schema only, so auth.users /
        # storage.objects / cron.job are not absences — they are out of scope,
        # and "refresh the snapshot" could never resolve them (QA 2026-09-19).
        if len(parts) > 1 and parts[-2] not in ("public", ""):
            continue
        if name and name not in ctes:
            out.add(name)
    return out


def alias_map(stripped: str, known):
    """alias/table name -> snapshot table. Only tables present in the snapshot
    are mapped, so an alias of a CTE or a function call resolves to nothing and
    its columns are never validated."""
    s = neutralize_from_operators(stripped.lower())
    ctes = cte_names(s)
    out = {}
    for m in re.finditer(r"\b(?:from|join|update|into)\s+(?:lateral\s+|only\s+)?"
                         r"([a-z_][\w.]*)\b(?!\s*\()\s*(?:as\s+)?([a-z_]\w*)?", s):
        tbl = m.group(1).split(".")[-1]
        if tbl in ctes or tbl not in known:
            continue
        out[tbl] = tbl
        alias = m.group(2)
        if alias and alias not in SQL_NOISE and alias not in ctes:
            out[alias] = tbl
    return out


def validate_columns(stripped: str, known, columns, tokens):
    """[(name, table)] for names this query attributes to a snapshot table and
    that appear NOWHERE in the snapshot. Empty on any uncertainty."""
    s = neutralize_from_operators(stripped.lower())
    ctes = cte_names(s)
    amap = alias_map(stripped, known)
    offenders = []

    # qualified: alias.column, where the alias resolves to a snapshot table
    for m in re.finditer(r"(?<![\w.])([a-z_]\w*)\.([a-z_]\w*)\b", s):
        qual, col = m.group(1), m.group(2)
        tbl = amap.get(qual)
        if not tbl or qual in ctes:
            continue
        if col in SQL_NOISE or col in tokens:
            continue
        offenders.append((col, tbl))

    # bare: ONLY when the whole query matches SIMPLE_SELECT — a closed grammar
    # (see its definition) that a query must match end to end to be scanned.
    #
    # This is deliberately a whitelist of query SHAPES, not a blacklist of
    # tokens. The blacklist version shipped on 2026-09-19 and two independent
    # QA passes found four distinct false-positive classes in it within the
    # hour: `AT TIME ZONE`/`ISNULL`/`COLLATE "C"` (unknown keywords), the alias
    # of a JOINed non-public table read as a column of the public one, the
    # second alias of a comma join, and the `E` of an E'...' escape string.
    # Each fix was another token or shape added to the blacklist, which is the
    # signature of an unbounded surface. A grammar cannot drift that way: a
    # query either matches these few productions or is never scanned at all.
    if not offenders and not ctes:
        m = SIMPLE_SELECT.match(s.strip())
        if m:
            tbl = m.group("tbl").split(".")[-1]
            schema = m.group("tbl").split(".")[-2] if "." in m.group("tbl") else ""
            if tbl in known and schema in ("", "public"):
                names = [n.strip() for n in m.group("cols").split(",")]
                names += re.findall(r"(?:^|\band\b|\bor\b)\s*([a-z_]\w*)\s*(?:=|<|>|!)",
                                    m.group("pred") or "")
                for name in names:
                    if name in SQL_NOISE or name in amap or name in tokens or name == tbl:
                        continue
                    offenders.append((name, tbl))

    seen, out = set(), []
    for name, tbl in offenders:
        if name not in seen:
            seen.add(name)
            out.append((name, tbl))
    return out


# ----------------------------------------------------------------- session --

def session_paths(session_id):
    name = re.sub(r"[^A-Za-z0-9_-]", "_", str(session_id or "nosession"))[:120] or "nosession"
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except Exception:
        return None, None
    return os.path.join(STATE_DIR, name), os.path.join(STATE_DIR, name + ".migration")


def write_quiet(path, text):
    if not path:
        return
    try:
        with open(path, "w") as f:
            f.write(text)
    except Exception:
        pass


def remove_quiet(path):
    if not path:
        return
    try:
        os.remove(path)
    except Exception:
        pass


def read_quiet(path):
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except Exception:
        return ""


def handle_apply_migration(data) -> None:
    """PostToolUse on apply_migration: note the snapshot is now behind prod and
    re-arm the once-per-session hold so the next data query cites it."""
    tool_input = data.get("tool_input")
    name = ""
    if isinstance(tool_input, dict):
        raw = tool_input.get("name") or tool_input.get("migration_name") or ""
        name = raw if isinstance(raw, str) else ""
    label = name or "(unnamed migration)"
    marker, migfile = session_paths(data.get("session_id"))
    write_quiet(migfile, label)
    remove_quiet(marker)
    print(
        f"SNAPSHOT NOW STALE (sql-guard): migration `{label}` was just applied, so "
        f"{SNAPSHOT_RELPATH} no longer matches prod. Refresh it with /schema-snapshot "
        "before relying on it. The next execute_sql in this session is held once as "
        "a reminder."
    )
    sys.exit(0)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)
    if not isinstance(data, dict):
        sys.exit(0)

    tool = data.get("tool_name")
    if tool == "mcp__supabase__apply_migration":
        if data.get("hook_event_name") == "PostToolUse":
            handle_apply_migration(data)
        sys.exit(0)
    if tool != "mcp__supabase__execute_sql":
        sys.exit(0)

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        sys.exit(0)
    query = tool_input.get("query")
    if not isinstance(query, str) or not query.strip():
        sys.exit(0)

    stripped = strip_sql(query)

    # --- Rule 1: multi-statement block (always) ---
    if re.search(r";\s*\S", stripped):
        print(
            "BLOCKED (sql-guard): multi-statement SQL — execute_sql returns only "
            "the LAST statement's result; earlier statements' output is silently "
            "lost. Split into one execute_sql call per statement.",
            file=sys.stderr,
        )
        sys.exit(2)

    marker, migfile = session_paths(data.get("session_id"))

    if re.search(
        # any pg_* relation, not a fixed list — pg_stat_activity, pg_roles,
        # pg_extension and pg_trigger were all missing from it (QA 2026-09-19)
        r"\b(information_schema|pg_[a-z_]+)\b",
        stripped, re.I,
    ):
        # Schema was consulted — satisfies the check for the rest of the session.
        write_quiet(marker, "schema-consulted\n")
        remove_quiet(migfile)
        sys.exit(0)

    cwd = data.get("cwd")
    path, others, reason = resolve_snapshot(
        tool_input.get("project_id"), cwd if isinstance(cwd, str) else "", query)
    text = read_snapshot(path) if path else ""
    age = snapshot_age_days(text) if text else None
    migration = read_quiet(migfile)

    # --- Rule 2: schema-first, one-time hold per session ---
    if not marker or not os.path.exists(marker):
        write_quiet(marker, "warned\n")
        remove_quiet(migfile)
        notes = []
        if migration:
            notes.append(
                f"A migration was applied in this session (`{migration}`), so the "
                "snapshot is behind prod until /schema-snapshot is re-run.")
        if reason == "unmatched":
            notes.append(
                f"No snapshot under {DEV_ROOT} declares project ref "
                f"{tool_input.get('project_id')!r}, so table and column validation "
                "is OFF for this project. Add docs/SCHEMA-PROD.md to its repo "
                "(/schema-snapshot) to turn it on.")
        else:
            aged = f", {age} days old" if age is not None else ""
            notes.append(f"Snapshot: {path}{aged}.")
            if reason == "ambiguous" and others:
                notes.append("Several snapshots declare this project ref — using the "
                             "one above; the others are " + ", ".join(others) + ".")
            if age is not None and age > SNAPSHOT_MAX_STALE_DAYS:
                notes.append(
                    f"That is STALE (>{SNAPSHOT_MAX_STALE_DAYS}d) — a stale snapshot "
                    "caused wrong-column guesses in a recent session. Run "
                    "/schema-snapshot to refresh it.")
        print(
            "HOLD (sql-guard, fires once per session): schema-first rule.\n"
            + "\n".join(f"- {n}" for n in notes)
            + "\nConfirm the schema for the tables you are about to touch: read the "
            "snapshot above, or run an information_schema.columns query (catalog "
            "queries always pass this guard). Guessed column names cost retries in "
            "10+ recent sessions.\nRe-run this exact query after checking; this guard "
            "will not fire again this session.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not text:
        sys.exit(0)
    known = snapshot_tables(text)
    if not known:
        sys.exit(0)

    # --- Rule 3: per-query table validation ---
    columns = snapshot_columns(text)
    tokens = snapshot_tokens(text)
    unknown = [t for t in sorted(extract_tables(stripped))
               if t not in known and t not in tokens]
    if unknown:
        msgs = []
        for t in unknown:
            close = difflib.get_close_matches(t, known, n=3, cutoff=0.6)
            section = snapshot_section(text, close[0]) if close else ""
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            msgs.append(f"- '{t}' is not in {path}.{hint}")
            if section:
                msgs.append(f"  Closest match's snapshot section:\n{section}")
        print(
            "BLOCKED (sql-guard v2): query references table(s) missing from "
            "the schema snapshot:\n" + "\n".join(msgs) + "\n"
            "If the table genuinely exists (snapshot drift), refresh via "
            "/schema-snapshot or verify with information_schema.columns "
            "(catalog queries always pass this guard).",
            file=sys.stderr,
        )
        sys.exit(2)

    # --- Rule 4 (v3): per-query column validation ---
    bad = validate_columns(stripped, known, columns, tokens)
    if bad:
        msgs = []
        for name, tbl in bad:
            real = sorted(columns.get(tbl) or ())
            close = difflib.get_close_matches(name, real, n=3, cutoff=0.6)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            msgs.append(f"- '{name}' appears nowhere in {path}.{hint}")
            if real:
                msgs.append(f"  {tbl} columns per the snapshot: {', '.join(real)}")
        print(
            "BLOCKED (sql-guard v3): query references column(s) that appear nowhere "
            "in the schema snapshot:\n" + "\n".join(msgs) + "\n"
            "If the column genuinely exists (snapshot drift), refresh via "
            "/schema-snapshot or verify with information_schema.columns "
            "(catalog queries always pass this guard).",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
