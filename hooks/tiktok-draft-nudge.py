#!/usr/bin/env python3
"""PostToolUse: after a TikTok DRAFT is pushed, require a Telegram nudge to Zalo.

Why this exists
---------------
TikTok cannot be auto-published: the API's publish scope is capped per API
client (Post for Me 403 `reached_active_user_cap`, hit twice) and TikTok's
audit policy rejects single-creator utility tools. The working rail is the
UPLOAD scope — the reel lands in Zalo's TikTok drafts and he taps publish
in-app.

That last step is human, so a pushed draft that nobody tells him about is a
post that silently never happens. He asked for this directly (2026-08-01):
"you just gotta nudge me when you post the drafts to tik tok so i remember to
post."

A prose rule in a brief cannot hold it — posting runs from background workers
that each start with no memory of this conversation. A hook fires in every
session, forever.

What it does
------------
Detects a Bash call that pushed a TikTok draft (a publish call carrying
`tiktokDraft`, or a status poll whose output shows TikTok's own
"Saved as draft" confirmation) and injects a non-blocking reminder to send the
nudge. It never sends anything itself — it only makes forgetting impossible.

Exit 0 always: this must never block a publish.
"""

import json
import re
import sys

PUBLISH_MARKERS = ("api/publish", "/publish")
DRAFT_MARKERS = ("tiktokdraft", "is_draft")
CONFIRMED_MARKERS = ("saved as draft", "check your tiktok inbox")
# Matching on tool OUTPUT is what makes this hook strong: it catches a draft
# TikTok confirmed even from a command shape nobody predicted (a wrapper script,
# a poller). But it also means merely READING a file that documents the rail
# fires it — `pipeline.md` quotes TikTok's own "Content saved as draft... Check
# your TikTok inbox notifications." verbatim, so `grep tiktokDraft pipeline.md`
# echoed the confirmation and nudged Zalo about a draft nobody pushed
# (observed 2026-08-02, mid-build).
#
# Fix: exclude READ-ONLY commands rather than demanding a specific call shape.
# Requiring `curl`/`/publish` in the command would also silence the legitimate
# wrapper-script case this hook exists to cover.
# Every token here must be incapable of publishing anything. `echo` belongs on
# this list: a compound read like `ls x && echo "---" && grep tiktokDraft spec.md`
# is still just a read, but omitting `echo` made `is_read_only` return False and
# the hook fired on the grep's output (observed 2026-08-02, second false alarm).
READ_ONLY_CMDS = (
    # readers / searchers
    "grep", "rg", "ag", "cat", "bat", "head", "tail", "less", "more",
    "sed", "awk", "find", "ls", "wc", "diff", "open", "strings", "jq",
    # glue that appears in compound reads and cannot publish
    "echo", "printf", "sort", "uniq", "tr", "cut", "column", "tee",
    "basename", "dirname", "stat", "file", "du", "date", "pwd", "cd",
    "true", "false", "test", "[", ":",
)
# ...unless the command ALSO talks to the network, since `cat body.json | curl`
# is a real push whose first token is a read verb.
NETWORK_MARKERS = ("curl", "wget", "http://", "https://", "requests.", "fetch(", "axios")

# A command whose SUBJECT is transcripts, saved results, hook sources or audit
# data is analysis ABOUT this rail, never a push through it. Such commands
# legitimately print TikTok's own confirmation wording (they are quoting a past
# firing) and legitimately carry JSON `"id":` fields, so every content-based
# test misreads them. This is the 2026-08-16/17 false-fire class: a transcript
# scan hunting for previous firings fired the hook it was auditing, and the
# fabricated nudge named a draft nobody pushed (audit 2026-08-28, P13).
# Checked against the command text only — output is untrusted by design here.
META_MARKERS = (
    ".claude/projects", ".claude/hooks", ".claude/usage-data",
    ".jsonl", "bg-results", "bg-queue", "tiktok-draft-nudge", "transcript",
)

# Interpreters running INLINE code: the code is fully visible in the command, so
# it can be judged on its own contents. `python3 script.py` is opaque and must
# NOT be listed here — a poller/wrapper script is a real push shape this hook
# exists to catch (see the "inbox-notification wording fires" test).
INLINE_INTERPRETERS = {
    "python": ("-c",), "python3": ("-c",), "perl": ("-e",), "ruby": ("-e",),
    "node": ("-e", "-p", "--eval", "--print"), "bun": ("-e",), "deno": ("eval",),
}


def is_read_only(command: str) -> bool:
    """True when every pipeline segment is a read and nothing hits the net.

    Judged PER SEGMENT, not over the whole command string. A network marker
    inside a reader's own arguments is a search pattern, not a call:
    `grep -n "curl" tiktok-draft-nudge.py` reads this very file, and a
    whole-string network test marked it as a possible push — then the file's
    quoted copy of TikTok's confirmation fired the hook, nudging Zalo about a
    draft nobody pushed (observed 2026-08-16, during a read-only memory sync).
    """
    low = command.lower()

    # Cut heredoc bodies FIRST. `python3 - <<'PY' ... PY` delivers fully
    # visible code on stdin, so it is judgeable exactly like `-c`, but its
    # body is prose-shaped: a stray `;` or `|` inside it splits into fake
    # pipeline segments whose leading token is something like `for` or
    # `json.dumps(r)`, which is in no allowlist, so the whole read reads as a
    # possible push. This is THE shape transcript and corpus scans are written
    # in, and it false-fired the hook during read-only memory-sync runs
    # (2026-08-17, ground-truthed by pulling the triggering command out of the
    # worker's own transcript rather than guessing a third time).
    heredoc_bodies: list[str] = []
    stripped = low
    while True:
        m = re.search(r"<<-?\s*(['\"]?)(\w+)\1", stripped)
        if not m:
            break
        delim = m.group(2)
        end = re.search(r"^\s*%s\s*$" % re.escape(delim), stripped[m.end():], re.M)
        if end:
            heredoc_bodies.append(stripped[m.end():m.end() + end.start()])
            stripped = stripped[:m.start()] + " " + stripped[m.end() + end.end():]
        else:  # unterminated: treat the remainder as the body
            heredoc_bodies.append(stripped[m.end():])
            stripped = stripped[:m.start()]
            break
    # The body is code we can read: trust it only if it cannot reach the net.
    if any(mk in b for b in heredoc_bodies for mk in NETWORK_MARKERS):
        return False
    had_heredoc = bool(heredoc_bodies)
    low = stripped

    # Mask quoted spans BEFORE splitting: `python3 -c "import json,sys; ..."`
    # carries a `;` inside its own code, and splitting on it blindly made the
    # code's second half look like a separate command whose leading token was
    # `[print(l)` — not a reader — so a plain transcript read was treated as a
    # possible push (the 2026-08-16 memory-sync false alarm).
    quoted: list[str] = []

    def _mask(m: re.Match) -> str:
        quoted.append(m.group(0))
        return "\x00%d\x00" % (len(quoted) - 1)

    masked = re.sub(r"'[^']*'|\"[^\"]*\"", _mask, low)
    segments = [s.strip() for s in masked.replace("&&", "|").replace(";", "|").split("|")]
    words = [s.split() for s in segments if s.split()]
    if not words:
        return False

    def _unmask(text: str) -> str:
        return re.sub(r"\x00(\d+)\x00", lambda m: quoted[int(m.group(1))], text)

    for w in words:
        token = w[0].rsplit("/", 1)[-1]
        if token in READ_ONLY_CMDS:
            continue  # a reader is a reader whatever its pattern text contains
        flags = INLINE_INTERPRETERS.get(token)
        # `python3 - <<'PY'` and bare `python3 <<'PY'` are the stdin form of
        # inline code; the body was already network-checked above.
        if flags and had_heredoc and (len(w) == 1 or w[1] == "-"):
            continue
        if flags and len(w) > 1 and w[1] in flags:
            # Inline code is visible: trust it only if it cannot reach the net.
            if any(m in _unmask(" ".join(w)) for m in NETWORK_MARKERS):
                return False
            continue
        return False
    return True

REMINDER = """TIKTOK DRAFT PUSHED — send Zalo a Telegram nudge NOW, before you do anything else.

He asked for this explicitly (2026-08-01): "you just gotta nudge me when you post the drafts to tik tok so i remember to post."

TikTok drafts do NOT publish themselves. He has to open the TikTok app and tap publish. A draft he was never told about is a post that never happens.

The nudge must say:
  - WHICH video was drafted (piece + what it's about, not a filename)
  - that it is waiting in his TikTok inbox/drafts and needs him to tap publish
  - anything he should add in-app (trending audio / native text — the reason drafts can outperform direct posts)

Send it as a normal Telegram message (sendMessage). If you are a background worker, creds are NOT in env: run `python3 /tmp/tg-creds.py` and parse its printed TOK= / CID= lines."""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # fail open

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        return 0
    low = command.lower()

    response = payload.get("tool_response")
    if isinstance(response, dict):
        out = str(response.get("stdout", "")) + str(response.get("stderr", ""))
    else:
        out = str(response or "")
    out_low = out.lower()

    # PRECONDITION: reading or searching a file that merely MENTIONS the rail is
    # not a push, however perfectly its contents match.
    if is_read_only(command):
        return 0

    # THE PRINCIPLE, learned over three false alarms on 2026-08-02:
    # **evidence of a push lives in the OUTPUT, never in the command text.**
    # Command text alone cannot distinguish
    #   - running a publish            (a push)
    #   - WRITING a script that publishes (`cat > sched.py <<'PY' ... tiktokDraft ...`)
    #   - dry-running that script      (prints a plan, sends nothing)
    #   - grepping the spec that documents it
    # All four contain "api/publish" and "tiktokDraft". Only the first produces
    # a submission receipt. So require one:
    #   (a) TikTok's own confirmation wording, or
    #   (b) a post id / terminal status in the output of a draft-flagged call.
    # AUTHORING guard: `cat > sched.py <<'PY' ... PY` WRITES a publisher, it does
    # not run one. Its body legitimately contains curl, http:// and tiktokDraft,
    # so every content-based test misreads it. A heredoc redirected into a file
    # is the giveaway.
    if re.search(r">\s*\S+[\s\S]*<<", command):
        return 0

    # META guard (P13): reading/scanning the rail's own records is not a push,
    # however perfectly the records match. This runs BEFORE any output test
    # precisely because the output of such a command is a quotation.
    if any(m in low for m in META_MARKERS):
        return 0

    confirmed = any(m in out_low for m in CONFIRMED_MARKERS)
    # A receipt: PFM post id, or a JSON id field.
    # A Post-for-Me submission id IS a receipt on its own. A bare JSON `"id":`
    # is not — any asset listing has those — so it needs corroborating
    # draft/publish wording in the SAME output (P13, audit 2026-08-28).
    strong_receipt = bool(re.search(r"\bsp_[A-Za-z0-9]{8,}", out))
    weak_receipt = bool(re.search(r'"id"\s*:\s*"', out))
    networked = any(m in low for m in NETWORK_MARKERS)
    draft_flagged = any(m in low for m in PUBLISH_MARKERS) and any(
        m in low for m in DRAFT_MARKERS
    )
    tiktok_ctx = "tiktok" in low or "tiktok" in out_low

    # Two shapes of real push, deliberately kept separate:
    #  1. the command IS the network publish and carries a draft flag — fires
    #     even when the response was not captured, because the call went out;
    #  2. a wrapper script (no publish markers in its argv) that PRODUCED
    #     receipts — this is what distinguishes `--go` from a dry run, which
    #     prints the same plan but no ids.
    receipt_ctx = any(m in out_low for m in ("draft", "publish", "post_id", "status"))
    receipt = strong_receipt or (weak_receipt and receipt_ctx)
    pushed = (draft_flagged and networked) or (receipt and tiktok_ctx)

    if not (confirmed or pushed):
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": REMINDER,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
