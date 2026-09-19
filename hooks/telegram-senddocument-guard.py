#!/usr/bin/env python3
"""PreToolUse guard: block Telegram `sendVideo` — review clips go as documents.

Why this exists
---------------
Telegram RE-ENCODES anything sent via `sendVideo`. Zalo reviews every reel on
his phone, and on 2026-08-01 he flagged that his avatar looked soft in the
delivered clips. Measurement chain: our files are full 1080x1920 and nothing in
our pipeline downscales — but the copies he was watching had been through
Telegram's compressor. Re-sent byte-identical via `sendDocument`, his verdict
was immediate: "the file version on telegram looks better. Always send them
like that to view."

That makes sendVideo actively harmful here: it silently degrades the artifact
the review decision is made on, so real defects hide and phantom ones appear.
Worst case, a genuine quality problem gets "fixed" that was never in the file.

Prose in a brief cannot hold this — briefs are written per job and background
workers each start fresh with no memory of the ruling. A hook applies to every
session, including every bg worker, forever.

What it blocks
--------------
Bash commands POSTing to api.telegram.org/.../sendVideo.

What it allows
--------------
sendDocument, sendPhoto, sendMessage, sendAudio, and everything non-Telegram.
sendPhoto stays allowed: stills are for glancing at, Telegram's still handling
is far gentler, and comparison PNGs are routinely sent that way.

Exit 0 = allow. Exit 2 = block (stderr is shown to Claude).
"""

import json
import re
import sys

# Matches the Bot API method regardless of quoting/spacing around the URL:
#   https://api.telegram.org/bot<TOKEN>/sendVideo
# Token is opaque, so match the host and the method separately but require the
# telegram host to be present in the same command.
TELEGRAM_HOST = re.compile(r"api\.telegram\.org", re.I)
SEND_VIDEO = re.compile(r"/send[Vv]ideo\b|\bsendVideo\b")

MESSAGE = """BLOCKED (telegram-senddocument-guard): sendVideo re-encodes the file.

Telegram compresses anything sent as a VIDEO. Zalo reviews reels on his phone
and judged the compressed copies as looking soft; sent byte-identical via
sendDocument he said "the file version on telegram looks better. Always send
them like that to view." (2026-08-01, standing rule.)

Sending a re-encoded copy means he reviews an artifact that is NOT the one you
built — real defects hide, phantom ones appear.

Use sendDocument instead:

  curl -s -X POST "https://api.telegram.org/bot${TOK}/sendDocument" \\
    -F "chat_id=${CID}" \\
    -F "document=@/path/to/clip.mp4" \\
    -F "caption=P2 A2P - v11" \\
    -F "disable_content_type_detection=true"

Stills (sendPhoto) and audio (sendAudio) are unaffected — only video is.
If the file exceeds Telegram's 50MB bot limit, send a smaller ENCODE as a
document (e.g. 720p CRF 26) and say so in the caption — do not fall back to
sendVideo."""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail open — never wedge the session on a malformed payload

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        return 0

    if TELEGRAM_HOST.search(command) and SEND_VIDEO.search(command):
        print(MESSAGE, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
