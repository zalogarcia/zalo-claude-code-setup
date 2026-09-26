#!/usr/bin/env python3
r"""PreToolUse guard: social media page loads must go through the pacing gate.

Why this exists
---------------
2026-09-26. A background worker looking for Facebook owners ran

    node cdp-read.mjs https://www.facebook.com/<someone>

about 631 times against the Blueprint Chrome on port 9222 (the GoHighLevel
browser), 556 of them onto a login wall, from this Mac's IP, where Zalo's real
Facebook, LinkedIn and Instagram accounts are logged in. Nothing paced it.
Zalo: "we cannot have hundreds of stuff, you know, pages and traffic from social
media, as we might get banned easily because it's not human-like."

The pacing itself lives in ~/.claude/scripts/social-gate.py (one budget for the
whole machine, per platform, file locked, ledger backed). This hook makes the
tool calls an agent actually makes go through it.

What it does
------------
Browser tools (Playwright MCP, a Chrome MCP, WebFetch):
  * a navigation to a social URL takes a slot from the gate at the moment of the
    call (acquire with no wait), or uses a slot an earlier
    `social-gate.py acquire --grant` reserved. If neither is available it is
    BLOCKED, and the message names the wait and the caps. Checking without
    taking the slot would let every call through one at a time, which is the
    bulk load this exists to stop, so the check and the reservation are one step.
  * page code (browser_run_code, browser_evaluate) that navigates to a social
    host counts as one load; code that navigates more than once, names several
    social URLs, loops, reduces, recurses or sets timers is blocked as bulk.

Bash, deny by default. A command is a social LOAD when a fetch or browse
primitive meets a social host:
  * curl, wget, httpie, yt-dlp and friends, open, a headless Chrome, the
    playwright or puppeteer CLIs, whose TARGET host is social (a Google search
    whose query names facebook.com is not a load; the target host decides);
  * a python / node / osascript / expect one liner, or a heredoc fed to an
    interpreter, that holds a full social URL, or a social host plus a fetch
    primitive;
  * a script file (the file, its local imports one level down, and any data
    files on the command line) that has a fetch or browser primitive and a
    social URL literal in the same file, or is handed social URLs, unless it
    calls the gate itself; an interpreter handed a social URL for a script this
    hook cannot read also counts;
  * a curl to a remote renderer (Cloudflare Browser Rendering and the other
    hosts in the config) whose payload names a social host: route remote;
  * a fetch whose URL comes from a variable, a substitution, a URL list, a
    heredoc or stdin, when the command or the files it reads name a social host;
  * work handed to tmux, screen, open (a script file) or expect;
  * a function or alias defined in the command and called with a social URL,
    or an unknown program handed a full social URL.
A LOAD passes only when it is paired, in the same command, as

    python3 ~/.claude/scripts/social-gate.py acquire --url <u> --actor <a> [--route r] && <ONE load of that platform>

(the real gate path, `&&` directly between them, same platform and route, one
social URL), or when it is the only load in the command and a grant is waiting.
Always blocked, gated or not:
  * port 9222 (or the Blueprint profile dir) in an executing part of the command
    (a fetch, an interpreter, a script, an executed heredoc) together with a
    social host: the GHL browser never loads one;
  * an unpaired load inside a loop, xargs, parallel, watch or find -exec;
  * one load naming several social URLs (repeats included), curl URL globbing,
    recursive wget, a script whose own code loads social URLs without the gate,
    a script fed a file of social URLs;
  * a crontab, at, batch or launchctl entry whose command would load a social
    page (given inline, or as a file: a launchd plist, `at -f job`, `batch <
    job`), and a heredoc that writes an unpaced social loader to disk;
  * a fetch inside a loop whose target host is computed at run time;
  * a data file too large to scan (over 64 MB) handed to a fetcher, loop or
    script: presumed to be a URL list;
  * any write, move or delete of the gate's own ledger, state or config
    (~/.claude/state/social-*, ~/.claude/config/social-pacing.json), from Bash
    or from Write / Edit / MultiEdit: those files ARE the budget, and Zalo
    changes them in his own terminal.
Normalised first: fullwidth letters, ideographic and percent encoded dots,
userinfo (https://u@facebook.com), quote splicing, line continuations, variables
assigned in the same command, aliases, `cd`, bash -c / eval one level down, a
quoted command or a fetch tail handed to any other program (docker run, ssh, su,
arch, script), wrappers with their value options (env -S, nohup, nice -n,
timeout -s, npx, xargs...), a redirector followed with -L (google.com/url?q=<a
social URL>). The bridge's schedule.mjs is not a scheduler here on purpose: its
--run entries execute through Claude or Codex, where this hook runs again at
fire time.

LIMITS, stated plainly
----------------------
  * A script that reads its URLs from a file it opens itself, with no social
    host in its code or on its command line, is invisible here. So are npm
    scripts, `python3 -m module`, base64 or eval of a computed string, a URL
    assembled at runtime outside a loop, a click on a link whose text carries no
    URL, a script that deletes the ledger from inside its own code, and a command
    run on a remote host over ssh that only names a variable. A gate call inside
    the tool itself (the bu-cold-outreach owner resolver and evidence miner have
    one since 2026-09-26; Jev's lane does not yet) and the Chrome History audit
    (~/.claude/scripts/social-load-audit.py) are the layers for those.
  * Astra's Computer Use clicks in Codex are not tool calls this hook sees. The
    audit counts them; the bu-cold-outreach skill tells Astra to call the gate.
  * An offline test file (tests/, test_*, *.test.*, *.spec.*, without live, real,
    prod or e2e in its name) is judged on its command line and data files only,
    because its own code names social URLs as fixtures. A script that merely
    mentions "social-gate" counts as self pacing. A worker who renames a loader
    or writes that comment to get past this guard has lied in a diff; the audit
    still counts the browser loads.
There is no in-band override and no environment switch. If a load is refused,
wait for the time printed, or stop; do not rewrite the command to get around it.

Exit 0 = allow. Exit 2 = block (stderr is shown to the agent).
"""

import importlib.util
import json
import os
import re
import shlex
import shutil
import sys
import unicodedata
from urllib.parse import unquote

HOME = os.path.expanduser("~")
GATE_PATH = os.path.join(HOME, ".claude", "scripts", "social-gate.py")
CONFIG_PATH = os.path.join(HOME, ".claude", "config", "social-pacing.json")
GATE_CMD = "python3 ~/.claude/scripts/social-gate.py"
CLAUDE_JSON = os.path.join(HOME, ".claude.json")

# The guard's own files name social hosts, fetch words and 9222 on purpose.
EXEMPT = {os.path.realpath(os.path.join(HOME, ".claude", p)) for p in (
    "scripts/social-gate.py", "scripts/social-gate.test.py",
    "hooks/social-pace-guard.py", "hooks/social-pace-guard.test.py",
    "scripts/social-load-audit.py", "scripts/social-load-audit.test.py")}

DEFAULT_HOSTS = {  # used only when the config cannot be read (then every load is refused)
    "facebook": ["facebook.com", "fb.com", "fb.me", "fb.watch", "messenger.com"],
    "instagram": ["instagram.com", "instagr.am"], "linkedin": ["linkedin.com", "lnkd.in"],
    "x": ["x.com", "twitter.com"], "tiktok": ["tiktok.com"],
    "threads": ["threads.net", "threads.com"]}

SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
INTERPRETERS = SHELLS | {"python", "python3", "python2", "node", "nodejs", "deno", "bun",
                         "ruby", "perl", "php", "osascript", "tsx", "ts-node", "pypy3",
                         "expect"}
FETCH_TOOLS = {"curl", "curlie", "wget", "wget2", "http", "https", "httpie", "xh", "hurl",
               "aria2c", "lynx", "w3m", "links", "elinks", "yt-dlp", "youtube-dl",
               "gallery-dl", "instaloader", "snscrape", "open", "chromium",
               "chromium-browser", "chrome", "google-chrome", "google chrome",
               "google-chrome-stable", "chrome-headless-shell", "headless_shell",
               "playwright", "puppeteer", "shot-scraper", "wkhtmltopdf", "wkhtmltoimage",
               "agent-browser", "safaridriver", "firefox", "brave", "microsoft edge",
               "httpx", "monolith", "single-file", "lighthouse", "xidel"}
PLAIN_HTTP = {"curl", "curlie", "wget", "wget2", "http", "https", "httpie", "xh"}
WRAPPERS = {"env", "sudo", "nohup", "command", "exec", "time", "caffeinate", "stdbuf",
            "setsid", "timeout", "gtimeout", "nice", "unbuffer", "npx", "bunx", "pnpx",
            "doas", "builtin", "noglob", "then", "else", "do", "!", "{", "}", "if", "elif",
            "while", "until"}
WRAPPER_VALUE_OPTS = {"nice": {"-n"}, "timeout": {"-s", "-k", "--signal", "--kill-after"},
                      "gtimeout": {"-s", "-k", "--signal", "--kill-after"},
                      "sudo": {"-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D"},
                      "doas": {"-u", "-C"}, "caffeinate": {"-t", "-w"},
                      "env": {"-u", "--unset", "-C", "--chdir", "-P"},
                      "stdbuf": {"-i", "-o", "-e"}}
LOOP_HEADS = {"for", "while", "until", "select", "xargs", "parallel", "watch", "repeat",
              "foreach"}
SAFE_HEADS = {"echo", "printf", "print", "cat", "head", "tail", "grep", "egrep", "fgrep",
              "rg", "ag", "sed", "awk", "gawk", "jq", "yq", "sort", "uniq", "wc", "cut",
              "tr", "tee", "ls", "git", "gh", "sqlite3", "test", "[", "[[", "true", "false",
              "column", "diff", "comm", "paste", "mkdir", "touch", "cp", "mv", "rm", "ln",
              "chmod", "stat", "file", "cd", "pushd", "popd", "pwd", "export", "set",
              "unset", "date", "sleep", "wait", "read", "local", "declare", "readonly",
              "return", "exit", "less", "more", "basename", "dirname", "realpath", "xxd",
              "od", "base64", "shasum", "md5", "pbcopy", "pbpaste", "say", "alias",
              "unalias", "type", "which", "whence", "trap", "shift", "nl",
              "fold", "fmt", "rev", "expand", "strings", "iconv", "mktemp", "du", "df",
              "ps", "pgrep", "brctl", "code", "vim", "nano", "gzip", "gunzip", "zip",
              "unzip", "tar", "defaults", "plutil", "mdls", "mdfind", "htmlq", "pup",
              "xmllint", "hxselect", "mlr", "csvcut", "csvgrep", "xsv", "qsv", "duckdb",
              "find", "fd", "tree", "done", "fi", "esac", "in", "case", "then", "else"}
SCHEDULERS = {"crontab", "at", "batch", "launchctl"}
HANDOFF_HEADS = {"tmux", "screen"}
CURL_VALUE_FLAGS = {"-d", "--data", "--data-raw", "--data-binary", "--data-ascii",
                    "--data-urlencode", "--json", "-F", "--form", "--form-string", "-H",
                    "--header", "-e", "--referer", "-A", "--user-agent", "-b", "--cookie",
                    "-u", "--user", "-w", "--write-out", "-x", "--proxy", "--resolve",
                    "--connect-to", "-T", "--upload-file", "--max-time", "-m", "--retry",
                    "-X", "--request", "--max-redirs", "-r", "--range", "--limit-rate", "-Y",
                    "-y", "-z", "--time-cond", "--cacert", "--cert", "--key", "-E",
                    "--connect-timeout", "-U", "--proxy-user", "--interface", "--local-port",
                    "--dns-servers", "--variable", "--retry-delay", "--retry-max-time"}
OUTPUT_FLAGS = {"-o", "--output", "-D", "--dump-header", "-c", "--cookie-jar", "--output-dir",
                "-O", "--trace", "--trace-ascii", "--stderr", "--etag-save", "--hsts",
                "--alt-svc", "--libcurl"}
CURL_CONFIG_FLAGS = {"-K", "--config"}
WGET_BULK_FLAGS = {"-r", "--recursive", "-m", "--mirror", "-i", "--input-file", "-l",
                   "--level", "-p", "--page-requisites", "--spider"}
XARGS_VALUE_FLAGS = {"-n", "-P", "-I", "-L", "-s", "-a", "-E", "-d", "-J", "-R", "-S", "-j",
                     "--jobs", "--max-args", "--max-procs"}
INTERP_VALUE_OPTS = {"-W", "-X", "-Q", "--require", "--loader", "--import",
                     "--env-file", "--conditions", "-C", "--title", "--config", "--cwd",
                     "--inspect-port", "--input-type", "--experimental-loader"}
SCRIPT_EXTS = (".sh", ".bash", ".zsh", ".command", ".tool", ".py", ".mjs", ".cjs", ".js",
               ".ts", ".rb", ".pl", ".php", ".exp", ".applescript", ".scpt")

BLUEPRINT_RE = re.compile(
    r"(?:[:=]|port[\s=:\"']*|\s-p\s+|\bcdp[\s=:\"']*)9222(?![0-9])|9222/(?:json|devtools)"
    r"|blueprint-chrome-profile", re.IGNORECASE)
GATE_REF_RE = re.compile(r"social[-_]gate", re.IGNORECASE)
FETCH_CODE_RE = re.compile(
    r"\bcurl\b|\bwget\b|urlopen|urllib\.request|urllib3|\brequests\s*\.\s*(?:get|post|head|"
    r"request|Session)|\bhttpx\b|\baiohttp\b|http\.client|\bfetch\s*\(|\baxios\b|\bgot\s*\("
    r"|\bundici\b|node-fetch|XMLHttpRequest|\bplaywright\b|\bpuppeteer\b|\bselenium\b"
    r"|webdriver|\bchromium\b|\.goto\s*\(|Page\.navigate|connectOverCDP|chrome-remote-"
    r"interface|remote-debugging|WebSocket\s*\(|\bwebbrowser\b|\bopen\s+-a\b"
    r"|osascript|yt[-_]dlp|youtube[-_]dl|gallery[-_]dl|instaloader|snscrape"
    r"|browser-rendering|Browser Rendering|\bhttps?\.get\s*\(|\bhttps?\.request\s*\("
    r"|open location|window\.open|location\.(?:href|assign|replace)|\bspawn\b", re.IGNORECASE)
NAV_CALL_RE = re.compile(
    r"\.goto\s*\(|location(?:\.href)?\s*=(?!=)|location\.(?:assign|replace)\s*\("
    r"|window\.open\s*\(|\bfetch\s*\(|navigate\s*\(|newPage|XMLHttpRequest|\.click\s*\("
    r"|\.src\s*=(?!=)|setContent\s*\(|setAttribute\s*\(\s*['\"](?:src|href|action)['\"]"
    r"|innerHTML\s*=|outerHTML\s*=|insertAdjacentHTML|document\.write"
    r"|\.submit\s*\(|sendBeacon|importScripts|\.reload\s*\(", re.IGNORECASE)
# One liners: a fetch primitive, or anything that spawns a process or opens a URL
ONELINER_FETCH_RE = re.compile(
    FETCH_CODE_RE.pattern + r"|subprocess|child_process|\bexec\w*\s*\(|\bsystem\s*\(|Popen"
    r"|\bspawnSync\b|\bopen\s+location\b|\bdo shell script\b|\bspawn\s", re.IGNORECASE)
SOCIAL_TOOLS = {"instaloader": "instagram", "instagram-scraper": "instagram",
                "instagram_scraper": "instagram", "snscrape": "x", "twint": "x",
                "facebook-scraper": "facebook", "facebook_scraper": "facebook",
                "tiktok-scraper": "tiktok", "tiktok_scraper": "tiktok", "tiktokapi": "tiktok",
                "linkedin-scraper": "linkedin", "linkedin_scraper": "linkedin",
                "linkedin_api": "linkedin", "twscrape": "x", "gallery-dl": None}
CODE_LOOP_RE = re.compile(
    r"\bfor\s*\(|\bfor\s+\w+\s+(?:of|in)\b|\bwhile\b|\.forEach\s*\(|\.map\s*\(|\.reduce\s*\("
    r"|Promise\.all|\bfor\s+\w+\s*,|\bfor\s+await\b|setInterval|setTimeout|\bArray\.from\b"
    r"|\brepeat\b|\bfunction\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?"
    r"(?:function\b|\([^)]*\)\s*=>|\w+\s*=>)", re.IGNORECASE)
TEST_FILE_RE = re.compile(r"(?:^|/)(?:tests?|__tests__|spec)/|(?:^|/)test_[^/]*$|_test\.[a-z]+$"
                          r"|\.(?:test|spec)\.[a-z]+$")
LIVE_TEST_RE = re.compile(r"live|real|prod|e2e", re.IGNORECASE)
THIRD_PARTY_RE = re.compile(r"/(?:node_modules|site-packages|dist-packages|\.venv|venv|\.npm|"
                            r"\.nvm|\.bun|\.cargo|\.cache|Library|\.local|\.pyenv|\.rbenv)/")
HEREDOC_OPEN_RE = re.compile(r"^<<-?$")
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::?[-=+?][^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*)")
REDIR_RE = re.compile(r"\d*[<>]+[&|]?|&[<>]+")
PREFILTER_RE = re.compile(
    r"\$|<<|(?:^|[\s;&|(`'\"])(?:\S*/)?(?:%s)(?:$|[\s;&|)`'\"])|(?:^|[\s;&|(])[.~]{0,2}/\S"
    % "|".join(re.escape(w) for w in sorted(
        (FETCH_TOOLS | INTERPRETERS | LOOP_HEADS | SCHEDULERS | HANDOFF_HEADS | {"eval"})
        - {"google chrome", "microsoft edge"})), re.IGNORECASE)
PUNCT = "();<>|&\n"
# The host scan is linear (about 0.1 s a MB), so a data file is read whole up to
# MAX_FILE; from there to MAX_BIG only its lines that name a social host are kept;
# anything larger, or a set of files past MAX_SCAN, is presumed to be a URL list and
# refused when a fetcher, loop or script is handed it. The old 2 MB / 200 KB caps
# made big URL lists invisible (QA round 3).
MAX_FILE = 8 * 1024 * 1024
MAX_BIG = 64 * 1024 * 1024
MAX_SCAN = 24 * 1024 * 1024  # characters of any one text scanned for hosts
TOO_BIG = "https://www.facebook.com/__data_too_large_to_scan__"


def normalize(text):
    """The same normalisation as social-gate.normalize, plus userinfo removal:
    fullwidth letters (NFKC), ideographic / fullwidth / percent encoded dots, and
    `://user@` dropped, so https://u@facebook.com reads as facebook.com."""
    text = text or ""
    if len(text) > MAX_SCAN:  # too long to scan: presumed to hide social URLs
        text = text[:MAX_SCAN] + "\n" + TOO_BIG + "\n" + TOO_BIG
    s = unicodedata.normalize("NFKC", text)
    for ch in "。．｡":
        s = s.replace(ch, ".")
    s = re.sub(r"%2e", ".", s, flags=re.IGNORECASE)
    return re.sub(r"(://)[^/\s@\"'<>`]{0,256}@", r"\1", s).lower()


# --------------------------------------------------------------------------
# context: config, host matching, the gate (loaded lazily)
# --------------------------------------------------------------------------

class Ctx:
    """Everything one decision needs. Tests pass a Gate built on a temp dir."""

    def __init__(self, gate=None, cwd=None, claude_json=CLAUDE_JSON):
        self._gate = gate
        self.cwd = cwd or os.getcwd()
        self.claude_json = claude_json
        self.cfg_error = None
        path = gate.config_path if gate is not None else CONFIG_PATH
        try:
            with open(path) as fh:
                self.cfg = json.load(fh)
            if not isinstance(self.cfg.get("platforms"), dict):
                raise ValueError("no platforms")
        except (OSError, ValueError, AttributeError) as e:
            self.cfg = None
            self.cfg_error = "cannot read %s: %s" % (path, e)
        plats = (self.cfg or {}).get("platforms") or DEFAULT_HOSTS
        self.suffixes = sorted(((d.lower().strip("."), p) for p, ds in plats.items()
                                for d in ds), key=lambda x: -len(x[0]))
        # The core domains only: linear. The subdomain labels are walked by hand in
        # _hosts(), because `(?:[a-z0-9-]+\.)*` backtracks quadratically on a long
        # dotted token (QA round 1: 16k chars took 18 s against a 15 s hook timeout).
        self.core_rx = re.compile(r"(?:%s)(?![a-z0-9\-]|\.[a-z0-9])"
                                  % "|".join(re.escape(d) for d, _ in self.suffixes))
        self.renderers = [h.lower() for h in ((self.cfg or {}).get("remote_renderers") or [])]
        self.api_hosts = [h.lower().strip(".") for h in
                          (((self.cfg or {}).get("not_page_hosts") or {}).get("hosts") or [])]

    @property
    def gate(self):
        if self._gate is None:
            spec = importlib.util.spec_from_file_location("social_gate_for_hook", GATE_PATH)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._gate = mod.Gate(lock_timeout_s=5.0)
        return self._gate

    def platform_of(self, host):
        """Same rule as social-gate.platform_of_host: API hosts are not pages."""
        host = (host or "").lower().rstrip(".")
        if any(host == h or host.endswith("." + h) for h in self.api_hosts):
            return None
        for d, p in self.suffixes:
            if host == d or host.endswith("." + d):
                return p
        return None

    def _hosts(self, text):
        """[host] of every social-suffixed host in NORMALISED text."""
        out = []
        for m in self.core_rx.finditer(text):
            s = j = m.start()
            if s > 0 and text[s - 1] != ".":
                if re.match(r"[a-z0-9\-@]", text[s - 1]):
                    continue
            else:
                while j > 0 and re.match(r"[a-z0-9.\-]", text[j - 1]) and s - j < 256:
                    j -= 1
                if j > 0 and text[j - 1] == "@":
                    continue  # an email address, not a page
            out.append(text[j:m.end()].lstrip(".-"))
        return out

    def socials(self, text):
        """[(platform, host)] for every social host named in text, in order."""
        out = []
        for host in self._hosts(normalize(text)):
            p = self.platform_of(host)
            if p:
                out.append((p, host))
        return out

    def url_literals(self, text):
        """[(platform, host)] for full URL literals only: https://host..., plain or
        JSON escaped. What a script would actually load, not a domain in a list."""
        out = []
        for m in re.finditer(r"https?:(?://|\\/\\/)([a-z0-9.\-]{1,253})", normalize(text)):
            p = self.platform_of(m.group(1))
            if p:
                out.append((p, m.group(1)))
        return out

    def social_urls(self, text):
        """Every social URL or bare host occurrence in text, repeats KEPT, so that
        `curl FB FB FB` is three loads, not one."""
        out = []
        for tok in re.split(r"[\s\"'<>`,\[\]{}()]+", normalize(text)):
            if not tok or len(tok) > 4096:
                continue
            if any(self.platform_of(h) for h in self._hosts(tok)):
                out.append(tok.split("#")[0].rstrip(".,;"))
        return out

    def is_renderer(self, host):
        host = (host or "").lower()
        return any(host == r or host.endswith("." + r) for r in self.renderers)


class Deny(Exception):
    pass


def url_host(tok):
    """Host of a URL-ish token, normalised; '' when the token is not URL shaped."""
    s = normalize(tok).strip().strip("\"'")
    if "://" not in s:
        if not re.match(r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}(?:[/:?#]|$)", s):
            return ""
        s = "https://" + s
    m = re.match(r"^[a-z][a-z0-9+.\-]*://([^/?#\s:]+)", s)
    return m.group(1).rstrip(".") if m else ""


# --------------------------------------------------------------------------
# shell parsing
# --------------------------------------------------------------------------

def tokenize(text):
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lex.whitespace_split = True
    lex.whitespace = " \t\r"
    return list(lex)


def is_op(tok):
    """A command separator. Redirections (>, >>, 2>&1's >&, &>, <<<) are not."""
    if not tok or not all(c in PUNCT for c in tok):
        return False
    return not REDIR_RE.fullmatch(tok)


def op_kind(tok):
    if "&&" in tok:
        return "&&"
    if "||" in tok:
        return "||"
    if "|" in tok:
        return "|"
    return ";"


def split_segments(tokens):
    """[[segment tokens, operator that FOLLOWS it]]."""
    out, cur = [], []
    for t in tokens:
        if is_op(t):
            if cur:
                out.append([cur, op_kind(t)])
                cur = []
            elif out and op_kind(t) != ";":
                out[-1][1] = op_kind(t)
        else:
            cur.append(t)
    if cur:
        out.append([cur, ";"])
    return out


def heredoc_openers(line):
    """Delimiters of heredocs opened on this line, OUTSIDE quotes only."""
    try:
        toks = tokenize(line)
    except ValueError:
        return []
    out = []
    for i, t in enumerate(toks[:-1]):
        if HEREDOC_OPEN_RE.match(t):
            d = toks[i + 1].lstrip("-")
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", d):
                out.append(d)
    return out


def split_heredocs(command):
    """(text without bodies, [(kind, body, header line)]).

    kind: shell | code (an interpreter reads it) | fetch (a fetch tool or a loop
    reads it as data) | text. An opener inside quotes is not an opener, and a body
    that never meets its terminator is not a heredoc: its lines stay commands.
    """
    lines = command.split("\n")
    kept, bodies, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for delim in heredoc_openers(line):
            j = i
            while j < len(lines) and lines[j].strip() != delim:
                j += 1
            if j >= len(lines):
                break  # unterminated: not a heredoc, keep the lines as commands
            bodies.append((heredoc_target(line), "\n".join(lines[i:j]), line))
            i = j + 1
    return "\n".join(kept), bodies


def heredoc_target(line):
    try:
        toks = tokenize(line)
    except ValueError:
        return "shell"
    kind = "text"
    for seg, _ in split_segments(toks):
        seg = strip_prefixes(seg, {})
        if not seg:
            continue
        head = os.path.basename(seg[0]).lower()
        if head in SHELLS:
            return "shell"
        if head in INTERPRETERS:
            return "code"
        if head in FETCH_TOOLS or head in LOOP_HEADS or head in ("done", "read"):
            kind = "fetch"
    return kind


def strip_prefixes(seg, aliases, depth=0):
    """Drop FOO=bar assignments and wrapper words; expand an alias head."""
    i = 0
    while i < len(seg):
        t = seg[i]
        base = os.path.basename(t).lower()
        if ASSIGN_RE.match(t):
            i += 1
            continue
        if base in WRAPPERS:
            i += 1
            while i < len(seg) and (seg[i].startswith("-") or (
                    base in ("timeout", "gtimeout") and re.match(r"^\d", seg[i]))):
                if base == "env" and seg[i] in ("-S", "--split-string") and i + 1 < len(seg):
                    # env -S 'curl FB': the string IS the command
                    try:
                        seg = seg[:i] + tokenize(seg[i + 1]) + seg[i + 2:]
                    except ValueError:
                        seg = seg[:i] + seg[i + 1].split() + seg[i + 2:]
                    break
                # a wrapper option that takes a value (nice -n 5, sudo -u me,
                # timeout -s KILL 5): the value is not the command (QA round 3)
                i += 2 if seg[i] in WRAPPER_VALUE_OPTS.get(base, ()) else 1
            continue
        break
    seg = list(seg[i:])
    if seg and seg[0] in aliases and depth < 3:
        return strip_prefixes(aliases[seg[0]] + seg[1:], aliases, depth + 1)
    return seg


def substitute(text, env):
    for _ in range(3):
        new = VAR_RE.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), text)
        if new == text:
            break
        text = new
    return text


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------

def resolve_path(tok, cwd):
    t = tok.replace("${HOME}", HOME).replace("$HOME", HOME)
    t = os.path.expanduser(t)
    if not os.path.isabs(t):
        t = os.path.join(cwd, t)
    return t


def read_text(path):
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE:
            return None
        with open(path, "rb") as fh:
            data = fh.read()
    except (OSError, ValueError):
        return None
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", "replace")


JS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"](\.{1,2}/[^'"]+)['"]""",
    re.MULTILINE)
PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([A-Za-z_]\w*)\s+import|import\s+([A-Za-z_]\w*))",
                          re.MULTILINE)


def script_files(path):
    """[text] of the script and its local imports, one level down."""
    text = read_text(path)
    if text is None:
        return None
    parts = [text]
    d = os.path.dirname(path)
    for m in JS_IMPORT_RE.finditer(text):
        base = os.path.normpath(os.path.join(d, m.group(1)))
        for ext in ("", ".mjs", ".js", ".cjs", ".ts", "/index.js", "/index.mjs"):
            t = read_text(base + ext)
            if t is not None:
                parts.append(t)
                break
    for m in PY_IMPORT_RE.finditer(text):
        t = read_text(os.path.join(d, (m.group(1) or m.group(2)) + ".py"))
        if t is not None:
            parts.append(t)
    for s in re.findall(r"^\s*(?:source|\.)\s+(\S+)", text, re.MULTILINE)[:5]:
        t = read_text(resolve_path(s.strip("\"'"), d))
        if t is not None:
            parts.append(t)
    return parts


def words_of(tokens):
    """Candidate file names on a command line; output targets are not sources."""
    skip_next = False
    for t in tokens:
        if skip_next:
            skip_next = False
            continue
        if t in OUTPUT_FLAGS or (REDIR_RE.fullmatch(t) and ">" in t):
            skip_next = True
            continue
        for w in re.split(r"[\s()`$\"'<>|;&]+", t):
            if w.startswith("-") and "=" in w:
                w = w.split("=", 1)[1]
            if w.startswith("@"):
                w = w[1:]
            if w and not w.startswith("-") and len(w) <= 1024:
                yield w


def data_files_text(tokens, cwd, skip=None):
    """Text of existing files named on the command line (URL lists, payloads)."""
    out, seen = [], set()
    for w in words_of(tokens):
        p = resolve_path(w, cwd)
        try:
            real = os.path.realpath(p)
        except (OSError, ValueError):
            continue
        if real in seen or (skip and real in skip) or real in EXEMPT:
            continue
        seen.add(real)
        txt = read_text(p)
        if txt is None:
            txt = big_file_text(p)
        if txt is not None:
            out.append(txt)
    return "\n".join(out)


BIG_LINE_RX = re.compile(rb"facebook|fb\.|messenger|instagr|ig\.me|linkedin|lnkd|x\.com"
                         rb"|twitter|tiktok|threads|m\.me|%2e|\xe3\x80\x82|\xef\xbc|\xef\xbd",
                         re.IGNORECASE)


def big_file_text(path):
    """A data file past MAX_FILE: only its lines that could name a social host (the
    scan stays fast), or the TOO_BIG marker past MAX_BIG. None for a binary file."""
    try:
        if not os.path.isfile(path):
            return None
        size = os.path.getsize(path)
        if size <= MAX_FILE:
            return None
        if size > MAX_BIG:
            return TOO_BIG + "\n" + TOO_BIG
        with open(path, "rb") as fh:
            data = fh.read()
    except (OSError, ValueError):
        return None
    if b"\x00" in data[:8192]:
        return None
    keep = [ln for ln in data.split(b"\n") if BIG_LINE_RX.search(ln)]
    return b"\n".join(keep).decode("utf-8", "replace")


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------

class Load:
    def __init__(self, platforms, urls, route, detail, bulk=None):
        self.platforms = platforms
        self.urls = urls            # every occurrence, repeats kept
        self.route = route
        self.detail = detail
        self.bulk = bulk
        self.paired = False


class Analysis:
    def __init__(self):
        self.loads = []
        self.loop = False
        self.blueprint = False     # 9222 or the Blueprint profile in an EXECUTING part
        self.social = False        # a social host in an executing part or its data


def make_load(ctx, text, route, detail, bulk=None):
    soc = ctx.socials(text)
    if not soc:
        return None
    urls = ctx.social_urls(text) or [h for _, h in soc]
    if len(text) > MAX_SCAN or "__data_too_large_to_scan__" in text:
        bulk = ("a data file too large to scan (over %d MB, or %d MB together) is handed "
                "to a fetcher, loop or script, so it is presumed to be a social URL list. "
                "Split it, or keep social URLs out of it" % (MAX_BIG // 2 ** 20,
                                                            MAX_SCAN // 2 ** 20))
    if not bulk and len(urls) > 1:
        bulk = "one load names %d social URLs" % len(urls)
    return Load({p for p, _ in soc}, urls, route, detail[:120], bulk)


def gate_invocation(seg, cwd):
    """A dict when seg runs THE gate (resolved path), else None."""
    if not seg:
        return None
    head, args = seg[0], seg[1:]
    if os.path.basename(head).lower() in ("python", "python3"):
        j = 0
        while j < len(args) and args[j].startswith("-"):
            j += 1
        if j >= len(args):
            return None
        head, args = args[j], args[j + 1:]
    try:
        if os.path.realpath(resolve_path(head, cwd)) != os.path.realpath(GATE_PATH):
            return None
    except (OSError, ValueError):
        return None
    if not args or args[0] != "acquire":
        return {"sub": args[0] if args else ""}
    info = {"sub": "acquire", "url": None, "route": "local", "grant": False}
    i = 1
    while i < len(args):
        a = args[i]
        for flag in ("--url", "--route"):
            if a == flag and i + 1 < len(args):
                info[flag[2:]] = args[i + 1]
                i += 1
            elif a.startswith(flag + "="):
                info[flag[2:]] = a.split("=", 1)[1]
        if a == "--grant":
            info["grant"] = True
        i += 1
    return info


def fetch_parts(head, args):
    """(targets, payload, url_sources, bulk) for a plain HTTP client.

    Redirections and their files, output files and placeholder words are never
    targets; config files, URL lists and stdin files are url_sources."""
    targets, payload, sources, bulk = [], [], [], None
    i = 0
    while i < len(args):
        a = args[i]
        if REDIR_RE.fullmatch(a):
            if "<" in a and i + 1 < len(args):
                sources.append(args[i + 1])
            i += 2
            continue
        if head in ("curl", "curlie"):
            if a in CURL_CONFIG_FLAGS and i + 1 < len(args):
                sources.append(args[i + 1])
                bulk = "curl reads its URLs from a config file or stdin"
                i += 2
                continue
            if (a in CURL_VALUE_FLAGS or a in OUTPUT_FLAGS) and i + 1 < len(args):
                if a in CURL_VALUE_FLAGS:
                    payload.append(args[i + 1])
                i += 2
                continue
            if a == "--url" and i + 1 < len(args):
                targets.append(args[i + 1])
                i += 2
                continue
            if a.startswith("--url="):
                targets.append(a.split("=", 1)[1])
            elif a in ("-Z", "--parallel", "--next", "-:"):
                bulk = "curl %s runs several requests" % a
            elif a.startswith("-"):
                if "=" in a:
                    payload.append(a.split("=", 1)[1])
            elif a not in ("{}", "%", "::::", ":::"):
                targets.append(a)
            i += 1
            continue
        if head in ("wget", "wget2"):
            if a in WGET_BULK_FLAGS or a.split("=")[0] in WGET_BULK_FLAGS:
                bulk = "wget %s fetches many pages" % a
                if a in ("-i", "--input-file") and i + 1 < len(args):
                    sources.append(args[i + 1])
                    i += 2
                    continue
            elif a in ("-O", "-o", "-a", "--output-document", "--output-file", "-P") \
                    and i + 1 < len(args):
                i += 2
                continue
            elif not a.startswith("-"):
                targets.append(a)
            i += 1
            continue
        if not a.startswith("-"):
            targets.append(a)
        i += 1
    if head not in ("curl", "curlie", "wget", "wget2"):
        if targets and targets[0].upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
            targets = targets[1:]
        targets, payload = targets[:1], payload + targets[1:]
    return targets, payload, sources, bulk


def cron_command(text):
    """Strip crontab time fields so the rest reads as a shell command."""
    return "\n".join(re.sub(r"^\s*(?:@\w+|(?:[\d*/,\-]+\s+){5})", "", line)
                     for line in text.split("\n"))


def scheduled_text(path):
    """The command a scheduler file would run: a launchd plist's Program and
    ProgramArguments, else the file read as a crontab or an at/batch job."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
    except OSError:
        return ""
    if path.endswith(".plist") or head.startswith((b"bplist", b"<?xml")):
        import plistlib
        try:
            with open(path, "rb") as fh:
                pl = plistlib.load(fh)
        except Exception:  # noqa: BLE001 an unreadable plist runs nothing we can see
            return ""
        if not isinstance(pl, dict):
            return ""
        argv = [str(a) for a in (pl.get("ProgramArguments") or []) if isinstance(a, str)]
        prog = pl.get("Program")
        if isinstance(prog, str) and (not argv or argv[0] != prog):
            argv = [prog] + argv[1:] if argv else [prog]
        return shlex.join(argv) if argv else ""
    return cron_command(read_text(path) or "")


def analyze(command, ctx, an=None, depth=0, env=None, aliases=None, cwd=None):
    an = an if an is not None else Analysis()
    env = dict(env or {})
    aliases = dict(aliases or {})
    cwd = cwd or ctx.cwd
    command = command.replace("\\\n", " ")
    stripped, bodies = split_heredocs(command)

    try:
        header_heads = {os.path.basename(t).lower() for t in tokenize(stripped)}
    except ValueError:
        header_heads = set()
    for kind, body, header in bodies:
        body = substitute(body, env)
        if kind in ("shell", "code") and BLUEPRINT_RE.search(body):
            an.blueprint = True
        if not ctx.socials(body):
            continue
        if kind == "shell":
            if depth < 3:
                analyze(body, ctx, an, depth + 1, env, aliases, cwd)
        elif kind == "code":
            an.social = True
            if not GATE_REF_RE.search(body) and (ctx.url_literals(body) or
                                                 FETCH_CODE_RE.search(body)):
                route = "remote" if any(ctx.is_renderer(url_host(u)) for u in re.findall(
                    r"https?://[^\s\"'`]+", normalize(body))) else "local"
                an.loads.append(make_load(ctx, body, route, "heredoc code: " + header.strip()))
        elif kind == "fetch":
            an.social = True
            an.loads.append(make_load(ctx, body, "local", "heredoc read as URLs: "
                                      + header.strip(), "URLs fed from a heredoc"))
        elif FETCH_CODE_RE.search(body) or FETCH_TOOLS & set(re.findall(r"[a-z][\w.-]*",
                                                                          body.lower())):
            if GATE_REF_RE.search(body):
                continue
            if re.search(r">\s*\S|\btee\b", header):
                raise Deny("a heredoc writes an unpaced social loader to disk (%s): it names "
                           "a social host and a fetch or browser primitive and never calls "
                           "the gate" % header.strip()[:80])
            if header_heads & SCHEDULERS:
                sub = analyze(cron_command(body), ctx, None, depth + 1, env, aliases, cwd)
                if [x for x in sub.loads if x]:
                    raise Deny("a crontab / at / launchctl entry would load a social page "
                               "later, outside the gate")

    try:
        tokens = tokenize(stripped)
    except ValueError:
        tokens = stripped.replace("\n", " ; ").split()
        if ctx.socials(stripped) and (FETCH_CODE_RE.search(stripped) or
                                      FETCH_TOOLS & {t.lower() for t in tokens}):
            raise Deny("the command's quoting cannot be parsed and it names a social host "
                       "next to a fetch primitive; refusing rather than guessing")

    for t in tokens:
        m = ASSIGN_RE.match(t)
        if m:
            env[m.group(1)] = m.group(2)
    tokens = [substitute(t, env) for t in tokens]
    defines_function = bool(re.search(
        r"(?:^|[\s;&|{])(?:function\s+[\w-]+|[\w-]+\s*\(\s*\)\s*\{?)", stripped))
    for i, t in enumerate(tokens):
        if t == "alias" and i + 1 < len(tokens):
            m = ASSIGN_RE.match(tokens[i + 1])
            if m:
                try:
                    aliases[m.group(1)] = tokenize(m.group(2))
                except ValueError:
                    aliases[m.group(1)] = m.group(2).split()

    full_text = " ".join(tokens)
    if re.search(r"\{\d+\.\.\d+\}|\bseq\s+\d", stripped):
        an.loop = True

    segs = split_segments(tokens)
    pending_gate = None
    for raw_seg, op_after in segs:
        if raw_seg and os.path.basename(raw_seg[0]).lower() in LOOP_HEADS:
            an.loop = True
        seg = strip_prefixes(raw_seg, aliases)
        if not seg:
            pending_gate = None
            continue
        head_raw = seg[0]
        head = os.path.basename(head_raw).lower()
        args = seg[1:]
        raw_text = " ".join(raw_seg)
        found = []

        if head in LOOP_HEADS or (head == "find" and any(
                a in ("-exec", "-execdir", "-ok", "-okdir") for a in args)):
            an.loop = True

        if head in ("cd", "pushd") and args:
            cwd = resolve_path(args[-1], cwd)
            pending_gate = None
            continue

        gi = gate_invocation(seg, cwd)
        if gi is not None:
            pending_gate = gi if (gi.get("sub") == "acquire" and op_after == "&&") else None
            continue

        # the real command inside xargs / parallel / find -exec / watch
        inner = None
        if head in ("xargs", "parallel"):
            j = 0
            while j < len(args) and args[j].startswith("-"):
                j += 2 if args[j] in XARGS_VALUE_FLAGS else 1
            inner = args[j:]
        elif head == "find":
            for k, a in enumerate(args):
                if a in ("-exec", "-execdir", "-ok", "-okdir") and k + 1 < len(args):
                    inner = args[k + 1:]
                    break
        elif head == "watch":
            j = 0
            while j < len(args) and args[j].startswith("-"):
                j += 2 if args[j] in ("-n", "--interval") else 1
            inner = args[j:]
            if len(inner) == 1:
                try:
                    inner = tokenize(inner[0])
                except ValueError:
                    inner = inner[0].split()
        if inner is not None:
            inner = strip_prefixes(inner, aliases)
            if not inner:
                pending_gate = None
                continue
            head_raw, head, args = inner[0], os.path.basename(inner[0]).lower(), inner[1:]
            seg = inner

        seg_text = " ".join(seg)
        # xargs / parallel / find -exec / watch over a file or list that names social
        # URLs: bulk, whatever the payload command is (sh -c 'curl {}' included). The
        # whole command counts, not only this segment: `echo FB | xargs curl` gets its
        # URLs from the echo segment before the pipe (QA round 3 HIGH).
        if inner is not None:
            fan = data_files_text(tokens, cwd) + "\n" + full_text
            if ctx.socials(fan) and head not in SAFE_HEADS:
                an.social = True
                an.loads.append(make_load(ctx, fan, "local", raw_text, "a fan out (xargs, "
                                          "parallel, find -exec, watch) over social URLs"))
                pending_gate = None
                continue
        executing = head not in SAFE_HEADS
        if executing and BLUEPRINT_RE.search(raw_text):
            an.blueprint = True
        if executing and ctx.socials(raw_text):
            an.social = True

        # shells, eval, tmux and screen: the string they run is a command of its own
        sub_cmds = []
        c_at = next((k for k, a in enumerate(args) if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a)),
                    None) if head in SHELLS else None
        if c_at is not None and c_at + 1 < len(args):
            sub_cmds.append(args[c_at + 1])
        elif head == "eval":
            sub_cmds.append(" ".join(args))
        elif head in HANDOFF_HEADS:
            sub_cmds += [a for a in args if not a.startswith("-") and " " in a]
            sub_cmds.append(" ".join(a for a in args[1:] if not a.startswith("-")))
        if sub_cmds or head == "eval" or head in HANDOFF_HEADS:
            for sub_cmd in sub_cmds:
                if depth >= 3:
                    if ctx.socials(sub_cmd):
                        raise Deny("social host nested more than three shells deep")
                    continue
                sub = analyze(sub_cmd, ctx, None, depth + 1, env, aliases, cwd)
                an.loop = an.loop or sub.loop
                an.blueprint = an.blueprint or sub.blueprint
                an.social = an.social or sub.social
                for ld in sub.loads:
                    if ld:
                        ld.detail = ("inside %s: %s" % (head, ld.detail))[:120]
                        an.loads.append(ld)
            pending_gate = None
            continue

        # git runs a `!`-prefixed alias through the shell: git -c alias.x='!curl ...' x,
        # or git config alias.x '!curl ...' written for a later call
        if head == "git":
            bang = [a.split("=", 1)[1][1:] if "=!" in a else a[1:] for a in args
                    if a.startswith("!") or "=!" in a]
            for b in bang:
                sub = analyze(b, ctx, None, depth + 1, env, aliases, cwd)
                if [x for x in sub.loads if x] or (sub.blueprint and sub.social):
                    raise Deny("a git alias runs a social load through the shell (%s)"
                               % raw_text[:80])
            pending_gate = None
            continue

        # make runs its recipes through the shell: read the Makefile like a script
        if head in ("make", "gmake"):
            mk = next((args[k + 1] for k, a in enumerate(args[:-1]) if a in ("-f", "--file")),
                      None)
            names = [mk] if mk else ["GNUmakefile", "makefile", "Makefile"]
            for nm in names:
                p = resolve_path(nm, cwd)
                if os.path.isfile(p):
                    found += scan_script(ctx, an, p, [], seg_text, cwd)
                    break

        # any other program handed a command: a quoted string (docker run IMG sh -c
        # '...', ssh host '...', su me -c '...', script -q f sh -c '...') or a tail that
        # starts with a fetch tool or an interpreter (docker run IMG curl -s FB, arch
        # -arm64 curl FB). Read it as a command of its own (QA round 3).
        if head not in SAFE_HEADS and head not in FETCH_TOOLS and head not in INTERPRETERS \
                and head not in SCHEDULERS and head not in ("make", "gmake"):
            subs = [a for a in args if (" " in a or "\n" in a) and ctx.socials(a)]
            k = next((k for k, a in enumerate(args) if os.path.basename(a).lower() in (
                FETCH_TOOLS | INTERPRETERS | LOOP_HEADS | {"xargs", "eval"})), None)
            if k is not None and ctx.socials(" ".join(args[k:])):
                subs.append(shlex.join(args[k:]))
            for sub_cmd in subs:
                if depth >= 3:
                    raise Deny("social host nested more than three commands deep")
                sub = analyze(sub_cmd, ctx, None, depth + 1, env, aliases, cwd)
                an.loop = an.loop or sub.loop
                an.blueprint = an.blueprint or sub.blueprint
                an.social = an.social or sub.social
                for ld in sub.loads:
                    if ld:
                        ld.detail = ("inside %s: %s" % (head, ld.detail))[:120]
                        found.append(ld)

        # a social scraper is a bulk social load whatever its arguments look like
        scraper = head if head in SOCIAL_TOOLS else None
        if scraper is None and head in INTERPRETERS and "-m" in args:
            k = args.index("-m")
            if k + 1 < len(args) and args[k + 1].lower() in SOCIAL_TOOLS:
                scraper = args[k + 1].lower()
        if scraper:
            plat = SOCIAL_TOOLS[scraper] or "facebook"
            found.append(Load({plat}, [scraper, scraper], "local", seg_text,
                              "%s is a social scraper: it loads many pages" % scraper))

        if head in ("source", ".") and args:
            p = resolve_path(args[0], cwd)
            if os.path.isfile(p):
                found += scan_script(ctx, an, p, args[1:], seg_text, cwd)

        if head in SCHEDULERS:
            # the scheduled command is a quoted token somewhere in this command (echo
            # "0 * * * * curl ..." | crontab -), or what follows `--` (launchctl submit)
            cands = [cron_command(t) for t in tokens if " " in t or "\n" in t]
            if "--" in args:
                cands.append(" ".join(args[args.index("--") + 1:]))
            cands.append(cron_command(" ".join(args)))
            # ... or a FILE: launchctl load/bootstrap x.plist (or a LaunchAgents dir),
            # at -f job.sh, batch < job.sh, crontab file (QA round 3)
            for a in args:
                p = resolve_path(a, cwd)
                if os.path.isdir(p) and head == "launchctl":
                    try:
                        names = sorted(os.listdir(p))[:300]
                    except OSError:
                        names = []
                    cands += [scheduled_text(os.path.join(p, n)) for n in names
                              if n.endswith(".plist")]
                elif os.path.isfile(p):
                    cands.append(scheduled_text(p))
            # the job file may only reach its place when the command runs (cp x.plist
            # ~/Library/LaunchAgents/ && launchctl load ...): read every existing file
            # the command names
            seen_sched = set()
            for w in list(words_of(tokens))[:200]:
                p = resolve_path(w, cwd)
                if p not in seen_sched and os.path.isfile(p):
                    seen_sched.add(p)
                    cands.append(scheduled_text(p))
            for cand in cands:
                sub = analyze(cand, ctx, None, depth + 1, env, aliases, cwd)
                if [x for x in sub.loads if x] or (sub.blueprint and sub.social):
                    raise Deny("a crontab / at / launchctl entry would load a social page "
                               "later, outside the gate (%s)" % raw_text[:80])
            pending_gate = None
            continue

        if head in FETCH_TOOLS:
            if head in PLAIN_HTTP:
                targets, payload, sources, bulk = fetch_parts(head, args)
                social_t = [t for t in targets if ctx.platform_of(url_host(t))]
                renderer_t = [t for t in targets if ctx.is_renderer(url_host(t))]
                variable = [t for t in targets if "$" in t or "`" in t]
                if an.loop and (re.search(r"://[^/\s\"']*(?:\$\(|`)", stripped) or any(
                        re.search(r"://[^/]*(?:\$\(|`|\$$)", t) for t in targets)):
                    # https://www.$(printf face)book.com/$s in a loop: the host is only
                    # known at run time, so which site it loads cannot be read here
                    raise Deny("a fetch inside a loop whose target HOST is computed at run "
                               "time ($(...) or backticks in the host part); write the host "
                               "out literally (%s)" % seg_text[:80])
                follows = head in ("wget", "wget2") or any(
                    a in ("--location", "--location-trusted", "--follow")
                    or re.match(r"^-[a-zA-Z]*L[a-zA-Z]*$", a) for a in args) or (
                    head in ("http", "https", "httpie", "xh") and "-F" in args)
                embedded = [unquote(t.split("?", 1)[1]) for t in targets if "?" in t
                            and not social_t and ctx.url_literals(unquote(t.split("?", 1)[1]))]
                if follows and embedded and not renderer_t:
                    # google.com/url?q=<a facebook url> with -L: a redirector that lands
                    # on the social page, from this Mac
                    found.append(make_load(ctx, " ".join(embedded), "local",
                                           seg_text + " (a redirector to a social page)"))
                elif social_t:
                    tt = " ".join(social_t)
                    if re.search(r"\[[^\]]*-[^\]]*\]|\{[^}]*,[^}]*\}", tt):
                        bulk = "curl URL globbing expands to many pages"
                    found.append(make_load(ctx, tt, "local", seg_text, bulk))
                elif renderer_t:
                    body = " ".join(payload + targets) + "\n" + data_files_text(
                        payload + sources, cwd)
                    if ctx.socials(body):
                        found.append(make_load(ctx, body, "remote",
                                               seg_text + " (via a remote renderer)"))
                elif sources or variable or (not targets and inner is not None):
                    reach = data_files_text(sources, cwd)
                    if variable or inner is not None or an.loop:
                        reach += "\n" + data_files_text(tokens, cwd)
                    if variable:
                        reach += "\n" + full_text
                    if ctx.socials(reach):
                        found.append(make_load(ctx, reach, "local", seg_text, bulk or (
                            "the URLs come from a file or stdin"
                            if (sources or inner is not None) else None)))
            else:
                social_a = [a for a in args if ctx.platform_of(url_host(a))]
                if head == "open":
                    for a in args:
                        p = resolve_path(a, cwd)
                        if (a.lower().endswith(SCRIPT_EXTS) or a.startswith(("/", "./", "~"))) \
                                and os.path.isfile(p):
                            found += scan_script(ctx, an, p, [], seg_text, cwd)
                if social_a:
                    found.append(make_load(ctx, " ".join(social_a), "local", seg_text))

        elif head in INTERPRETERS:
            inline, script, j = None, None, 0
            while j < len(args):
                a = args[j]
                if a in ("-c", "-e", "--eval", "-p", "--print", "-m") and j + 1 < len(args):
                    inline = " ".join(args[j + 1:])
                    break
                if REDIR_RE.fullmatch(a):
                    if "<" in a and j + 1 < len(args):
                        found += scan_script(ctx, an, resolve_path(args[j + 1], cwd), [],
                                             seg_text, cwd)
                    j += 2
                    continue
                if a in INTERP_VALUE_OPTS or (a == "-r" and head in ("node", "nodejs")):
                    j += 2
                    continue
                if a.startswith("-"):
                    j += 1
                    continue
                if head in ("deno", "bun") and a in ("run", "x", "exec"):
                    j += 1
                    continue
                script = a
                break
            if inline is not None:
                # a one liner is a load when it names a social host AND can fetch, open
                # or spawn something; printing a canonical link is not a load
                if ctx.socials(inline) and ONELINER_FETCH_RE.search(inline):
                    route = "remote" if any(ctx.is_renderer(url_host(u)) for u in re.findall(
                        r"https?://[^\s\"'`]+", normalize(inline))) else "local"
                    found.append(make_load(ctx, inline, route, seg_text))
                # a one liner that runs a script file (do shell script "bash x.sh",
                # spawn bash x.sh, subprocess.run(['node', 'x.mjs'])): read that file
                for w in re.findall(r"[\w~./-]+", inline):
                    if w.lower().endswith(SCRIPT_EXTS):
                        p = resolve_path(w, cwd)
                        if os.path.isfile(p):
                            found += scan_script(ctx, an, p, [], seg_text, cwd)
            elif script:
                p = resolve_path(script, cwd)
                rest = args[j + 1:]
                if read_text(p) is not None:
                    found += scan_script(ctx, an, p, rest, seg_text, cwd)
                elif any(ctx.platform_of(url_host(a)) for a in rest):
                    # a script this hook cannot read, handed a social URL: a load
                    found.append(make_load(ctx, " ".join(a for a in rest if ctx.platform_of(
                        url_host(a))), "local", seg_text + " (script not readable here)"))
            elif not found:
                # `cat x.sh | bash`, `python3 -`: the code arrives on stdin, from the
                # command itself or from a file the command names
                reach = full_text + "\n" + data_files_text(tokens, cwd)
                if ctx.socials(reach) and (FETCH_CODE_RE.search(reach) or FETCH_TOOLS
                                           & set(re.findall(r"[a-z][\w.-]*", reach.lower()))):
                    found.append(make_load(ctx, reach, "local",
                                           "%s reading code from stdin" % head))

        elif os.sep in head_raw or head_raw.startswith("~"):
            p = resolve_path(head_raw, cwd)
            if os.path.isfile(p):
                found += scan_script(ctx, an, p, args, seg_text, cwd)

        elif head not in SAFE_HEADS:
            p = shutil.which(head_raw)
            p = os.path.realpath(p) if p else None
            if p and p.startswith(HOME + os.sep) and read_text(p) is not None:
                found += scan_script(ctx, an, p, args, seg_text, cwd)
            elif defines_function or head in aliases:
                if ctx.socials(" ".join(args)):
                    found.append(make_load(ctx, " ".join(args), "local",
                                           "%s (a function or alias)" % seg_text))
            elif any("://" in a and ctx.platform_of(url_host(a)) for a in args):
                found.append(make_load(ctx, " ".join(a for a in args if "://" in a),
                                       "local", "%s (an unknown program handed a social URL)"
                                       % seg_text))

        for ld in [x for x in found if x]:
            an.social = True
            if (pending_gate and pending_gate.get("url") and not pending_gate.get("grant")
                    and not ld.bulk and len(ld.urls) <= 1 and len(ld.platforms) == 1):
                gp = ctx.platform_of(url_host(pending_gate["url"]))
                gr = pending_gate.get("route")
                if gp in ld.platforms and (gr == ld.route or (ld.route == "remote"
                                                              and gr == "local")):
                    ld.paired = True
                    pending_gate = None
            an.loads.append(ld)
        pending_gate = None
    return an


def scan_script(ctx, an, path, args, seg_text, cwd):
    real = os.path.realpath(path)
    if real in EXEMPT or THIRD_PARTY_RE.search(real):
        return []
    files = script_files(path)
    if files is None:
        return []
    code = "\n".join(files)
    data = data_files_text(args, cwd, skip={real})
    offline_test = bool(TEST_FILE_RE.search(real)) and not LIVE_TEST_RE.search(
        os.path.basename(real))
    # A social URL literal counts only in a file that can also fetch or browse: a
    # module that merely builds a canonical profile link is not a loader.
    soc_code = [] if offline_test else [
        x for t in files if FETCH_CODE_RE.search(t) for x in ctx.url_literals(t)]
    soc_args = [a for a in args if ctx.platform_of(url_host(a))]
    soc_data = ctx.socials(data)
    if BLUEPRINT_RE.search(code) and not offline_test:
        an.blueprint = True
    if not (soc_code or soc_args or soc_data):
        return []
    an.social = True
    if GATE_REF_RE.search(code) or not FETCH_CODE_RE.search(code):
        return []  # paces itself through the gate, or cannot fetch at all
    route = "remote" if any(ctx.is_renderer(url_host(u)) for u in re.findall(
        r"https?://[^\s\"'`$]+", normalize(code))) else "local"
    name = os.path.basename(path)
    if soc_code:
        return [make_load(ctx, code, route, "script %s: %s" % (name, seg_text),
                          "%s loads social URLs named in its own code, and never calls "
                          "the gate. Wire the gate in before every social load. If it truly "
                          "loads no social page (the URLs are only data), say so in the "
                          "file: a comment `social-gate: loads no social page`" % name)]
    if soc_data:
        return [make_load(ctx, data, route, "script %s: %s" % (name, seg_text),
                          "%s is handed a file of social URLs" % name)]
    return [make_load(ctx, " ".join(soc_args), route, "script %s: %s" % (name, seg_text))]


# --------------------------------------------------------------------------
# decisions
# --------------------------------------------------------------------------

FOOTER = """
The sanctioned shapes (one budget for the whole Mac, per platform: {rules}):
  {gate} acquire --url <url> --actor <you> && curl -s <that one url>
  {gate} acquire --url <url> --actor <you> --grant     (then, on its own, one load or browser_navigate)
  {gate} status                                          (what is left today)
A script that loads social pages calls the gate before EVERY load (import it, or run the
CLI per page). The Blueprint Chrome on port 9222 never loads a social host.
There is no override. If the gate says wait, wait; if it refuses, stop for now and report."""


def rules_line(ctx):
    try:
        loc, rem = ctx.cfg["routes"]["local"], ctx.cfg["routes"]["remote"]
        return ("local {g} s apart at least, {h} an hour, {d} a day; remote {rg} s apart, "
                "{rd} a day".format(g=loc["min_gap_s"], h=loc["per_hour"], d=loc["per_day"],
                                    rg=rem["min_gap_s"], rd=rem["per_day"]))
    except (TypeError, KeyError):
        return "config unreadable"


def deny_text(ctx, reason, extra=""):
    msg = "BLOCKED (social-pace-guard): %s" % reason
    if extra:
        msg += "\n" + extra
    return msg + FOOTER.format(rules=rules_line(ctx), gate=GATE_CMD)


# --- the gate's own files -----------------------------------------------------
# The ledger, the gate state and the owner's config ARE the budget: `rm` the ledger
# and every cap resets, `rm` the state and the gap is gone, `sed -i` the config and
# the caps rise (QA round 3). Only Zalo changes them, in his own terminal.

STATE_DIR = os.path.join(HOME, ".claude", "state")
PROTECTED_NAMES = ("social-loads.jsonl", "social-gate-state.json", "social-gate.lock",
                   "social-pacing.json")
PROTECTED_PARENTS = {os.path.realpath(p) for p in (
    HOME, os.path.join(HOME, ".claude"), STATE_DIR, os.path.dirname(CONFIG_PATH))}
REMOVE_HEADS = {"rm", "unlink", "mv", "trash", "srm", "shred", "truncate", "tee", "sponge"}
DEST_HEADS = {"cp", "ln", "install", "rsync", "ditto", "gcp"}
INPLACE_HEADS = {"sed", "gsed", "perl", "ruby", "awk", "gawk"}
PROTECT_PREFILTER_RE = re.compile(r"social-|\.claude|\bstate\b|~|HOME|/Users/|\bconfig\b")
PROTECTED_TEXT_RE = re.compile(r"social-(?:loads|gate-state|gate\.lock|pacing)|\.claude/state"
                               r"|\.claude/config|\bstate/\*|config/\*", re.IGNORECASE)
WRITE_CODE_RE = re.compile(
    r"open\s*\([^)]*['\"][rbt]*[wax+][rwabxt+]*['\"]|write_text|write_bytes|\bunlink|"
    r"\bremove\s*\(|rmtree|\brename|os\.replace|\btruncate|writeFile|appendFile|rmSync|"
    r"unlinkSync|renameSync|copyFile|\bos\.system|subprocess|shutil\.(?:move|copy)|"
    r"\bdo shell script\b|\bspawn|\bexec\w*\s*\(", re.IGNORECASE)


def protected_kind(tok, cwd):
    """'file' for the ledger, the gate state or the config (a glob that could match
    one included), 'dir' for a directory that holds them, else None."""
    if not tok or tok.startswith("-"):
        return None
    p = resolve_path(tok.split("=", 1)[1] if tok.startswith("of=") else tok, cwd)
    if any(c in p for c in "*?["):
        import fnmatch
        d = os.path.realpath(os.path.dirname(p))
        pat = os.path.basename(p)
        if d in (os.path.realpath(STATE_DIR), os.path.realpath(os.path.dirname(CONFIG_PATH))) \
                and any(fnmatch.fnmatch(n, pat) for n in PROTECTED_NAMES):
            return "file"
        return "dir" if d in PROTECTED_PARENTS and pat in ("*", ".*") else None
    try:
        real = os.path.realpath(p)
    except (OSError, ValueError):
        return None
    if real == os.path.realpath(CONFIG_PATH) or (
            os.path.dirname(real) == os.path.realpath(STATE_DIR)
            and os.path.basename(real).startswith("social-")):
        return "file"
    return "dir" if real in PROTECTED_PARENTS else None


def protected_write(command, cwd, depth=0):
    """A reason string when the command would write, move or delete the gate's own
    files, else None. Reads are fine (cat, grep, jq, ls, sqlite3, git add/diff)."""
    if depth > 3 or not PROTECT_PREFILTER_RE.search(command):
        return None
    stripped, bodies = split_heredocs(command.replace("\\\n", " "))
    for kind, body, header in bodies:
        if kind == "shell":
            r = protected_write(body, cwd, depth + 1)
            if r:
                return r
        elif kind == "code" and PROTECTED_TEXT_RE.search(body) and WRITE_CODE_RE.search(body):
            return "a heredoc program writes or deletes the gate's files (%s)" % header.strip()[:60]
    try:
        tokens = tokenize(stripped)
    except ValueError:
        tokens = stripped.split()
    env = {}
    for t in tokens:
        m = ASSIGN_RE.match(t)
        if m:
            env[m.group(1)] = m.group(2)
    tokens = [substitute(t, env) for t in tokens]
    whole_hits = any(protected_kind(t, cwd) for t in tokens)
    for k, t in enumerate(tokens):  # > file, >> file, &> file, >| file
        if REDIR_RE.fullmatch(t) and ">" in t and "&" != t[-1:] and k + 1 < len(tokens) \
                and protected_kind(tokens[k + 1], cwd) == "file":
            return "a redirection writes %s" % tokens[k + 1]
    for raw, _ in split_segments(tokens):
        seg = strip_prefixes(raw, {})
        if not seg:
            continue
        head, args = os.path.basename(seg[0]).lower(), seg[1:]
        if head in ("cd", "pushd") and args:
            cwd = resolve_path(args[-1], cwd)
            continue
        if head in ("xargs", "parallel"):
            j = 0
            while j < len(args) and args[j].startswith("-"):
                j += 2 if args[j] in XARGS_VALUE_FLAGS else 1
            inner = strip_prefixes(args[j:], {})
            if inner and os.path.basename(inner[0]).lower() in (
                    REMOVE_HEADS | DEST_HEADS | INPLACE_HEADS | {"rmdir"}) and whole_hits:
                return "%s %s over the gate's files" % (head, inner[0])
            continue
        kinds = [(a, protected_kind(a, cwd)) for a in args if not REDIR_RE.fullmatch(a)]
        files = [a for a, kd in kinds if kd == "file"]
        dirs = [a for a, kd in kinds if kd == "dir"]
        if head == "mv":
            plain = [a for a in args if not a.startswith("-")]
            src, dst = plain[:-1], plain[-1:]
            if any(protected_kind(s, cwd) for s in src) or (dst and (
                    protected_kind(dst[0], cwd) == "file" or (
                        protected_kind(dst[0], cwd) == "dir"
                        and any(os.path.basename(s) in PROTECTED_NAMES for s in src)))):
                return "mv moves or replaces the gate's files (%s)" % " ".join(plain)[:80]
        elif head in REMOVE_HEADS:
            recursive = head in ("trash", "srm") or any(re.match(r"^-\w*[rR]", a) for a in args)
            if files or (dirs and recursive):
                return "%s on %s" % (head, " ".join(files or dirs)[:80])
        if head in DEST_HEADS:
            plain = [a for a in args if not a.startswith("-")]
            if plain:
                kd = protected_kind(plain[-1], cwd)
                if kd == "file" or (kd == "dir" and any(
                        os.path.basename(s) in PROTECTED_NAMES for s in plain[:-1])):
                    return "%s writes over %s" % (head, plain[-1])
        if head in INPLACE_HEADS and files and any(
                a.startswith("-i") or a.startswith("--in-place") or re.match(r"^-\w*i", a)
                or a == "inplace" for a in args):
            return "%s edits %s in place" % (head, files[0])
        if head == "dd" and files:
            return "dd writes %s" % files[0]
        if head == "find" and (files or dirs) and ("-delete" in args or any(
                os.path.basename(args[k + 1]).lower() in REMOVE_HEADS | INPLACE_HEADS
                for k, a in enumerate(args[:-1]) if a in ("-exec", "-execdir", "-ok"))):
            return "find deletes or edits under %s" % " ".join(files or dirs)[:80]
        if head == "git" and args:
            sub = next((a for a in args if not a.startswith("-")), "")
            if sub in ("rm", "mv") and files:
                return "git %s on %s" % (sub, files[0])
            if sub == "clean" and any(re.match(r"^-\w*[xX]", a) for a in args) and (
                    os.path.realpath(cwd).startswith(os.path.realpath(
                        os.path.join(HOME, ".claude"))) or ".claude" in " ".join(args)):
                return "git clean -x in ~/.claude deletes the ignored ledger and state"
        if head in SHELLS or head == "eval":
            c_at = next((k for k, a in enumerate(args) if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*",
                                                                       a)), None)
            sub_cmd = args[c_at + 1] if (c_at is not None and c_at + 1 < len(args)) else (
                " ".join(args) if head == "eval" else None)
            if sub_cmd:
                r = protected_write(sub_cmd, cwd, depth + 1)
                if r:
                    return r
        if head in INTERPRETERS and head not in SHELLS:
            code = " ".join(a for a in args if a not in ("-c", "-e", "--eval"))
            if PROTECTED_TEXT_RE.search(code) and WRITE_CODE_RE.search(code) and not any(
                    os.path.realpath(resolve_path(a, cwd)) in EXEMPT for a in args):
                return "a %s one liner writes or deletes the gate's files" % head
    return None


def protected_msg(reason):
    return ("BLOCKED (social-pace-guard): %s.\nThe social pacing ledger, the gate state and "
            "~/.claude/config/social-pacing.json ARE the budget: deleting the ledger resets "
            "every cap, and the config is Zalo's. Only Zalo changes them, in his own "
            "terminal. Read them freely (cat, jq, `%s status`). There is no override."
            % (reason, GATE_CMD))


def decide_bash(command, ctx):
    if not command.strip():
        return True, ""
    reason = protected_write(command, ctx.cwd)
    if reason:
        return False, protected_msg(reason)
    if not (ctx.socials(command) or ctx.socials(command.replace('"', "").replace("'", ""))
            or PREFILTER_RE.search(command)):
        return True, ""
    try:
        an = analyze(command, ctx)
    except Deny as e:
        return False, deny_text(ctx, str(e))

    loads = [ld for ld in an.loads if ld]
    if an.blueprint and (an.social or loads):
        return False, deny_text(
            ctx, "port 9222 or the Blueprint profile together with a social host",
            "The Blueprint Chrome (port 9222, ~/.blueprint-chrome-profile) is the GoHighLevel\n"
            "browser. It never loads Facebook, LinkedIn, Instagram, X, TikTok or Threads, gated\n"
            "or not: that is how 631 Facebook profiles were loaded on 2026-09-26.")
    if not loads:
        return True, ""
    if ctx.cfg_error:
        return False, deny_text(ctx, "the pacing gate cannot run (%s), so no social load "
                                     "passes" % ctx.cfg_error)
    for ld in loads:
        if ld.bulk:
            return False, deny_text(ctx, "bulk social load: %s (%s)" % (ld.bulk, ld.detail))
    unpaired = [ld for ld in loads if not ld.paired]
    if not unpaired:
        return True, ""
    if an.loop:
        return False, deny_text(ctx, "a social load inside a loop, xargs, parallel, watch or "
                                     "find -exec with no gate call per load (%s)"
                                % unpaired[0].detail)
    ld = unpaired[0]
    plat = sorted(ld.platforms)[0]
    try:
        if len(unpaired) == 1 and len(ld.platforms) == 1 and len(ld.urls) <= 1 and (
                ctx.gate.consume_grant(plat, ld.route) or
                (ld.route == "remote" and ctx.gate.consume_grant(plat, "local"))):
            return True, ""
        probe = ld.urls[0] if ld.urls else plat + ".com"
        line = ctx.gate.check(probe, ld.route).line()
    except Exception as e:  # noqa: BLE001 the gate failing is a refusal
        line = "the gate could not be read: %s" % e
    return False, deny_text(ctx, "an unpaced social load (%s, route %s): %s" % (
        "/".join(sorted(ld.platforms)), ld.route, ld.detail), "Gate now: " + line)


# --- browser tools ---------------------------------------------------------

URL_TOOL_RE = re.compile(r"navigate|tabs|new_page|newpage|open_url|goto|webfetch|open_tab"
                         r"|create_tab", re.IGNORECASE)
CODE_TOOL_RE = re.compile(r"evaluate|run_code|javascript|execute|script", re.IGNORECASE)
ELEMENT_TOOL_RE = re.compile(r"_type$|fill|form_input|select_option|press_key|hover|"
                             r"file_upload|snapshot|screenshot|console|network|find$", re.IGNORECASE)
BROWSER_TOOL_RE = re.compile(r"^(?:WebFetch|mcp__.*(?:playwright|chrome|browser|puppeteer).*)$",
                             re.IGNORECASE)


def strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings_in(v)


def playwright_on_blueprint(ctx):
    """Is the Playwright MCP configured to drive a CDP browser on port 9222?"""
    try:
        with open(ctx.claude_json) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return False
    hits = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "mcpServers" and isinstance(v, dict):
                    hits.extend(json.dumps(c) for n, c in v.items() if "playwright" in n.lower())
                else:
                    walk(v)
    walk(d)
    return any(BLUEPRINT_RE.search(h) or ("9222" in h and "cdp" in h.lower()) for h in hits)


def decide_browser(tool, tool_input, ctx, session=""):
    blob = "\n".join(strings_in(tool_input))
    soc = ctx.socials(blob)
    if not soc:
        return True, ""
    is_url_tool, is_code_tool = bool(URL_TOOL_RE.search(tool)), bool(CODE_TOOL_RE.search(tool))
    omnibox = bool(re.search(r"computer|omnibox|address", tool, re.IGNORECASE))
    if omnibox and isinstance(tool_input.get("text"), str) and len(
            tool_input["text"].split()) > 1:
        # prose typed into a page (a Gmail reply naming facebook.com/joes) is not a
        # navigation: the omnibox would search it, not load it (QA round 3)
        return True, ""
    if not (is_url_tool or is_code_tool) and not omnibox and ELEMENT_TOOL_RE.search(tool):
        # Playwright type / fill / select act on a page element: they cannot reach
        # the address bar, so a social URL typed into a CRM field is not a load
        return True, ""
    if not (is_url_tool or is_code_tool) and (ctx.url_literals(blob) or omnibox):
        # a Chrome `computer` action (it can type into the address bar) naming a social
        # host, with or without a scheme, or any other browser action carrying a full
        # social URL (a click on a link): it IS a navigation, so it spends a slot
        is_url_tool = True
    if not (is_url_tool or is_code_tool):
        return True, ""
    if BLUEPRINT_RE.search(blob) or (tool.startswith("mcp__playwright")
                                     and playwright_on_blueprint(ctx)):
        return False, deny_text(ctx, "a social host in a browser attached to port 9222 "
                                     "(the Blueprint Chrome)")
    urls = ctx.social_urls(blob)
    if is_code_tool:
        navs = len(NAV_CALL_RE.findall(blob))
        if not navs:
            return True, ""
        if len(urls) > 1 or navs > 1 or CODE_LOOP_RE.search(blob):
            return False, deny_text(ctx, "page code that loads several pages, loops, reduces, "
                                         "recurses or sets timers (%s)" % tool)
    elif len(urls) > 1:
        return False, deny_text(ctx, "one browser call names %d social URLs (%s)"
                                % (len(urls), tool))
    if ctx.cfg_error:
        return False, deny_text(ctx, "the pacing gate cannot run (%s)" % ctx.cfg_error)
    plat, host = soc[0]
    url = urls[0] if urls else host
    try:
        if ctx.gate.consume_grant(plat, "local"):
            return True, ""
        actor = "hook:" + (re.sub(r"[^A-Za-z0-9]", "", session)[:8] or "claude")
        # the gate is asked about the normalised host this call names, so a
        # spelling the gate would not classify can never pass as "not social"
        d = ctx.gate.acquire("https://%s/" % host, actor, "local", max_wait=0,
                             via="hook:" + tool[-40:])
    except Exception as e:  # noqa: BLE001 the gate failing is a refusal
        return False, deny_text(ctx, "the pacing gate failed (%s)" % e)
    if d.code == 0 and d.social:
        return True, ""
    if d.code == 0:
        return False, deny_text(ctx, "the gate did not classify %s as social; refusing" % host)
    extra = "Gate: " + d.line()
    if d.code == 3:
        extra += ("\nTo wait for the slot: %s acquire --url '%s' --actor <you> --grant\n"
                  "(it sleeps up to max_wait_s, then this navigation passes once)."
                  % (GATE_CMD, url))
    return False, deny_text(ctx, "social page load refused by the gate (%s)" % tool, extra)


def decide(payload, ctx=None):
    if not isinstance(payload, dict):
        return True, ""
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input")
    if not isinstance(ti, dict):
        return True, ""
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        if path and protected_kind(path, payload.get("cwd") or os.getcwd()) == "file":
            return False, protected_msg("%s would change %s" % (tool, path))
        return True, ""
    if tool == "Bash":
        return decide_bash(str(ti.get("command") or ""), ctx or Ctx(cwd=payload.get("cwd")))
    if BROWSER_TOOL_RE.match(tool):
        if not re.search(r"[.。．｡]|%2e", "".join(strings_in(ti)), re.IGNORECASE):
            return True, ""
        return decide_browser(tool, ti, ctx or Ctx(cwd=payload.get("cwd")),
                              str(payload.get("session_id") or ""))
    return True, ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 an unreadable payload is not a command
        return 0
    try:
        allowed, msg = decide(payload)
    except Exception as e:  # noqa: BLE001 never crash OPEN on a social command
        blob = normalize(json.dumps(payload.get("tool_input") if isinstance(payload, dict)
                                    else "", ensure_ascii=False))
        if re.search(r"facebook|instagram|linkedin|twitter|tiktok|threads|messenger|x\.com"
                     r"|fb\.|lnkd|instagr|9222", blob, re.IGNORECASE):
            print("BLOCKED (social-pace-guard): internal error (%s: %s) on a call that names "
                  "a social host; refusing rather than guessing." % (type(e).__name__, e),
                  file=sys.stderr)
            return 2
        return 0
    if allowed:
        return 0
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
