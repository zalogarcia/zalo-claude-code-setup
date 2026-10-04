#!/usr/bin/env python3
"""Behaviour suite for social-pace-guard.py. Run: python3 ~/.claude/hooks/social-pace-guard.test.py

Same shape as tmux-peer-guard.test.py / money-guard.test.py (a table of labelled
commands with allow or deny), run IN PROCESS against a Gate built on a temp state
dir, so no case ever writes the real ledger or spends the real budget. A last
section feeds a few payloads to the real hook over stdin, to prove the wiring
(exit codes, stderr) on shapes that never touch the gate's state.

Nothing here loads a page. The fixture scripts are written to a temp dir and
only ever READ by the hook.
"""
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile

HOOK = os.path.expanduser("~/.claude/hooks/social-pace-guard.py")
GATE = os.path.expanduser("~/.claude/scripts/social-gate.py")
REAL_CFG = os.path.expanduser("~/.claude/config/social-pacing.json")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hk = load("spg", HOOK)
sg = load("sg", GATE)

T = tempfile.mkdtemp(prefix="spg-test-")
G = "python3 " + GATE  # the real gate path, as an agent would type it
GT = "python3 ~/.claude/scripts/social-gate.py"
FB = "https://www.facebook.com/some.person.1"
FB2 = "https://www.facebook.com/other.person.2"
LI = "https://www.linkedin.com/in/someone"
CF = "https://api.cloudflare.com/client/v4/accounts/abc/browser-rendering/markdown"


def fx(name, text):
    p = os.path.join(T, name)
    with open(p, "w") as fh:
        fh.write(text)
    return p


URLS = fx("fb-urls.txt", FB + "\n" + FB2 + "\n")
ONE_URL = fx("one-url.txt", FB + "\n")
# the 2026-09-26 incident shape: a CDP page reader aimed at the Blueprint Chrome
CDP = fx("cdp-read.mjs", "const url = process.argv[2];\n"
         "const v = await (await fetch('http://127.0.0.1:9222/json/version')).json();\n"
         "const ws = new WebSocket(v.webSocketDebuggerUrl);\n")
CDP_IMPORT = fx("batch.mjs", "import { connect } from './cdp.mjs';\n"
                "import fs from 'fs';\nconst urls = JSON.parse(fs.readFileSync(process.argv[2]));\n")
fx("cdp.mjs", "export async function connect() {\n"
   "  const v = await (await fetch('http://localhost:9222/json/version')).json();\n}\n")
WORKLIST = fx("worklist.json", json.dumps([FB, FB2]))
LOADER_JS = fx("loader.mjs", "const r = await fetch('https://www.facebook.com/x');\n")
LOADER_SH = fx("loader.sh", "#!/bin/bash\ncurl -s https://www.facebook.com/x -o /tmp/x.html\n")
READER = fx("read-page.mjs", "const r = await fetch(process.argv[2]);\n"
            "console.log((await r.text()).length);\n")
GATED = fx("gated.py", "import subprocess, requests\n"
           "# calls ~/.claude/scripts/social-gate.py acquire before every load\n"
           "def load(u):\n    subprocess.run(['python3', 'social-gate.py', 'acquire'])\n"
           "    return requests.get(u)\nload('https://www.facebook.com/x')\n")
PARSER = fx("extract.py", "import re,sys\nprint(re.findall(r'facebook\\.com/[^\"]+', "
            "open(sys.argv[1]).read()))\n")
PAYLOAD = fx("contact.json", json.dumps({"website": "https://facebook.com/x"}))
PY_LOADER = fx("fbloop.py", "import urllib.request\nfor u in open('x'):\n"
               "    urllib.request.urlopen(u)\n")
HELPER_DIR = os.path.join(T, "pkg")
os.makedirs(HELPER_DIR)
fx("pkg/helper.py", "import requests\nFB='https://www.facebook.com/'\n"
   "def get(u):\n    return requests.get(FB + u)\n")
PY_IMPORTER = fx("pkg/main.py", "import helper\nprint('go')\n")
os.makedirs(os.path.join(T, "tests"))
OFFLINE_TEST = fx("tests/test_lane.py", "import urllib.request\nFIX = 'https://www.facebook.com/x'\n"
                  "PS = '--remote-debugging-port=9222'\n")
LIVE_TEST = fx("tests/test_lane_live.py", "import urllib.request\n"
               "urllib.request.urlopen('https://www.facebook.com/x')\n")
CLASSIFIER = fx("norm.mjs", "export const SOCIAL = ['facebook.com', 'linkedin.com', 'x.com'];\n"
                "export async function geo(q) { return fetch('https://maps.example.com/' + q); }\n")
fx("lib-norm.mjs", "export const li = (a) => `https://www.linkedin.com/in/${a}`;\n")
fx("lib-api.mjs", "export const run = (q) => fetch('https://api.apify.com/v2/x?q=' + q);\n")
MERGE = fx("merge.mjs", "import { li } from './lib-norm.mjs';\nimport { run } from './lib-api.mjs';\n")
MAILER = fx("mailer.py", "import urllib.request\nFREE = {'gmail.com', 'x.com'}\n"
            "OWNER = 'someone@linkedin.com'\nurllib.request.urlopen('https://example.com')\n")
# a review file that NAMES social homepages as findings (the 2026-09-28 amiron REVIEW.md):
# prose + URLs, no code. Sending it or editing it is not a page load.
fx("REVIEW.md", "CRO review. They point to the bare homepages https://facebook.com "
   "https://instagram.com https://x.com https://linkedin.com https://tiktok.com and "
   "https://www.threads.net/@acct as findings.\n")
DASH = os.path.expanduser("~/.claude/scripts/dash-check.sh")

CASES = []


def case(label, cmd, expected):
    CASES.append((label, cmd, expected))


# ------------------------------------------------------------------ allowed
case("unrelated ls", "ls -la ~/dev", "allow")
case("git status", "git status", "allow")
case("grep a social host in a csv", "grep -c facebook.com /tmp/prospects.csv", "allow")
case("sqlite count of social urls", "sqlite3 /tmp/h.db \"select count(*) from urls where "
     "url like '%facebook.com%'\"", "allow")
case("echo a social url", "echo " + FB, "allow")
case("commit message naming curl and facebook",
     'git commit -m "route curl loads of facebook.com through the gate"', "allow")
case("gate acquire alone", G + " acquire --url " + FB + " --actor t", "allow")
case("gate check alone", GT + " check --url " + FB, "allow")
case("gate status", GT + " status", "allow")
case("PAIRED: acquire && one curl", G + " acquire --url " + FB + " --actor t && curl -s "
     + FB + " -o /tmp/p.html", "allow")
case("PAIRED: tilde gate path", GT + " acquire --url " + FB + " --actor t && curl -s " + FB,
     "allow")
case("PAIRED: $HOME gate path", "python3 $HOME/.claude/scripts/social-gate.py acquire --url "
     + FB + " --actor t && curl -s " + FB, "allow")
case("PAIRED: with 2>&1 redirect", G + " acquire --url " + FB + " --actor t 2>&1 && curl -s "
     + FB + " 2>/dev/null", "allow")
case("PAIRED: fb.com load with a facebook acquire", G + " acquire --url " + FB +
     " --actor t && curl -s https://fb.com/x", "allow")
case("PAIRED remote: renderer with a remote acquire", G + " acquire --url " + FB +
     " --actor r --route remote && curl -s -X POST " + CF + " -d '{\"url\": \"" + FB + "\"}'",
     "allow")
case("PAIRED remote: renderer with a LOCAL acquire (stricter budget)", G + " acquire --url "
     + FB + " --actor r && curl -s -X POST " + CF + " -d '{\"url\": \"" + FB + "\"}'", "allow")
case("PAIRED: one page reader script with one url", G + " acquire --url " + FB +
     " --actor t && node " + READER + " " + FB, "allow")
case("PAIRED inside a loop: every iteration acquires",
     "for u in a b; do " + G + " acquire --url https://www.facebook.com/$u --actor t && "
     "curl -s https://www.facebook.com/$u; done", "allow")
case("curl a business site then grep its facebook link",
     "curl -s https://example.com/ | grep -o 'facebook.com/[^\"]*'", "allow")
case("curl a site then htmlq for the facebook link",
     "curl -s https://example.com/ | htmlq 'a[href*=\"facebook.com\"]' --attribute href",
     "allow")
case("curl to a non social API with a social URL as data",
     "curl -s -X POST https://services.leadconnectorhq.com/contacts -d '{\"website\":\"" + FB
     + "\"}'", "allow")
case("curl to a non social API with a payload file", "curl -s -X POST "
     "https://services.leadconnectorhq.com/contacts -d @" + PAYLOAD, "allow")
case("9222 without a social host (GHL work)", "curl -s localhost:9222/json/version", "allow")
case("a gated script", "python3 " + GATED, "allow")
case("a parser script with no fetch primitive", "python3 " + PARSER + " /tmp/page.html",
     "allow")
case("a page reader script with a non social url", "node " + READER + " https://example.com",
     "allow")
case("heredoc prose that names facebook", "cat > /tmp/notes.md <<'EOF'\nOwner found at "
     "facebook.com/x\nEOF", "allow")
case("commit heredoc naming curl and facebook with the gate",
     "git commit -m \"$(cat <<'EOF'\nsocial-gate: curl to facebook.com now paced\nEOF\n)\"",
     "allow")
case("schedule entry for the audit", "node ~/dev/claude-telegram-bridge/schedule.mjs add "
     "daily 08:15 \"Run python3 ~/.claude/scripts/social-load-audit.py --alert\" --run", "allow")
case("the guard's own suite", "python3 ~/.claude/hooks/social-pace-guard.test.py", "allow")
case("the audit script", "python3 ~/.claude/scripts/social-load-audit.py --json", "allow")
case("curl with an unrelated variable", "curl -s \"$SUPABASE_URL/rest/v1/x\" -H "
     "\"apikey: $KEY\"", "allow")
case("npm install style third party run", "npx -y vercel --version", "allow")
case("Graph API call (the BU ads check)", "curl -s \"https://graph.facebook.com/v21.0/act_1/"
     "insights?access_token=$META_ADS_TOKEN\"", "allow")
case("Graph API one liner", "python3 -c \"import json,subprocess; print('graph.facebook.com')\"",
     "allow")
case("graph host does not launder a page load", "curl -s https://graph.facebook.com/x && "
     "curl -s " + FB, "deny")

# ------------------------------------------------------------------ denied: plain
case("bare curl", "curl -s " + FB, "deny")
case("wget instagram", "wget https://www.instagram.com/someone/", "deny")
case("curl linkedin quoted", "curl -s \"" + LI + "\"", "deny")
case("httpie", "http GET " + FB, "deny")
case("open in default browser", "open " + FB, "deny")
case("open -a Chrome", "open -a \"Google Chrome\" " + FB, "deny")
case("osascript open location", "osascript -e 'tell application \"Google Chrome\" to open "
     "location \"" + FB + "\"'", "deny")
case("python one liner", "python3 -c \"import urllib.request; urllib.request.urlopen('" + FB
     + "')\"", "deny")
case("node one liner", "node -e \"fetch('" + FB + "')\"", "deny")
case("python -m webbrowser", "python3 -m webbrowser " + FB, "deny")
case("yt-dlp tiktok", "yt-dlp https://www.tiktok.com/@x/video/1", "deny")
case("npx playwright screenshot", "npx playwright screenshot " + FB + " /tmp/o.png", "deny")
case("headless chromium", "chromium --headless --dump-dom " + FB, "deny")
case("Chrome binary by path", "\"/Applications/Google Chrome.app/Contents/MacOS/Google "
     "Chrome\" --headless --dump-dom " + FB, "deny")
case("x.com via wget", "wget -q -O - https://x.com/someone", "deny")
case("threads.com", "curl https://www.threads.com/@someone", "deny")
case("m.facebook.com", "curl https://m.facebook.com/x", "deny")
case("messenger.com", "curl https://www.messenger.com/t/1", "deny")
case("wrapped in nohup and timeout", "nohup gtimeout 30 curl -s " + FB, "deny")
case("env prefix", "env HTTPS_PROXY=x curl -s " + FB, "deny")

# ------------------------------------------------------------------ denied: pairing rules
case("acquire ; curl (not &&)", G + " acquire --url " + FB + " --actor t ; curl " + FB, "deny")
case("acquire || curl", G + " acquire --url " + FB + " --actor t || curl " + FB, "deny")
case("acquire && sleep && curl (not direct)", G + " acquire --url " + FB +
     " --actor t && sleep 1 && curl " + FB, "deny")
case("one acquire, two loads", G + " acquire --url " + FB + " --actor t && curl " + FB +
     " && curl " + FB2, "deny")
case("one acquire, one curl of two urls", G + " acquire --url " + FB + " --actor t && curl "
     + FB + " " + FB2, "deny")
case("curl URL globbing", G + " acquire --url " + FB + " --actor t && curl "
     "\"https://www.facebook.com/p[1-50]\"", "deny")
case("curl brace list", G + " acquire --url " + FB + " --actor t && curl "
     "\"https://www.facebook.com/{a,b,c}\"", "deny")
case("curl --parallel", G + " acquire --url " + FB + " --actor t && curl -Z " + FB, "deny")
case("platform mismatch", G + " acquire --url " + LI + " --actor t && curl " + FB, "deny")
case("remote acquire for a direct local load", G + " acquire --url " + FB +
     " --actor t --route remote && curl " + FB, "deny")
case("--grant chained with a load", G + " acquire --url " + FB + " --actor t --grant && curl "
     + FB, "deny")
case("a copy of the gate elsewhere", "cp " + GATE + " /tmp/social-gate.py; python3 "
     "/tmp/social-gate.py acquire --url " + FB + " --actor t && curl " + FB, "deny")
case("gate mentioned in an echo only", "echo social-gate.py acquire && curl " + FB, "deny")
case("unpaced remote renderer", "curl -s -X POST " + CF + " -d '{\"url\": \"" + FB + "\"}'",
     "deny")
case("renderer payload naming two profiles", G + " acquire --url " + FB + " --actor r "
     "--route remote && curl -s -X POST " + CF + " -d '{\"urls\": [\"" + FB + "\", \"" + FB2
     + "\"]}'", "deny")

# ------------------------------------------------------------------ denied: bypass shapes
case("bash -c", "bash -c \"curl -s " + FB + "\"", "deny")
case("sh -c", "sh -c 'curl -s " + FB + "'", "deny")
case("zsh -lc", "zsh -lc 'curl -s " + FB + "'", "deny")
case("bash --norc -c", "bash --norc -c 'curl -s " + FB + "'", "deny")
case("eval", "eval \"curl -s " + FB + "\"", "deny")
case("gate outside, load inside bash -c", G + " acquire --url " + FB + " --actor t && bash "
     "-c 'curl -s " + FB + "'", "deny")
case("alias", "alias c=curl; c -s " + FB, "deny")
case("function", "f(){ curl -s \"$1\"; }; f " + FB, "deny")
case("function keyword", "function g { curl -s \"$1\"; }; g " + FB, "deny")
case("env var holds the url", "U=" + FB + "; curl -s \"$U\"", "deny")
case("export holds the host", "export H=facebook.com; curl -s \"https://www.$H/x\"", "deny")
case("host split across a variable", "H=face; curl -s \"https://www.${H}book.com/x\"", "deny")
case("quote splicing", "curl -s \"https://www.face\"\"book.com/x\"", "deny")
case("line continuation", "curl -s \\\n  " + FB, "deny")
case("herestring into a variable", "read -r U <<< \"" + FB + "\"; curl -s \"$U\"", "deny")
case("heredoc fed to bash", "bash <<'EOF'\ncurl -s " + FB + "\nEOF", "deny")
case("heredoc fed to python", "python3 - <<'EOF'\nimport urllib.request\n"
     "urllib.request.urlopen('" + FB + "')\nEOF", "deny")
case("heredoc fed to node", "node <<'EOF'\nfetch('" + FB + "')\nEOF", "deny")
case("heredoc writes a loader", "cat > /tmp/l.sh <<'EOF'\nfor u in a b; do curl -s "
     "https://www.facebook.com/$u; done\nEOF", "deny")
case("heredoc writes a loader then runs it", "cat > /tmp/l.sh <<'EOF'\ncurl -s " + FB +
     "\nEOF\nbash /tmp/l.sh", "deny")
case("echo piped into bash", "echo 'curl -s " + FB + "' | bash", "deny")
case("script fed by redirect", "bash < " + LOADER_SH, "deny")
case("backticks around a url file", "curl -s `cat " + ONE_URL + "`", "deny")
case("command substitution of a url file", "curl -s \"$(head -1 " + ONE_URL + ")\"", "deny")

# ------------------------------------------------------------------ denied: bulk
case("for loop", "for u in a b c; do curl -s https://www.facebook.com/$u; done", "deny")
case("brace range", "for i in {1..50}; do curl -s https://www.facebook.com/p$i; done", "deny")
case("while read from a url file", "while read u; do curl -s \"$u\"; done < " + URLS, "deny")
case("cat | xargs curl", "cat " + URLS + " | xargs -n1 curl -s", "deny")
case("xargs -a", "xargs -a " + URLS + " -n1 -P4 curl -s", "deny")
case("parallel", "parallel curl -s ::: " + FB + " " + FB2, "deny")
case("watch", "watch -n 60 curl -s " + FB, "deny")
case("find -exec", "find . -name '*.txt' -exec curl -s https://www.facebook.com/{} \\;",
     "deny")
case("wget -i url list", "wget -i " + URLS, "deny")
case("wget recursive", G + " acquire --url " + FB + " --actor t && wget -r " + FB, "deny")
case("curl -K config", "curl -K " + URLS, "deny")
case("gated acquire then an xargs fan out", G + " acquire --url " + FB + " --actor t && cat "
     + URLS + " | xargs -n1 curl -s", "deny")

# ------------------------------------------------------------------ denied: scripts
case("THE INCIDENT: CDP reader on 9222", "node " + CDP + " " + FB + " 7000", "deny")
case("the incident, even gated", G + " acquire --url " + FB + " --actor t && node " + CDP +
     " " + FB, "deny")
case("the incident via cd and a relative path", "cd " + T + " && node cdp-read.mjs " + FB,
     "deny")
case("batch script importing a 9222 helper, fed a worklist", "node " + CDP_IMPORT + " " +
     WORKLIST, "deny")
case("script with a hardcoded social load", "node " + LOADER_JS, "deny")
case("script with a hardcoded load, even gated", G + " acquire --url " + FB + " --actor t && "
     "node " + LOADER_JS, "deny")
case("shell script run by path", "bash " + LOADER_SH, "deny")
case("executable by path", LOADER_SH, "deny")
case("page reader fed a url file", "node " + READER + " " + URLS, "deny")
case("page reader handed two urls", "node " + READER + " " + FB + " " + FB2, "deny")
case("page reader handed one url, unpaced", "node " + READER + " " + FB, "deny")
case("python loop fed a url list", "python3 " + PY_LOADER + " " + URLS, "deny")
case("python script whose local import names the host", "python3 " + PY_IMPORTER, "deny")
case("npx tsx on a loader", "npx tsx " + LOADER_JS, "deny")
case("an offline test naming social fixtures and 9222", "python3 " + OFFLINE_TEST, "allow")
case("a LIVE test that loads a social page", "python3 " + LIVE_TEST, "deny")
case("an offline test handed a social url file", "python3 " + OFFLINE_TEST + " " + URLS, "deny")
case("a classifier with a bare domain list and a non social fetch", "node " + CLASSIFIER,
     "allow")
case("an email address and a bare domain are not pages", "python3 " + MAILER, "allow")
case("a link builder module and a separate fetch module", "node " + MERGE, "allow")

# ------------------------------------------------------------------ denied: 9222 always
case("CDP new tab with a social url", "curl -s \"localhost:9222/json/new?" + FB + "\"", "deny")
case("CDP port env with a social url", "CDP_PORT=9222 node " + READER + " " + FB, "deny")
# QA round 1: naming both in a read only grep is not a load; a social host in an
# EXECUTING part next to 9222 is (next cases)
case("9222 check next to a grep that names facebook", "grep -c facebook.com /tmp/x; curl -s "
     "localhost:9222/json", "allow")
case("9222 in one curl, a social load in the next", "curl -s localhost:9222/json; curl -s "
     + FB, "deny")
case("grep for 9222 piped to a grep for facebook", "grep -rn 'localhost:9222' ~/dev/x | "
     "grep -c facebook.com", "allow")
case("blueprint profile dir with a social url", "open -na 'Google Chrome' --args "
     "--user-data-dir=$HOME/.blueprint-chrome-profile " + FB, "deny")
case("9222 in a heredoc with a social url", "node <<'EOF'\nconst v = await fetch("
     "'http://127.0.0.1:9222/json/version'); // then open " + FB + "\nEOF", "deny")

# ------------------------------------------------------------------ denied: schedules
# schedule.mjs --run entries execute through Claude or Codex, where this hook runs
# again at fire time; a plain reminder is only text sent to Zalo
case("bridge schedule text naming a social page (checked at fire time)",
     "node ~/dev/claude-telegram-bridge/schedule.mjs add daily 09:00 \"open "
     "linkedin.com/in/zalo and post\"", "allow")
case("crontab via echo pipe", "(crontab -l; echo \"0 * * * * curl -s " + FB + "\") | "
     "crontab -", "deny")
case("at job", "echo \"curl -s " + FB + "\" | at now + 1 hour", "deny")
case("LaunchAgent plist by heredoc", "cat > ~/Library/LaunchAgents/com.x.fb.plist <<'EOF'\n"
     "<string>curl -s " + FB + "</string>\nEOF", "deny")
case("launchctl submit", "launchctl submit -l fb -- curl -s " + FB, "deny")

# ---------------------------------------------------------------- allowed: two fixes 09-28
# (1) An upload to a sink host (Telegram Bot API) does not read a file passed as a body /
# multipart field as a URL list. Each of these was BLOCKED by the old hook (the ${TOK}
# variable made it read every command token as a data file, and REVIEW.md named 7 socials).
# (2) An offline script (no network / process / dynamic-loading capability) is not a load
# just because it holds social URL strings.
case("SINK: telegram upload of a file naming socials (block 1)",
     'curl -s -F document=@REVIEW.md -F caption="numbers match REVIEW.md" '
     '"https://api.telegram.org/bot${TOK}/sendDocument"', "allow")
case("SINK: telegram -T upload of a social-naming file",
     'curl -s -T REVIEW.md -F caption="see REVIEW.md" '
     '"https://api.telegram.org/bot${TOK}/sendDocument"', "allow")
case("SINK: telegram --data-binary @file, literal host",
     "curl -s --data-binary @REVIEW.md https://api.telegram.org/bot123:ABC/sendDocument",
     "allow")
case("SINK: telegram media group, two -F @png plus a caption naming REVIEW.md",
     "curl -s -F 'media=[{\"type\":\"photo\",\"media\":\"attach://a\",\"caption\":\"list in "
     "REVIEW.md\"}]' -F a=@REVIEW.md \"https://api.telegram.org/bot${TOK}/sendMediaGroup\"",
     "allow")
case("OFFLINE: heredoc rewrites a review naming socials, then greps and dash-checks it (block 2)",
     "python3 - <<'EOF'\ns=open('REVIEW.md').read()\n"
     "for a,b in [('https://facebook.com','Facebook'),('https://instagram.com','Instagram'),"
     "('https://x.com','X'),('https://linkedin.com','LinkedIn'),('https://tiktok.com','TikTok')]:\n"
     "    s=s.replace(a,b)\nopen('REVIEW-phone.md','w').write(s)\nEOF\n"
     "grep -c -i facebook REVIEW-phone.md; bash " + DASH + " REVIEW-phone.md | tail -1", "allow")
case("OFFLINE: python -c editing a file naming socials", "python3 -c \"s=open('REVIEW.md')"
     ".read().replace('https://facebook.com','FB'); open('REVIEW-phone.md','w').write(s)\"",
     "allow")

# ---------------------------------------------------------- the sink allowance stays narrow
case("SINK guard: the same upload shape to a NON sink host is still covered",
     'curl -s -F document=@REVIEW.md -F caption="numbers match REVIEW.md" '
     '"https://render.example.com/bot${TOK}/x"', "deny")
case("SINK guard: a sink host through an unresolved variable is not trusted",
     'curl -s -F document=@REVIEW.md -F caption="see REVIEW.md" '
     '"https://${SINK}/bot${TOK}/sendDocument"', "deny")
case("SINK guard: --resolve host remap disables the sink allowance",
     'curl -s --resolve api.telegram.org:443:1.2.3.4 -F document=@REVIEW.md '
     '-F caption="numbers match REVIEW.md" "https://api.telegram.org/bot${TOK}/sendDocument"',
     "deny")
case("SINK guard: a telegram upload AND a social destination in one command",
     'curl -s -F document=@REVIEW.md -F caption="match REVIEW.md" '
     '"https://api.telegram.org/bot${TOK}/sendDocument" ' + FB, "deny")
case("SINK guard: -K config of social urls even with a telegram target",
     "curl -s -K " + URLS + " https://api.telegram.org/bot1/sendMessage", "deny")

# ------------------------------------------------ the offline allowance stays capability-gated
case("OFFLINE guard: heredoc __import__ builds a fetch",
     "python3 - <<'EOF'\n__import__('urllib.request').urlopen('" + FB + "')\nEOF", "deny")
case("OFFLINE guard: heredoc exec of fetch code",
     "python3 - <<'EOF'\nexec(\"import urllib.request as u; u.urlopen('" + FB + "')\")\nEOF",
     "deny")
case("OFFLINE guard: heredoc importlib import_module fetch",
     "python3 - <<'EOF'\nimport importlib\nimportlib.import_module('urllib.request')"
     ".urlopen('" + FB + "')\nEOF", "deny")
case("OFFLINE guard: heredoc subprocess.run curl",
     "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['curl','" + FB + "'])\nEOF", "deny")
case("OFFLINE guard: heredoc os.system curl",
     "python3 - <<'EOF'\nimport os\nos.system('curl " + FB + "')\nEOF", "deny")
case("OFFLINE guard: offline heredoc writes a URL list, then wget -i reads it (virtual)",
     "python3 - <<'EOF'\nopen('u.txt','w').write('" + FB + "\\n" + FB2 + "')\nEOF\nwget -i u.txt",
     "deny")
case("OFFLINE guard: offline heredoc writes a curl config, then curl -K reads it (virtual)",
     "python3 - <<'EOF'\nopen('c.txt','w').write('url = \"" + FB + "\"')\nEOF\ncurl -s -K c.txt",
     "deny")
case("OFFLINE guard: offline heredoc writes a loader shell script, then runs it (virtual)",
     "python3 - <<'EOF'\nopen('l.sh','w').write('curl -s " + FB + "')\nEOF\nbash l.sh", "deny")
# QA 2026-09-29 CRITICALs: a write to a path the guard cannot resolve is untrackable, and a
# split fetch word reaches offline_code() yet writes a working loader. Both must fail closed.
case("OFFLINE guard: computed write name (concat) then wget -i (untrackable)",
     "python3 - <<'EOF'\nn='u'+'.txt'\nopen(n,'w').write('" + FB + "')\nEOF\nwget -i u.txt",
     "deny")
case("OFFLINE guard: f-string write path then curl -K (untrackable)",
     "python3 - <<'EOF'\ni=1\nopen(f'c{i}.txt','w').write('url = \"" + FB + "\"')\nEOF\n"
     "curl -s -K c1.txt", "deny")
case("OFFLINE guard: os.path.join write path then source (untrackable)",
     "python3 - <<'EOF'\nimport os\nd='.'\nopen(os.path.join(d,'ld.sh'),'w').write('cur'+'l -s "
     + FB + "')\nEOF\nsource ld.sh", "deny")
case("OFFLINE guard: split fetch word, literal path, then bash (poison, not the body)",
     "python3 - <<'EOF'\nopen('l.sh','w').write('cur'+'l -s " + FB + "')\nEOF\nbash l.sh", "deny")
case("OFFLINE guard: rename to a computed target then wget -i (untrackable)",
     "python3 - <<'EOF'\nimport os\nopen('t','w').write('" + FB + "')\nos.rename('t','o'+'.txt')\n"
     "EOF\nwget -i o.txt", "deny")
case("OFFLINE guard: node computed writeFileSync then wget -i (untrackable)",
     "node <<'EOF'\nconst fs=require('fs');const n='u'+'.txt';fs.writeFileSync(n,'" + FB + "')\n"
     "EOF\nwget -i u.txt", "deny")
# QA 2026-09-29 round 2 (independent verifier): the literal-path tracking was leaky by six
# routes. The fix poisons ANY not-on-disk path a later stage runs/fetches once an offline
# social-naming program has run, so all six close the same way. Each was DENY on the pre-fix
# hook of this same commit series and must stay DENY.
case("OFFLINE guard: header redirect > writes the loader, print builds it, then bash",
     "python3 - > l.sh <<'EOF'\nprint('open " + FB + "')\nEOF\nbash l.sh", "deny")
case("OFFLINE guard: | tee writes the loader then bash",
     "python3 - <<'EOF' | tee l.sh\nprint('cur'+'l -s " + FB + "')\nEOF\nbash l.sh", "deny")
case("OFFLINE guard: os.chdir moves where the write lands, then bash",
     "python3 - <<'EOF'\nimport os\nos.chdir('/tmp')\nopen('l.sh','w').write('cur'+'l -s "
     + FB + "')\nEOF\nbash /tmp/l.sh", "deny")
case("OFFLINE guard: os.open + os.write (uncounted write) then bash",
     "python3 - <<'EOF'\nimport os\nfd=os.open('l.sh',os.O_WRONLY|os.O_CREAT)\n"
     "os.write(fd,b'cur'+b'l -s " + FB + "')\nEOF\nbash l.sh", "deny")
case("OFFLINE guard: case-folded write name (L.SH) then bash l.sh",
     "python3 - <<'EOF'\nopen('L.SH','w').write('cur'+'l -s " + FB + "')\nEOF\nbash l.sh", "deny")
case("OFFLINE guard: subshell cd then write then bash",
     "(cd sub && python3 - <<'EOF'\nopen('l.sh','w').write('cur'+'l -s " + FB + "')\n"
     "EOF\nbash l.sh)", "deny")
case("OFFLINE guard: python -c writes a loader then bash (inline offline)",
     "python3 -c \"open('l.sh','w').write('cur'+'l -s " + FB + "')\" && bash l.sh", "deny")
case("OFFLINE guard: node -e writes a loader then bash (inline offline)",
     "node -e \"require('fs').writeFileSync('l.sh','cur'+'l -s " + FB + "')\" && bash l.sh",
     "deny")
# QA 2026-09-29 round 3: a loader NAMED after a PATH executable (grep, node, sed) still runs
# from cwd via `bash grep` / `source ./grep`; the PATH-executable carve-out on poison must not
# apply to an execution / fetch TARGET (only to a bare command name a broad scan picks up).
case("OFFLINE guard: loader named after a PATH command, run by bash",
     "python3 - <<'EOF'\nopen('grep','w').write('cur'+'l -s " + FB + "')\nEOF\nbash grep", "deny")
case("OFFLINE guard: loader named after a PATH command, sourced",
     "python3 - <<'EOF'\nopen('node','w').write('cur'+'l -s " + FB + "')\nEOF\nsource ./node",
     "deny")
case("OFFLINE guard: URL list named after a PATH command, wget -i",
     "python3 - <<'EOF'\nopen('sed','w').write('" + FB + "')\nEOF\nwget -i sed", "deny")
# QA 2026-09-29 round 4: the PATH-name loader also reaches an interpreter through a PIPE
# (cat grep | bash) and a fan out (cat grep | xargs curl); every broad file scan now drops
# the command HEAD and reads the ARG tokens strict=True, so a PATH-named data/loader file is
# still poisoned while the command name is not.
case("OFFLINE guard: PATH-named loader piped into a shell (cat grep | bash)",
     "python3 - <<'EOF'\nopen('grep','w').write('curl -s " + FB + "')\nEOF\ncat grep | bash",
     "deny")
case("OFFLINE guard: PATH-named loader piped into sh (cat sed | sh)",
     "python3 - <<'EOF'\nopen('sed','w').write('curl -s " + FB + "')\nEOF\ncat sed | sh", "deny")
case("OFFLINE guard: PATH-named URL list through a fan out (cat grep | xargs curl)",
     "python3 - <<'EOF'\nopen('grep','w').write('" + FB + "')\nEOF\ncat grep | xargs -I{} "
     "curl -s {}", "deny")
# and the carve-out still works: an offline program followed by a harmless command whose head
# is a PATH executable reading nothing off disk is not blocked (no false positive)
case("OFFLINE: offline heredoc then a harmless echo|xargs echo (command names not poisoned)",
     "python3 - <<'EOF'\nopen('out.md','w').write(open('REVIEW.md').read().replace('" + FB
     + "','x'))\nEOF\necho hi | xargs echo", "allow")
# and the allowance still stands: an offline program's output consumed only as DATA by an
# existing no-fetch tool (grep is safe; a scanned script with no fetch of its own) is allowed
case("OFFLINE: offline heredoc output consumed as a data arg by an existing no-fetch script",
     "python3 - <<'EOF'\nopen('out.md','w').write(open('REVIEW.md').read().replace('"
     + FB + "','x'))\nEOF\ngrep -c x out.md; wc -l out.md", "allow")


def fresh_ctx(**overrides):
    d = tempfile.mkdtemp(prefix="spg-gate-")
    cfg = json.load(open(REAL_CFG))
    for route, vals in overrides.items():
        cfg["routes"][route].update(vals)
    path = os.path.join(d, "cfg.json")
    json.dump(cfg, open(path, "w"))
    clk = sg.FakeClock(1790460000.0)
    gate = sg.Gate(config_path=path, state_dir=os.path.join(d, "state"), clock=clk,
                   rng=random.Random(3))
    return hk.Ctx(gate=gate, cwd=T, claude_json=os.path.join(d, "claude.json")), gate, clk, d


def run_bash(cmd, ctx=None):
    ctx = ctx or fresh_ctx()[0]
    return hk.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": T}, ctx)


PASS = FAIL = 0


def ok(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL  %s %s" % (label, detail))


print("A  Bash table (%d cases)" % len(CASES))
for label, cmd, expected in CASES:
    allowed, msg = run_bash(cmd)
    got = "allow" if allowed else "deny"
    ok(got == expected, "%s -> %s" % (label, expected), "(got %s) %s" % (got, msg[:160]))

print("B  grants and pairing against a real (temp) gate")
ctx, gate, clk, d = fresh_ctx()
ok(not run_bash("curl -s " + FB, ctx)[0], "no grant: a lone curl is refused")
gate.acquire(FB, "t", grant=True)
ok(run_bash("curl -s " + FB, ctx)[0], "after acquire --grant: one lone curl passes")
ok(not run_bash("curl -s " + FB, ctx)[0], "the grant is spent after one use")
clk.t += 1000
gate.acquire(FB, "t", grant=True)
ok(not run_bash("for u in a b; do curl -s https://www.facebook.com/$u; done", ctx)[0],
   "a grant never opens a loop")
ok(not run_bash("curl -s " + LI, ctx)[0], "a facebook grant does not open linkedin")
ok(run_bash("curl -s " + FB, ctx)[0], "the facebook grant is still there for facebook")
msg = run_bash("curl -s " + FB, ctx)[1]
ok("Gate now:" in msg and "facebook local" in msg, "a refusal names the gate state", msg[:200])
ok("40" in msg and "150" in msg, "a refusal names the caps")

print("C  browser tools")


def nav(ctx, url, tool="mcp__playwright__browser_navigate", sid="abc12345"):
    return hk.decide({"tool_name": tool, "tool_input": {"url": url}, "session_id": sid}, ctx)


ctx, gate, clk, d = fresh_ctx()
ok(nav(ctx, "https://example.com")[0], "navigate to a non social page passes")
ok(nav(ctx, FB)[0], "first social navigate passes and takes a slot")
rows = [json.loads(x) for x in open(gate.ledger_path)]
ok(len(rows) == 1 and rows[0]["via"].startswith("hook:") and rows[0]["host"] ==
   "www.facebook.com", "the hook wrote one ledger row, host only", str(rows))
allowed, msg = nav(ctx, FB2)
ok(not allowed and "WAIT" in msg and "--grant" in msg,
   "second navigate right away is refused with the wait and the grant hint", msg[:200])
ok(len([1 for _ in open(gate.ledger_path)]) == 1, "a refused navigate writes nothing")
ok(nav(ctx, LI)[0], "linkedin has its own budget")
clk.t += 30
gate_d = gate.acquire(FB, "agent", max_wait=10 ** 6, grant=True)
ok(gate_d.code == 0, "acquire --grant waits out the gap on the fake clock")
n_before = len(open(gate.ledger_path).read().splitlines())
ok(nav(ctx, FB2)[0], "the navigate after the grant passes")
ok(len(open(gate.ledger_path).read().splitlines()) == n_before,
   "and does not take a second slot")
# bulk through the browser: 60 navigations, 10 fake seconds apart
ctx, gate, clk, d = fresh_ctx()
passed = []
for i in range(60):
    if nav(ctx, "https://www.facebook.com/p%d" % i)[0]:
        passed.append(clk.t)
    clk.t += 10
gaps = [b - a for a, b in zip(passed, passed[1:])]
ok(len(passed) < 60 and (not gaps or min(gaps) >= 45),
   "60 navigations 10 s apart: only paced ones pass (%d passed, min gap %s)" % (
       len(passed), min(gaps) if gaps else "n/a"))
ctx, gate, clk, d = fresh_ctx()
ok(hk.decide({"tool_name": "WebFetch", "tool_input": {"url": FB, "prompt": "x"}}, ctx)[0],
   "WebFetch of one social page takes a slot")
ok(not hk.decide({"tool_name": "WebFetch", "tool_input": {"url": FB2, "prompt": "x"}}, ctx)[0],
   "a second WebFetch right away is refused")
code_loop = "async (page) => { for (const u of ['" + FB + "','" + FB2 + "']) await page.goto(u); }"
ok(not hk.decide({"tool_name": "mcp__playwright__browser_run_code_unsafe",
                  "tool_input": {"code": code_loop}}, fresh_ctx()[0])[0],
   "run_code looping over social urls is refused")
ok(not hk.decide({"tool_name": "mcp__playwright__browser_run_code_unsafe",
                  "tool_input": {"code": "async (page) => { for (let i=0;i<50;i++) await "
                                 "page.goto('https://www.facebook.com/p'+i) }"}},
                 fresh_ctx()[0])[0], "run_code with a for loop and one social url is refused")
ok(hk.decide({"tool_name": "mcp__playwright__browser_evaluate",
              "tool_input": {"function": "() => [...document.querySelectorAll("
                             "'a[href*=\"facebook.com\"]')].map(a => a.href)"}},
             fresh_ctx()[0])[0], "evaluate that only reads facebook links passes")
ok(hk.decide({"tool_name": "mcp__playwright__browser_click",
              "tool_input": {"element": "facebook.com link", "ref": "e1"}},
             fresh_ctx()[0])[0], "a click is not a URL tool (stated limit)")
ok(not hk.decide({"tool_name": "mcp__playwright__browser_navigate",
                  "tool_input": {"url": "http://localhost:9222/json/new?" + FB}},
                 fresh_ctx()[0])[0], "navigate through a 9222 URL is refused")
ctx9, gate9, _, d9 = fresh_ctx()
json.dump({"mcpServers": {"playwright": {"command": "npx", "args": [
    "@playwright/mcp@latest", "--cdp-endpoint", "http://localhost:9222"]}}},
    open(ctx9.claude_json, "w"))
ok(not nav(ctx9, FB)[0], "Playwright MCP attached to 9222: social navigate always refused")
ok(nav(ctx9, "https://app.gohighlevel.com/")[0], "and GHL navigation there still passes")
ctx1, g1, c1, _ = fresh_ctx(local={"per_day": 1})
ok(nav(ctx1, FB, tool="mcp__claude-in-chrome__navigate")[0] and not
   nav(ctx1, FB2, tool="mcp__claude-in-chrome__navigate")[0],
   "claude-in-chrome navigate spends the same daily budget")

print("D  fail closed")
bad = hk.Ctx(gate=None, cwd=T)
bad.cfg, bad.cfg_error = None, "cannot read config"
allowed, msg = hk.decide({"tool_name": "Bash", "tool_input": {"command": G + " acquire --url "
                          + FB + " --actor t && curl " + FB}}, bad)
ok(not allowed and "cannot run" in msg, "unreadable config: even a paired load is refused")
ok(hk.decide({"tool_name": "Bash", "tool_input": {"command": "ls"}}, bad)[0],
   "unreadable config: unrelated commands still pass")
ctx, gate, clk, d = fresh_ctx()
c = json.load(open(gate.config_path))
c["gap_model"] = "/nonexistent/governor.py"
json.dump(c, open(gate.config_path, "w"))
ok(not nav(ctx, FB)[0], "missing gap model: browser load refused")
src = open(HOOK).read()
ok("os.environ" not in src and "getenv" not in src, "the hook reads no environment variable")

print("E  the real hook over stdin (shapes that never touch the gate state)")


def stdin_case(label, payload, want):
    r = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30)
    ok(r.returncode == want, label, "exit %d stderr %s" % (r.returncode, r.stderr[:200]))
    return r


stdin_case("ls passes", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, 0)
r = stdin_case("the incident shape is blocked", {"tool_name": "Bash", "tool_input": {
    "command": "node " + CDP + " " + FB}, "cwd": T}, 2)
ok("BLOCKED (social-pace-guard)" in r.stderr and "9222" in r.stderr, "with a readable reason")
stdin_case("a loop is blocked", {"tool_name": "Bash", "tool_input": {
    "command": "for u in a b; do curl -s https://www.facebook.com/$u; done"}}, 2)
stdin_case("a non social navigate passes", {"tool_name": "mcp__playwright__browser_navigate",
                                            "tool_input": {"url": "https://example.com"}}, 0)
stdin_case("an unrelated tool passes", {"tool_name": "Read", "tool_input": {
    "file_path": "/tmp/x"}}, 0)
stdin_case("garbage payload passes (not a command)", "not json", 0)

print("F  QA round 1 regressions (each was ALLOWED by the first cut)")
SUB = os.path.join(T, "sub")
os.makedirs(SUB, exist_ok=True)
fx("sub/read.mjs", "const r = await fetch(process.argv[2]);\n")
fx("urls-rel.txt", FB + "\n" + FB2 + "\n")
fx("Makefile", "all:\n\tcurl -s https://www.facebook.com/a\n\tcurl -s https://www.facebook.com/b\n")
fx("run.command", "#!/bin/bash\ncurl -s https://www.facebook.com/x\n")
R1 = [
    ("cd into a dir, then a relative reader with a social url", "cd " + SUB + " && node read.mjs "
     + FB, "deny"),
    ("wget -i a relative url list", "wget -q -i urls-rel.txt", "deny"),
    ("curl -K - fed by a heredoc", "curl -s -K - <<EOF\nurl = \"" + FB + "\"\nurl = \"" + FB2
     + "\"\nEOF", "deny"),
    ("while read fed by a heredoc", "while read u; do curl -s \"$u\"; done <<EOF\n" + FB + "\n"
     + FB2 + "\nEOF", "deny"),
    ("a fake heredoc opener inside quotes hides nothing", "echo \"<<EOF\"\ncurl -s " + FB,
     "deny"),
    ("cat a loader into bash", "cat " + LOADER_SH + " | bash", "deny"),
    ("source a loader", "source " + LOADER_SH, "deny"),
    ("dot a loader", ". " + LOADER_SH, "deny"),
    ("parallel :::: a url file", "parallel curl -s :::: " + URLS, "deny"),
    ("xargs sh -c over a url file", "xargs -I{} sh -c 'curl -s {}' < " + URLS, "deny"),
    ("osascript do shell script a loader", "osascript -e 'do shell script \"bash " + LOADER_SH
     + "\"'", "deny"),
    ("expect spawning a loader", "expect -c 'spawn bash " + LOADER_SH + "'", "deny"),
    ("git alias with a shell bang", "git -c alias.fb='!curl -s " + FB + "' fb", "deny"),
    ("make with curls in the recipe", "cd " + T + " && make -f Makefile", "deny"),
    ("open a .command loader", "open " + os.path.join(T, "run.command"), "deny"),
    ("open -a Terminal a loader", "open -a Terminal " + LOADER_SH, "deny"),
    ("tmux new-session running a loader", "tmux new-session -d 'bash " + LOADER_SH + "'",
     "deny"),
    ("screen running a loader", "screen -dm bash " + LOADER_SH, "deny"),
    ("instaloader by name", "instaloader someprofile", "deny"),
    ("python -m instaloader", "python3 -m instaloader someprofile", "deny"),
    ("userinfo in the url", "curl -s https://u@facebook.com/x", "deny"),
    ("percent encoded dot", "curl -s https://www.facebook%2Ecom/x", "deny"),
    ("ideographic full stop", "curl -s https://www.facebook。com/x", "deny"),
    ("fullwidth letters", "curl -s https://www.ｆａｃｅｂｏｏｋ.com/x",
     "deny"),
    ("the same url three times", G + " acquire --url " + FB + " --actor t && curl -s " + FB
     + " " + FB + " " + FB, "deny"),
    ("an unreadable script handed a social url", "node /nonexistent/x.mjs " + FB, "deny"),
    ("deno run a loader", "deno run -A " + LOADER_JS, "deny"),
    # false positives the first cut had
    ("a Google search whose query names facebook", "curl -s \"https://www.google.com/search?"
     "q=site:facebook.com+plumber\"", "allow"),
    ("a variable target with an output file that names facebook", "curl -s \"$API/x\" -o "
     + PAYLOAD, "allow"),
    ("curl --version", "curl --version", "allow"),
    ("a one liner that prints a canonical link", "python3 -c \"print('" + FB + "')\"", "allow"),
    ("a commit message naming 9222 and facebook", "git commit -m \"the cdp 9222 reader must "
     "never load facebook.com\"", "allow"),
]
for label, cmd, want in R1:
    allowed, msg = run_bash(cmd)
    got = "allow" if allowed else "deny"
    ok(got == want, "%s -> %s" % (label, want), "(got %s) %s" % (got, msg[:160]))

odd = ["https://u@facebook.com/x", "https://www.facebook%2Ecom/x",
       "https://www.facebook。com/x", "https://www.ｆａｃｅｂｏ"
       "ｏｋ.com/x"]
for u in odd:
    ctx, gate, clk, d = fresh_ctx()
    first = nav(ctx, u)[0]
    rows = [json.loads(x) for x in open(gate.ledger_path)] if os.path.exists(
        gate.ledger_path) else []
    second = nav(ctx, u)[0]
    ok(first and len(rows) == 1 and rows[0]["platform"] == "facebook" and not second,
       "odd spelling %r is recognised: it takes a slot, then the next is refused" % u,
       "first %s rows %s second %s" % (first, rows, second))
ctx, gate, clk, d = fresh_ctx()
ok(hk.decide({"tool_name": "mcp__claude-in-chrome__computer", "tool_input": {
    "action": "type", "text": FB}}, ctx)[0] and os.path.exists(gate.ledger_path),
   "typing a social URL with a Chrome computer action takes a slot")
ok(not hk.decide({"tool_name": "mcp__claude-in-chrome__computer", "tool_input": {
    "action": "type", "text": FB2}}, ctx)[0], "and a second one right away is refused")
ctx, gate, clk, d = fresh_ctx()
bare = [hk.decide({"tool_name": "mcp__claude-in-chrome__computer", "tool_input": {
    "action": "type", "text": "facebook.com/person%d" % i}}, ctx)[0] for i in range(3)]
rows = open(gate.ledger_path).read().splitlines() if os.path.exists(gate.ledger_path) else []
ok(bare == [True, False, False] and len(rows) == 1,
   "typing a BARE social host (no scheme) is gated too (QA round 2 HIGH)",
   "%s rows %d" % (bare, len(rows)))
ok(hk.decide({"tool_name": "mcp__claude-in-chrome__computer", "tool_input": {
    "action": "screenshot"}}, fresh_ctx()[0])[0], "a screenshot action passes")
EV = "mcp__playwright__browser_evaluate"
RC = "mcp__playwright__browser_run_code_unsafe"
for label, tool, code in [
        ("reduce over gotos", RC, "async (page) => { await ['a','b'].reduce(async (p, n) => "
         "{ await p; await page.goto('https://www.facebook.com/' + n); }, Promise.resolve()); }"),
        ("recursion", RC, "async (page) => { const go = async (i) => { if (i > 300) return; "
         "await page.goto('https://www.facebook.com/p' + i); return go(i + 1); }; await go(0); }"),
        ("setInterval", RC, "async (page) => { setInterval(() => page.goto("
         "'https://www.facebook.com/p' + Math.random()), 60000); }"),
        ("50 iframes", EV, "() => { for (let i=0;i<50;i++){ const f=document.createElement("
         "'iframe'); f.src='https://www.facebook.com/p'+i; document.body.append(f);} }")]:
    ok(not hk.decide({"tool_name": tool, "tool_input": {"code": code, "function": code}},
                     fresh_ctx()[0])[0], "page code bulk: %s is refused" % label)
ctx, gate, clk, d = fresh_ctx()
ok(hk.decide({"tool_name": EV, "tool_input": {"function": "() => { new Image().src = '" + FB
                                               + "'; }"}}, ctx)[0]
   and os.path.exists(gate.ledger_path), "one new Image().src to a social URL takes a slot")
import time as _t
tok = "a." * 16000 + "com"
t0 = _t.time()
run_bash("echo " + tok)
hk.decide({"tool_name": "WebFetch", "tool_input": {"url": "https://" + tok}}, fresh_ctx()[0])
ok(_t.time() - t0 < 3.0, "a 32k character dotted token is judged in under 3 s (was 83 s)",
   "%.1f s" % (_t.time() - t0))

print("G  QA round 3 regressions (each was ALLOWED before)")
import plistlib


def plist(name, argv, program=None):
    p = os.path.join(T, name)
    d = {"Label": name, "ProgramArguments": argv}
    if program:
        d["Program"] = program
    with open(p, "wb") as fh:
        plistlib.dump(d, fh)
    return p


PL_CURL = plist("com.x.fb.plist", ["/usr/bin/curl", "-s", FB])
PL_SCRIPT = plist("com.x.loader.plist", ["bash", LOADER_SH], program="/bin/bash")
PL_OK = plist("com.x.ok.plist", ["/usr/bin/true"])
AGENTS = os.path.join(T, "agents")
os.makedirs(AGENTS, exist_ok=True)
plist("agents/com.x.fb.plist", ["/usr/bin/curl", "-s", FB])
JOB = fx("job.sh", "curl -s " + FB + "\n")
SLUGS = fx("slugs.txt", "joesplumbing\nacmehvac\n")
LOADER_PY = fx("loader.py", "import sys, urllib.request\nfor u in open(sys.argv[1]):\n"
               "    urllib.request.urlopen(u.strip())\n")
filler = "".join("https://example%d.com/about/team/page\n" % i for i in range(90000))
MID = fx("mid.txt", filler + FB + "\n" + FB2 + "\n")         # ~3.3 MB: past the old 2 MB cap
BIG = fx("big.txt", filler * 3 + FB + "\n" + FB2 + "\n")     # ~10 MB: line scan
HUGE = os.path.join(T, "huge.txt")                          # > 64 MB: presumed a URL list
with open(HUGE, "w") as fh:
    for _ in range(20):
        fh.write(filler)
LEDGER = os.path.expanduser("~/.claude/state/social-loads.jsonl")
STATE = os.path.expanduser("~/.claude/state/social-gate-state.json")
CFGP = os.path.expanduser("~/.claude/config/social-pacing.json")
R3 = [
    # HIGH: an xargs fan out fed from a pipe
    ("echo | xargs curl", "echo " + FB + " | xargs curl -s", "deny"),
    ("printf | xargs -n1 -P4 curl", "printf '" + FB + "\\n" + FB2 + "\\n' | xargs -n1 -P4 curl -s",
     "deny"),
    ("echo | xargs -I{} curl {}", "echo " + FB + " | xargs -I{} curl -s {}", "deny"),
    ("echo | xargs open", "echo " + FB + " | xargs open", "deny"),
    ("echo | xargs wget", "echo " + FB + " | xargs -n1 wget -qO-", "deny"),
    ("git ls-files | xargs grep facebook.com (not a load)",
     "git ls-files | xargs grep -l facebook.com", "allow"),
    # MEDIUM: a command string handed to another program
    ("docker run sh -c wget", "docker run --rm alpine sh -c 'wget -qO- " + FB + "'", "deny"),
    ("docker run IMG curl bare host", "docker run --rm curlimages/curl curl -s facebook.com/x",
     "deny"),
    ("ssh host 'curl'", "ssh somehost 'curl -s " + FB + "'", "deny"),
    ("nice -n 5 sh -c", "nice -n 5 sh -c 'curl -s " + FB + "'", "deny"),
    ("su -c", "su zalo -c 'curl -s " + FB + "'", "deny"),
    ("arch -arm64 sh -c", "arch -arm64 sh -c 'curl -s " + FB + "'", "deny"),
    ("arch -arm64 curl bare host", "arch -arm64 curl -s facebook.com/x", "deny"),
    ("script -q sh -c", "script -q /dev/null sh -c 'curl -s " + FB + "'", "deny"),
    ("env -S", "env -S 'curl -s " + FB + "'", "deny"),
    ("timeout -s KILL 5 curl", "timeout -s KILL 5 curl -s " + FB, "deny"),
    ("docker echo of prose (not a load)", "docker run --rm alpine echo 'see facebook.com page'",
     "allow"),
    ("ssh ls (not a load)", "ssh somehost 'ls -la /tmp'", "allow"),
    ("a prompt naming facebook.com (not a load)",
     "codex exec 'summarize why the facebook.com rail is paced'", "allow"),
    # MEDIUM: scheduler entries given as a file
    ("launchctl load a curl plist", "launchctl load " + PL_CURL, "deny"),
    ("launchctl bootstrap a curl plist", "launchctl bootstrap gui/501 " + PL_CURL, "deny"),
    ("launchctl load a plist running a loader", "launchctl load -w " + PL_SCRIPT, "deny"),
    ("launchctl load a directory", "launchctl load " + AGENTS, "deny"),
    ("at -f a job", "at -f " + JOB + " now + 1 hour", "deny"),
    ("batch < a job", "batch < " + JOB, "deny"),
    ("cp a plist into place, then load it", "cp " + PL_CURL + " ~/Library/LaunchAgents/"
     "com.x.fb.plist && launchctl load ~/Library/LaunchAgents/com.x.fb.plist", "deny"),
    ("launchctl load a harmless plist", "launchctl load " + PL_OK, "allow"),
    # a redirector followed onto a social page
    ("curl -L google.com/url?q=FB", "curl -sL 'https://www.google.com/url?q=" + FB + "'",
     "deny"),
    ("wget a percent encoded redirector", "wget -qO- 'https://l.example.com/r?u=https%3A%2F%2F"
     "www.facebook.com%2Fx'", "deny"),
    ("curl WITHOUT -L on a redirector (no load)", "curl -s 'https://www.google.com/url?q="
     + FB + "'", "allow"),
    ("a site: search with -L (no URL in the query)", "curl -sL 'https://www.google.com/search"
     "?q=site:facebook.com+plumber'", "allow"),
    ("launchctl list", "launchctl list", "allow"),
    # MEDIUM: data files past the old scan caps
    ("a 3 MB list, social URLs at the end", "xargs -a " + MID + " -n1 curl -s", "deny"),
    ("a 10 MB list, line scanned", "python3 " + LOADER_PY + " " + BIG, "deny"),
    ("a list over 64 MB is presumed social", "cat " + HUGE + " | xargs -n1 curl -s", "deny"),
    ("a non fetching script reading the 10 MB list", "python3 " + PARSER + " " + BIG, "allow"),
    # MEDIUM: the gate's own ledger, state and config
    ("rm the ledger", "rm " + LEDGER, "deny"),
    ("rm -f the state via $HOME", "rm -f $HOME/.claude/state/social-gate-state.json", "deny"),
    ("cd state && rm", "cd ~/.claude/state && rm social-loads.jsonl", "deny"),
    ("truncate by redirect", ": > ~/.claude/state/social-loads.jsonl", "deny"),
    ("overwrite the state by echo", "echo '{}' > " + STATE, "deny"),
    ("sed -i the config", "sed -i '' 's/40/400/' " + CFGP, "deny"),
    ("perl -pi the config", "perl -pi -e 's/40/400/' " + CFGP, "deny"),
    ("mv the ledger away", "mv " + LEDGER + " /tmp/", "deny"),
    ("cp over the config", "cp /tmp/loose.json " + CFGP, "deny"),
    ("rm -rf the state dir", "rm -rf ~/.claude/state", "deny"),
    ("rm a glob in the state dir", "rm ~/.claude/state/*", "deny"),
    ("python one liner removes the ledger", "python3 -c \"import os; os.remove('" + LEDGER
     + "')\"", "deny"),
    ("variable indirection", "D=~/.claude/state; rm $D/social-loads.jsonl", "deny"),
    ("echo | xargs rm", "echo " + LEDGER + " | xargs rm", "deny"),
    ("find -delete", "find ~/.claude/state -name 'social-*' -delete", "deny"),
    ("truncate -s 0", "truncate -s 0 " + LEDGER, "deny"),
    ("bash -c rm", "bash -c 'rm " + LEDGER + "'", "deny"),
    ("tee over the config", "echo '{}' | tee " + CFGP, "deny"),
    ("cat the ledger (a read)", "cat " + LEDGER, "allow"),
    ("tail | jq the ledger", "tail -5 " + LEDGER + " | jq .", "allow"),
    ("ls the state dir", "ls -la ~/.claude/state/", "allow"),
    ("sed -n the config", "sed -n 1,20p " + CFGP, "allow"),
    ("cp the config out", "cp " + CFGP + " /tmp/cfg.json", "allow"),
    ("git add the config", "git -C ~/.claude add config/social-pacing.json", "allow"),
    ("python reads the config", "python3 -c \"import json;json.load(open('" + CFGP + "'))\"",
     "allow"),
    ("mv a file into home", "mv /tmp/a.txt ~/", "allow"),
    ("rm another state file", "rm ~/.claude/state/mcp-discover-verdicts.json", "allow"),
    # LOW: a host assembled at run time inside a loop
    ("loop with a computed host", "for s in $(cat " + SLUGS + "); do curl -s "
     "\"https://www.$(printf face)book.com/$s\"; done", "deny"),
    ("loop with a computed PATH only", "for f in a b; do curl -s "
     "\"https://api.example.com/$(date +%s)/$f\"; done", "allow"),
]
for label, cmd, want in R3:
    t0 = _t.time()
    allowed, msg = run_bash(cmd)
    got = "allow" if allowed else "deny"
    ok(got == want, "%s -> %s" % (label, want), "(got %s) %s" % (got, msg[:200]))
    ok(_t.time() - t0 < 5.0, "%s judged in under 5 s" % label, "%.1f s" % (_t.time() - t0))
for tool, path in (("Edit", CFGP), ("Write", LEDGER), ("MultiEdit", STATE)):
    ok(not hk.decide({"tool_name": tool, "tool_input": {"file_path": path}}, fresh_ctx()[0])[0],
       "%s on %s is refused" % (tool, os.path.basename(path)))
ok(hk.decide({"tool_name": "Edit", "tool_input": {"file_path": HOOK}}, fresh_ctx()[0])[0],
   "Edit on another file passes")
# LOW: m.me and ig.me short links take a slot
for u, plat in (("https://m.me/joesplumbing", "facebook"), ("https://ig.me/m/joes", "instagram")):
    ctx, gate, clk, d = fresh_ctx()
    first = nav(ctx, u)[0]
    rows = [json.loads(x) for x in open(gate.ledger_path)] if os.path.exists(
        gate.ledger_path) else []
    ok(first and len(rows) == 1 and rows[0]["platform"] == plat and not nav(ctx, u)[0],
       "%s is gated as %s" % (u, plat), str(rows))
# LOW: typing into a page element is not a navigation; a click on a link still is
for label, tool, ti in (
        ("fill_form a CRM field", "mcp__playwright__browser_fill_form",
         {"fields": [{"name": "Website", "type": "textbox", "ref": "e1", "value": FB}]}),
        ("browser_type into a field", "mcp__playwright__browser_type",
         {"element": "Website", "ref": "e2", "text": FB}),
        ("Chrome computer typing prose", "mcp__claude-in-chrome__computer",
         {"action": "type", "text": "see our page at facebook.com/joesplumbing"})):
    ctx, gate, clk, d = fresh_ctx()
    ok(hk.decide({"tool_name": tool, "tool_input": ti}, ctx)[0]
       and not os.path.exists(gate.ledger_path), "%s passes and spends no slot" % label)
ctx, gate, clk, d = fresh_ctx()
ok(hk.decide({"tool_name": "mcp__playwright__browser_click", "tool_input": {
    "element": "link " + FB, "ref": "e3"}}, ctx)[0] and os.path.exists(gate.ledger_path),
   "a click on a social link still takes a slot")
ok(not hk.decide({"tool_name": "mcp__playwright__browser_click", "tool_input": {
    "element": "link " + FB2, "ref": "e4"}}, ctx)[0], "and the next one right away is refused")
# the real hook over stdin
stdin_case("real hook: echo | xargs curl is blocked", {"tool_name": "Bash", "tool_input": {
    "command": "echo " + FB + " | xargs curl -s"}, "cwd": T}, 2)
stdin_case("real hook: docker sh -c is blocked", {"tool_name": "Bash", "tool_input": {
    "command": "docker run --rm alpine sh -c 'wget -qO- " + FB + "'"}, "cwd": T}, 2)
r = stdin_case("real hook: rm the ledger is blocked", {"tool_name": "Bash", "tool_input": {
    "command": "rm " + LEDGER}, "cwd": T}, 2)
ok("Only Zalo" in r.stderr, "with the owner-only reason", r.stderr[:200])
stdin_case("real hook: Edit on the config is blocked", {"tool_name": "Edit", "tool_input": {
    "file_path": CFGP, "old_string": "40", "new_string": "400"}}, 2)
os.remove(HUGE)

print("H  independent verifier regressions (each was ALLOWED, or a false positive)")
CFG300 = fx("fb-urls.cfg", "".join('url = "https://www.facebook.com/p%d"\n' % i
                                   for i in range(300)))
CFG_OK = fx("ok.cfg", 'url = "https://example.com/a"\n')
DOC = fx("notes.md", "curl -s " + FB + " was the old way\n")
CMD = fx("cmd.txt", "curl -s " + FB + "\n")
HARMLESS = fx("harmless.txt", "ls -la /tmp\n")
RV = [
    ("cat cfg | curl -K -", "cat " + CFG300 + " | curl -s -K -", "deny"),
    ("cat cfg | curl --config /dev/stdin", "cat " + CFG300 + " | curl -s --config /dev/stdin",
     "deny"),
    ("curl -K <(cat cfg)", "curl -s -K <(cat " + CFG300 + ")", "deny"),
    ("curl -K - <<< herestring", "curl -s -K - <<< 'url = \"" + FB + "\"'", "deny"),
    ("echo | curl -K -", "echo 'url = \"" + FB + "\"' | curl -s -K -", "deny"),
    ("curl --config=/dev/stdin", "cat " + CFG300 + " | curl -s --config=/dev/stdin", "deny"),
    ("curl -K a non social config", "curl -s -K " + CFG_OK, "allow"),
    ("python requests aliased", "python3 -c \"import requests as r; print(r.get('" + FB
     + "').status_code)\"", "deny"),
    ("perl LWP", "perl -MLWP::Simple -e 'print get(\"" + FB + "\")'", "deny"),
    ("ruby open-uri", "ruby -ropen-uri -e 'puts URI.open(\"" + FB + "\").read'", "deny"),
    ("php file_get_contents", "php -r 'echo file_get_contents(\"" + FB + "\");'", "deny"),
    ("python socket", "python3 -c \"import socket; s=socket.create_connection(("
     "'www.facebook.com', 80))\"", "deny"),
    ("python json naming a host (not a load)", "python3 -c \"import json; print(json.dumps("
     "{'site': 'facebook.com'}))\"", "allow"),
    ("python heredoc, then grep of a doc naming FB (not a load)", "python3 - <<'EOF'\n"
     "import json\nprint(1)\nEOF\ngrep -c curl " + DOC, "allow"),
    ("python -c exec_module + the config path (a read)", "python3 -c \"import importlib.util,"
     "json; s=importlib.util.spec_from_file_location('au','/x/a.py'); print(json.load(open('"
     + CFGP + "'))['routes'])\"", "allow"),
    ("python -c subprocess cat of the config (a read)", "python3 -c \"import subprocess; "
     "print(subprocess.run(['cat','" + CFGP + "'],capture_output=True).stdout)\"", "allow"),
    ("python -c subprocess rm of the ledger", "python3 -c \"import subprocess; "
     "subprocess.run(['rm','" + LEDGER + "'])\"", "deny"),
    ("python -c os.system rm of the ledger", "python3 -c \"import os; os.system('rm "
     + LEDGER + "')\"", "deny"),
    ("9222 by arithmetic", "curl -s \"http://localhost:$((9000+222))/json/new?" + FB + "\"",
     "deny"),
    ("bash -c $(cat a loader file)", "bash -c \"$(cat " + CMD + ")\"", "deny"),
    ("eval $(< a loader file)", "eval \"$(< " + CMD + ")\"", "deny"),
    ("bash -c $(cat a harmless file)", "bash -c \"$(cat " + HARMLESS + ")\"", "allow"),
    ("nc to facebook", "nc www.facebook.com 443", "deny"),
    ("openssl s_client to facebook", "openssl s_client -connect www.facebook.com:443 -quiet",
     "deny"),
    ("socat to facebook", "socat - TCP:www.facebook.com:80", "deny"),
    ("openssl rand (not a load)", "openssl rand -hex 8", "allow"),
    ("nc -z localhost (not a load)", "nc -z localhost 5432", "allow"),
]
for label, cmd, want in RV:
    allowed, msg = run_bash(cmd)
    got = "allow" if allowed else "deny"
    ok(got == want, "%s -> %s" % (label, want), "(got %s) %s" % (got, msg[:200]))
ctx, gate, clk, d = fresh_ctx()
gate.acquire(FB, "t", grant=True)
ok(not run_bash("curl -s \"http://localhost:$((9000+222))/json/new?" + FB + "\"", ctx)[0],
   "9222 by arithmetic is refused even with a grant waiting")

print("I  re-verifier regressions (each was ALLOWED)")
RR = [
    ("quoted assignment X=\"$(curl FB)\"", "X=\"$(curl -s " + FB + ")\"", "deny"),
    ("echo \"$(curl FB)\" | grep", "echo \"$(curl -s " + FB + ")\" | grep -c x", "deny"),
    ("printf \"$(curl FB)\" > f", "printf '%s' \"$(curl -s " + FB + ")\" > /tmp/o.html", "deny"),
    ("grep <<< \"$(curl FB)\"", "grep x <<< \"$(curl -s " + FB + ")\"", "deny"),
    ("quoted backticks", "X=\"`curl -s " + FB + "`\"", "deny"),
    ("a loop of quoted substitutions", "for u in a b c; do H=\"$(curl -s "
     "https://www.facebook.com/$u)\"; echo ${#H}; done", "deny"),
    ("a literal $(...) in single quotes (not run)", "git commit -m 'never $(curl -s " + FB
     + ")'", "allow"),
    ("node require https", "node -e \"require('https').get('" + FB + "', r => r.resume())\"",
     "deny"),
    ("node:https alias", "node -e \"const h=require('node:https'); h.get('" + FB + "')\"",
     "deny"),
    ("deno eval fetch", "deno eval \"await fetch('" + FB + "')\"", "deny"),
    ("python http.client", "python3 -c \"from http import client; client.HTTPSConnection("
     "'www.facebook.com').request('GET','/x')\"", "deny"),
    ("9222 by $(echo), no scheme", "curl -s \"localhost:$(echo 9222)/json/new?" + FB + "\"",
     "deny"),
    ("9222 by P=$(echo), no scheme", "P=$(echo 9222); curl -s \"localhost:$P/json/new?" + FB
     + "\"", "deny"),
]
for label, cmd, want in RR:
    allowed, msg = run_bash(cmd)
    got = "allow" if allowed else "deny"
    ok(got == want, "%s -> %s" % (label, want), "(got %s) %s" % (got, msg[:200]))
for label, cmd in (("$(echo 9222) with a grant", "curl -s \"localhost:$(echo 9222)/json/new?"
                    + FB + "\""), ("P=$(echo 9222) with a grant", "P=$(echo 9222); curl -s "
                                   "\"localhost:$P/json/new?" + FB + "\"")):
    ctx, gate, clk, d = fresh_ctx()
    gate.acquire(FB, "t", grant=True)
    ok(not run_bash(cmd, ctx)[0], "%s is refused" % label)
LOOPED = ("() => { for (let i = 0; i < 50; i++) document.body.appendChild(Object.assign("
          "document.createElement('iframe'), {src: 'https://www.facebook.com/p' + i})); }")
ONCE = ("() => document.body.appendChild(Object.assign(document.createElement('iframe'), "
        "{src: '" + FB + "'}))")
for label, code, want_allowed, want_slot in (
        ("Object.assign iframe {src} in a loop", LOOPED, False, False),
        ("Object.assign iframe {src} once", ONCE, True, True),
        ("srcset", "() => { const i = new Image(); i.srcset = '" + FB + "'; }", True, True),
        ("dynamic import", "() => import('https://www.facebook.com/x.js')", True, True),
        ("prefetch link", "() => document.head.appendChild(Object.assign(document."
         "createElement('link'), {rel: 'prefetch', href: '" + FB + "'}))", True, True),
        ("reading links off a page (not a load)", "() => [...document.links].filter(a => "
         "a.href.includes('facebook.com')).map(a => ({href: a.href}))", True, False)):
    ctx, gate, clk, d = fresh_ctx()
    allowed = hk.decide({"tool_name": "mcp__playwright__browser_evaluate", "tool_input": {
        "function": code}}, ctx)[0]
    ok(allowed == want_allowed and os.path.exists(gate.ledger_path) == want_slot,
       "page code: %s -> %s, slot %s" % (label, "allow" if want_allowed else "deny",
                                          want_slot),
       "got allowed=%s slot=%s" % (allowed, os.path.exists(gate.ledger_path)))
stdin_case("real hook: a loop of quoted substitutions is blocked", {
    "tool_name": "Bash", "tool_input": {"command": "for u in a b c; do H=\"$(curl -s "
                                        "https://www.facebook.com/$u)\"; done"}, "cwd": T}, 2)

print("J  Codex Computer Use (mcp__codex-cu__js): page code that drives the logged in Chrome")
CU = "mcp__codex-cu__js"


def cu(ctx, code):
    return hk.decide({"tool_name": CU, "tool_input": {"code": code, "title": "t"},
                      "session_id": "cu123456"}, ctx)


def slots(gate):
    return len(open(gate.ledger_path).read().splitlines()) if os.path.exists(
        gate.ledger_path) else 0


ok(hk.BROWSER_TOOL_RE.match(CU) and hk.CODE_TOOL_RE.search(CU),
   "codex-cu js is classified as a browser code tool")
ok(hk.BROWSER_TOOL_RE.match("mcp__codex-cu__js_reset") and not hk.CODE_TOOL_RE.search(
    "mcp__codex-cu__js_reset"), "js_reset is a browser tool but not a code tool")
ctx, gate, clk, d = fresh_ctx()
ok(cu(ctx, 'const t = await cua.createBrowserTab("chrome", "' + FB + '");')[0]
   and slots(gate) == 1, "createBrowserTab to a social URL is gated: it takes a slot")
allowed, msg = cu(ctx, 'await tab.goto("' + FB2 + '");')
ok(not allowed and "WAIT" in msg and slots(gate) == 1,
   "a goto to a social URL right after is blocked, and writes nothing", msg[:160])
ok(not cu(fresh_ctx()[0], 'const t = await cua.createBrowserTab("chrome", "https://example.com");'
          ' await t.goto("' + FB + '");')[0],
   "createBrowserTab plus goto in one call (two navigations) is blocked even with budget free")
ctx, gate, clk, d = fresh_ctx()
ok(cu(ctx, 'let c = await cua.getApp("Google Chrome"); await c.typeText("' + FB + '");'
           ' await c.pressKey("Return");')[0] and slots(gate) == 1,
   "typeText of a social URL into Chrome is gated: it takes a slot")
ok(not cu(ctx, 'await c.typeText("' + FB2 + '"); await c.pressKey("Return");')[0],
   "a second typeText of a social URL right away is blocked")
ctx, gate, clk, d = fresh_ctx()
ok(cu(ctx, 'await c.typeText("facebook.com/joe.smith");')[0] and slots(gate) == 1,
   "typeText of a BARE social host (no scheme) is gated too")
for label, code in (
        ("paste", 'await c.paste("' + LI + '");'),
        ("setValue into the address bar", 'await c.setValue(10, "' + LI + '");')):
    ctx, gate, clk, d = fresh_ctx()
    first = cu(ctx, code)[0]
    second = cu(ctx, code)[0]
    ok(first and slots(gate) == 1 and not second,
       "%s of a social URL takes a slot, the same call again right away is blocked" % label,
       "first %s slots %d second %s" % (first, slots(gate), second))
for label, code in (
        ("a for loop over social URLs", 'for (const u of ["' + FB + '", "' + FB2 + '"]) '
         'await cua.createBrowserTab("chrome", u);'),
        ("one call naming two social URLs", 'await c.typeText("' + FB + '"); '
         'await c.typeText("' + FB2 + '");'),
        ("a timer", 'setInterval(() => c.typeText("' + FB + '"), 60000);')):
    ok(not cu(fresh_ctx()[0], code)[0], "codex-cu bulk: %s is blocked" % label)
ctx, gate, clk, d = fresh_ctx()
ok(cu(ctx, 'let app = await cua.getApp("Calculator"); await app.click(9); '
           'await app.typeText("123+456"); await app.getAXState();')[0] and slots(gate) == 0,
   "Calculator code passes and takes no slot")
ok(cu(ctx, 'const t = await cua.createBrowserTab("chrome", "https://example.com", '
           '{sessionName: "test"});')[0] and slots(gate) == 0,
   "createBrowserTab to example.com passes and takes no slot")
ok(cu(ctx, 'await c.getAXState(); // the tab title says facebook.com')[0] and slots(gate) == 0,
   "code that only reads state while naming a social host passes (no navigation verb)")
ok(cu(ctx, 'await c.typeText(atob("aHR0cHM6Ly93d3cuZmFjZWJvb2suY29tL3g="));')[0],
   "a URL built at run time (base64) passes: stated limit, the hook cannot see it")
for label, code in (
        ("a pressKey loop over bare hosts (no listed verb)", 'const app = await cua.getApp('
         '"Google Chrome"); for (const u of ["facebook.com/a","facebook.com/b"]) { await '
         'app.pressKey("cmd+l"); for (const ch of u) await app.pressKey(ch); }'),
        ("a list of social URLs parked in REPL state (no verb yet)",
         'globalThis.q = ["' + FB + '", "' + FB2 + '"];')):
    ok(not cu(fresh_ctx()[0], code)[0], "QA round 1: %s is blocked" % label)
ctx, gate, clk, d = fresh_ctx()
ok(hk.decide({"tool_name": CU, "tool_input": {
    "code": '// open ' + FB + '\nawait tab.goto("' + FB + '");',
    "title": "Open " + FB}}, ctx)[0] and slots(gate) == 1,
   "QA round 1: one goto whose title and comment repeat the URL is one paced load")
for label, code in (
        ("prose typed into TextEdit", 'const app = await cua.getApp("TextEdit"); await '
         'app.typeText("Find me on instagram.com/zalokabche and x.com/zalo");'),
        ("prose in a mail draft", 'await m.typeText("see the thread on x.com today.");'),
        ("tab form typeText into a page field", 'await tab.typeText(12, "' + LI + '");'),
        ("tab form paste into a page field", 'await tab.paste(null, "' + LI + '");')):
    ctx, gate, clk, d = fresh_ctx()
    ok(cu(ctx, code)[0] and slots(gate) == 0,
       "QA round 1: %s passes and takes no slot" % label)
for label, code in (
        ("bracket access", 'await app["paste"]("' + FB + '");'),
        ("typeText.call", 'const {typeText} = app; await typeText.call(app, "' + FB + '");'),
        ("node fetch", 'await fetch("' + FB + '");'),
        ("an escaped space does not make a URL prose", 'await c.typeText("facebook.com/x '
         '\\u0020");')):
    ctx, gate, clk, d = fresh_ctx()
    allowed = cu(ctx, code)[0]
    ok(not allowed or slots(gate) == 1,
       "QA round 1: %s is caught: it takes a slot or is refused, never a free pass" % label)
ctx, gate, clk, d = fresh_ctx()
ok(cu(ctx, 'let tab = await cua.getTab({url: "' + LI + '"}, {browser: "chrome"});')[0]
   and slots(gate) == 0, "QA round 2: getTab only binds an open tab: no load, no slot")
ok(cu(ctx, 'let tab = await cua.getTab({url: "' + LI + '"}); await tab.click(4);')[0]
   and slots(gate) == 1, "QA round 2: getTab then a click on that tab is gated")
for label, code in (
        ("a search URL with spaces in goto",
         'await tab.goto("https://www.facebook.com/search/top?q=roofing companies miami");'),
        ("a LinkedIn search URL with spaces in createBrowserTab",
         'await cua.createBrowserTab("chrome", "https://www.linkedin.com/search/results/'
         'people/?keywords=marketing agency owner");'),
        ("a URL then words typed into the address bar",
         'await c.typeText("https://www.facebook.com/joe go now"); await c.pressKey("Return");'),
        ("a verb word in a comment before one goto",
         '// navigate to the profile\nawait tab.goto("' + FB + '");'),
        ("a verb word in a block comment before one paste",
         '/* paste the profile URL into the address bar */ await c.paste("' + FB + '"); '
         'await c.pressKey("Return");'),
        ("a multi line template before a typeText",
         'const msg = `Hey Joe,\ngreat post!`; await c.click(3); await c.typeText(`' + FB
         + '\\n`);')):
    ctx, gate, clk, d = fresh_ctx()
    ok(cu(ctx, code)[0] and slots(gate) == 1,
       "QA round 2: %s is ONE paced load: it takes exactly one slot" % label,
       "slots %d" % slots(gate))
for label, code in (
        ("an escaped newline", 'globalThis.q = "' + FB + '\\n' + FB2 + '".split("\\n");'),
        ("a pipe", 'globalThis.q = "' + FB + '|' + FB2 + '".split("|");'),
        ("a semicolon", 'globalThis.q = "' + FB + ';' + FB2 + '".split(";");')):
    ok(not cu(fresh_ctx()[0], code)[0],
       "QA round 2: a list joined by %s is several URLs: blocked" % label)
ctx9, _, _, _ = fresh_ctx()
ok(not cu(ctx9, 'const ws = "ws://127.0.0.1:9222/devtools"; await c.typeText("' + FB
          + '");')[0],
   "codex-cu code that names the Blueprint port 9222 with a social host is blocked")
stdin_case("real hook: codex-cu Calculator code passes", {
    "tool_name": CU, "tool_input": {"code": 'let app = await cua.getApp("Calculator");'}}, 0)
r = stdin_case("real hook: codex-cu code opening two facebook pages is blocked", {
    "tool_name": CU, "tool_input": {"code": 'await cua.createBrowserTab("chrome", "' + FB
                                    + '"); await cua.createBrowserTab("chrome", "' + FB2 + '");'}},
    2)
ok("BLOCKED (social-pace-guard)" in r.stderr, "with a readable reason", r.stderr[:160])

print("K  the computer use app allow list is Zalo's (config/computer-use-apps.json)")
CUA = os.path.expanduser("~/.claude/config/computer-use-apps.json")
ok(os.path.realpath(hk.CU_APPS_PATH) == os.path.realpath(CUA), "the hook protects the real path")
for tool in ("Write", "Edit", "MultiEdit"):
    ok(not hk.decide({"tool_name": tool, "tool_input": {"file_path": CUA, "content": "{}"}},
                     fresh_ctx()[0])[0], "%s on computer-use-apps.json is refused" % tool)
for label, cmd in (
        ("a redirect", "echo '{\"apps\":[]}' > ~/.claude/config/computer-use-apps.json"),
        ("sed -i", "sed -i '' 's/Preview/Google Chrome/' ~/.claude/config/computer-use-apps.json"),
        ("jq into a temp then mv", "jq '.apps += [{\"name\":\"Google Chrome\"}]' "
         "~/.claude/config/computer-use-apps.json > /tmp/x.json && mv /tmp/x.json "
         "~/.claude/config/computer-use-apps.json"),
        ("cp over it", "cp /tmp/mine.json /Users/zalo/.claude/config/computer-use-apps.json"),
        ("rm", "rm ~/.claude/config/computer-use-apps.json"),
        ("a bare name from inside the config dir", "cd ~/.claude/config && tee "
         "computer-use-apps.json < /tmp/x"),
        ("python writing it", "python3 -c \"open('/Users/zalo/.claude/config/"
         "computer-use-apps.json','w').write('{}')\"")):
    allowed, msg = run_bash(cmd)
    ok(not allowed and "computer-use-apps.json" in msg and "his call" in msg,
       "Bash %s on the allow list is refused with the reason" % label, msg[:160])
for label, cmd in (
        ("echo after cd", "cd ~/.claude/config && echo '{}' > computer-use-apps.json"),
        ("cat heredoc after cd", "cd ~/.claude/config && cat > computer-use-apps.json <<'EOF'\n"
         "{}\nEOF"),
        ("printf into a relative path after cd", "cd ~/.claude && printf x > "
         "config/computer-use-apps.json"),
        ("the pacing config after cd (same gap, same fix)", "cd ~/.claude/config && "
         "echo '{}' >| social-pacing.json"),
        ("plutil -insert", "plutil -insert apps.4 -json '{\"name\":\"Google Chrome\"}' "
         "~/.claude/config/computer-use-apps.json"),
        ("patch", "patch ~/.claude/config/computer-use-apps.json /tmp/add-chrome.diff"),
        ("ed", "printf ',s/Preview/Chrome/\\nw\\n' | ed ~/.claude/config/computer-use-apps.json"),
        ("a hard link", "ln ~/.claude/config/computer-use-apps.json /tmp/h"),
        ("git checkout of the file", "cd ~/.claude && git checkout -- "
         "config/computer-use-apps.json"),
        ("git restore of the file", "git -C ~/.claude restore "
         "/Users/zalo/.claude/config/computer-use-apps.json"),
        ("git -C with a pathspec relative to -C", "cd ~/dev && git -C ~/.claude restore "
         "config/computer-use-apps.json"),
        ("git -C into the config dir", "git -C ~/.claude/config checkout HEAD -- "
         "computer-use-apps.json"),
        ("/bin/link (a hard link)", "link ~/.claude/config/computer-use-apps.json /tmp/x"),
        ("python os.link", "python3 -c \"import os; os.link('/Users/zalo/.claude/config/"
         "computer-use-apps.json', '/tmp/x')\""),
        ("a write to the Computer Use approvals store", "echo '{\"approvedBundleIdentifiers\":"
         "[\"com.google.Chrome\"]}' > \"$HOME/Library/Group Containers/2DC432GLL2.com.openai."
         "sky.CUAService/Library/Application Support/Software/ComputerUseAppApprovals.json\"")):
    allowed, msg = run_bash(cmd)
    ok(not allowed, "QA 10-03: Bash %s on a protected file is refused" % label, msg[:160])
for label, cmd in (("cat", "cat ~/.claude/config/computer-use-apps.json"),
                   ("jq read", "jq -r '.apps[].name' ~/.claude/config/computer-use-apps.json"),
                   ("jq read into a temp file", "jq . ~/.claude/config/computer-use-apps.json "
                    "> /tmp/apps-copy.json"),
                   ("plutil -p (print)", "plutil -p ~/.claude/config/computer-use-apps.json"),
                   ("a symlink (writes through it resolve to the real path)",
                    "ln -s ~/.claude/config/computer-use-apps.json /tmp/apps-link"),
                   ("git add and commit by name", "cd ~/.claude && git add "
                    "config/computer-use-apps.json && git commit -m x"),
                   ("cd then a write elsewhere", "cd ~/.claude/config && echo x > /tmp/y.txt")):
    ok(run_bash(cmd)[0], "reading the allow list (%s) passes" % label)
ok(not hk.decide({"tool_name": "Write", "tool_input": {"file_path": hk.CU_STORE_PATH,
                                                       "content": "{}"}}, fresh_ctx()[0])[0],
   "a Write to the Computer Use approvals store is refused")
ok(run_bash("cat \"$HOME/Library/Group Containers/2DC432GLL2.com.openai.sky.CUAService/Library/"
            "Application Support/Software/ComputerUseAppApprovals.json\"")[0],
   "reading the approvals store passes")
ok(run_bash("git -C ~/.claude log --oneline -3 -- config/computer-use-apps.json")[0],
   "git -C log of the allow list passes")
ok(not hk.decide({"tool_name": "Write", "tool_input": {"file_path": "/tmp/apps-link",
                                                       "content": "{}"}}, fresh_ctx()[0])[0]
   if os.path.islink("/tmp/apps-link") else True,
   "a Write through a symlink to the allow list resolves to it and is refused")
r = stdin_case("real hook: a Write to the allow list is blocked", {
    "tool_name": "Write", "tool_input": {"file_path": CUA, "content": "{}"}}, 2)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
