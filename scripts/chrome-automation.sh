#!/bin/bash
# Open (or focus) the Chrome profile Claude can drive.
#
# Why a separate profile: since Chrome 136, --remote-debugging-port is IGNORED
# on the default profile. Attaching to your everyday logged-in Chrome is simply
# not possible on current Chrome, so this is a dedicated profile instead — which
# is also the safer split: the debug port exposes ONLY this profile, never your
# personal tabs.
#
# Logins here PERSIST across restarts (they live in the profile directory), so
# each site is a one-time login. Only the running instance needs relaunching,
# which is what this script is for.
#
#   chrome-automation.sh                 # open/focus, no navigation
#   chrome-automation.sh <url>           # open/focus and load a URL
#
# Claude attaches over CDP at http://127.0.0.1:9222

set -u
PORT=9222
PROFILE="$HOME/.chrome-automation"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
URL="${1:-}"

[ -x "$CHROME" ] || { echo "Chrome not found at $CHROME"; exit 1; }
mkdir -p "$PROFILE"

is_up() { curl -sS --max-time 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; }

open_tab() {
  # CDP needs PUT on modern Chrome; GET was removed.
  local enc
  enc=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$1")
  curl -sS --max-time 5 -X PUT "http://127.0.0.1:$PORT/json/new?$enc" >/dev/null 2>&1
}

if is_up; then
  echo "✅ already running on :$PORT"
else
  echo "launching…"
  nohup "$CHROME" \
    --user-data-dir="$PROFILE" \
    --remote-debugging-port="$PORT" \
    --no-first-run --no-default-browser-check \
    ${URL:+"$URL"} ${URL:+} about:blank \
    >/tmp/chrome-automation.log 2>&1 &
  for _ in $(seq 1 12); do sleep 1; is_up && break; done
  is_up || { echo "❌ port $PORT never came up — see /tmp/chrome-automation.log"; exit 1; }
  echo "✅ up on :$PORT"
  URL=""   # already loaded as a launch arg
fi

[ -n "$URL" ] && { open_tab "$URL"; echo "→ opened $URL"; }

# Bring the window forward so it is obvious which one to type into.
osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 &
sleep 0.2

echo
echo "profile : $PROFILE   (logins persist here)"
echo "tabs    :"
curl -sS --max-time 3 "http://127.0.0.1:$PORT/json/list" 2>/dev/null \
  | python3 -c "
import json,sys
try:
    for t in json.load(sys.stdin):
        if t.get('type') == 'page': print('   -', t.get('url'))
except Exception: pass
"
echo
echo "NOTE: while this is running, any local process can drive THIS profile."
echo "      Quit the window when you're done if that bothers you."
