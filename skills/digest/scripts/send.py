#!/usr/bin/env python3
"""send.py: deliver a digest to Zalo's Telegram in the fixed order, text first.

Usage:
  send.py --text FILE [--photo PNG | --document FILE] [--shot PNG]
          [--caption TEXT | --caption-file FILE] [--allow-lint-findings] [--dry-run]

Order is fixed: 1) the text as a message (always, first), 2) the ONE extra: a diagram
(--photo) or a page (--document, with --shot as its phone screenshot photo).
Gates before anything is sent:
  - the text passes ste-lint.py (override: --allow-lint-findings, and say why in the report)
  - no em or en dash in the text or the caption
  - not both --photo and --document (one extra; pick-format.py decides which)
  - the shared Telegram cooldown (~/dev/claude-telegram-bridge/tg-throttle.json) is clear
Captions go as --form-string (never -F, which cuts the value at a ';').
It only calls sendMessage, sendPhoto and sendDocument. It never edits a message.
A photo that Telegram would refuse (width + height over 10000, a side ratio over 20,
or over 10 MB) is sent as a document instead.
Prints one JSON line per send with the message_id. The text or caption Telegram echoes back
must equal what was sent, or that send counts as failed (a cut caption is a failed send).
Exit codes: 0 all sent, 1 a gate failed or a send failed, 2 bad usage, 3 throttled.
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THROTTLE = os.environ.get("DIGEST_TG_THROTTLE") or os.path.expanduser("~/dev/claude-telegram-bridge/tg-throttle.json")
DASHES = ("‒", "–", "—", "―")


def creds():
    tok = cid = ""
    for p in ("~/.claude/settings.local.json", "~/.claude/settings.json"):
        try:
            with open(os.path.expanduser(p)) as fh:
                env = json.load(fh).get("env", {})
        except (OSError, ValueError):
            continue
        tok = tok or env.get("TELEGRAM_BOT_TOKEN", "")
        cid = cid or env.get("TELEGRAM_CHAT_ID", "")
    return tok, cid


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def throttled():
    try:
        with open(THROTTLE) as fh:
            until = json.load(fh).get("until", 0)
    except (OSError, ValueError):
        return 0
    left = until / 1000 - time.time()
    return left if left > 0 else 0


def chunks(text, limit=4000):
    """Split on blank lines so no message breaks inside a paragraph."""
    out, cur = [], ""
    for para in text.split("\n\n"):
        piece = para if not cur else cur + "\n\n" + para
        if len(piece) <= limit:
            cur = piece
            continue
        if cur:
            out.append(cur)
        while len(para) > limit:
            out.append(para[:limit])
            para = para[limit:]
        cur = para
    if cur:
        out.append(cur)
    return out


def echo_ok(fields, result):
    """The response carries what Telegram stored: it must equal what was sent."""
    for key in ("text", "caption"):
        if key in fields and (result.get(key) or "").strip() != fields[key].strip():
            return False
    return True


def call(tok, method, fields, files=None, dry=False):
    if dry:
        return {"ok": True, "result": {"message_id": None}, "dry_run": True}
    cfg = 'url = "https://api.telegram.org/bot%s/%s"\n' % (tok, method)
    cmd = ["curl", "-sS", "--max-time", "120", "-K", "-", "-X", "POST"]
    for k, v in fields.items():
        cmd += ["--form-string", "%s=%s" % (k, v)]
    for k, path in (files or {}).items():
        # Quote the path: curl -F reads an unquoted , or ; in it as syntax.
        cmd += ["-F", '%s=@"%s"' % (k, path.replace("\\", "\\\\").replace('"', '\\"'))]
    p = subprocess.run(cmd, input=cfg, capture_output=True, text=True)  # token via stdin, not argv
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"ok": False, "description": (p.stderr or p.stdout)[:300]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Send a digest: text first, then one extra.")
    ap.add_argument("--text", required=True)
    ap.add_argument("--photo")
    ap.add_argument("--document")
    ap.add_argument("--shot", help="phone screenshot to send after a --document page")
    ap.add_argument("--caption")
    ap.add_argument("--caption-file")
    ap.add_argument("--allow-lint-findings", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.photo and a.document:
        print("send: one extra only (a diagram OR a page); run pick-format.py", file=sys.stderr)
        return 2
    if a.shot and not a.document:
        print("send: --shot goes with --document (the page's phone screenshot)", file=sys.stderr)
        return 2
    for f in [a.text, a.photo, a.document, a.shot, a.caption_file]:
        if f and not os.path.isfile(f):
            print("send: missing file %s" % f, file=sys.stderr)
            return 2
    with open(a.text, encoding="utf-8") as fh:
        text = fh.read().strip()
    caption = a.caption or ""
    if a.caption_file:
        with open(a.caption_file, encoding="utf-8") as fh:
            caption = fh.read().strip()
    if not text:
        print("send: the text is empty; text is always the main output", file=sys.stderr)
        return 1
    if len(caption) > 1024:
        print("send: the caption is %d characters; Telegram allows 1024" % len(caption), file=sys.stderr)
        return 1
    if any(d in text + caption for d in DASHES):
        print("send: em or en dash in the text or caption (Zalo's rule); fix it first", file=sys.stderr)
        return 1
    lint = subprocess.run([sys.executable, os.path.join(HERE, "ste-lint.py"), a.text], capture_output=True, text=True)
    if lint.returncode != 0 and not a.allow_lint_findings:
        sys.stderr.write(lint.stdout + lint.stderr)
        print("send: ste-lint found problems; fix them or pass --allow-lint-findings", file=sys.stderr)
        return 1
    left = throttled()
    if left:
        print("send: Telegram is throttling the bot for %d more minutes; nothing sent" % (left / 60 + 1), file=sys.stderr)
        return 3
    tok, cid = creds()
    if not (tok and cid) and not a.dry_run:
        print("send: no TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in ~/.claude/settings.local.json", file=sys.stderr)
        return 1

    plan = [("sendMessage", {"chat_id": cid, "text": part}, None) for part in chunks(text)]
    def too_big(path):
        size = png_size(path)
        return os.path.getsize(path) > 10 * 1024 * 1024 or bool(
            size and (size[0] + size[1] > 10000 or max(size) / max(1, min(size)) > 20))

    if a.photo:
        if too_big(a.photo):
            plan.append(("sendDocument", {"chat_id": cid, "caption": caption}, {"document": a.photo}))
        else:
            plan.append(("sendPhoto", {"chat_id": cid, "caption": caption}, {"photo": a.photo}))
    if a.document:
        plan.append(("sendDocument", {"chat_id": cid, "caption": caption}, {"document": a.document}))
        if a.shot:
            method, field = ("sendDocument", "document") if too_big(a.shot) else ("sendPhoto", "photo")
            plan.append((method, {"chat_id": cid, "caption": "Phone view of the page above."}, {field: a.shot}))

    failed = False
    for i, (method, fields, files) in enumerate(plan):
        if i:
            time.sleep(1.2)  # the bot shares one per-chat budget with the bridge
        fields = {k: v for k, v in fields.items() if v != ""}
        r = call(tok, method, fields, files, a.dry_run)
        res = r.get("result") or {}
        if r.get("ok") and not a.dry_run and not echo_ok(fields, res):
            r = {"ok": False, "description": "Telegram stored a different text or caption than was sent (cut or altered)"}
        print(json.dumps({"method": method, "ok": bool(r.get("ok")), "message_id": res.get("message_id"),
                          "file": (list(files.values())[0] if files else None),
                          "error": None if r.get("ok") else r.get("description"), "dry_run": a.dry_run}))
        if not r.get("ok"):
            failed = True
            if r.get("error_code") == 429:
                retry = (r.get("parameters") or {}).get("retry_after", 60)
                try:
                    now = int(time.time() * 1000)
                    if now + (retry + 1) * 1000 <= throttled() * 1000 + now:
                        break  # an existing, later deadline already holds the other senders
                    with open(THROTTLE, "w") as fh:
                        json.dump({"until": now + (retry + 1) * 1000, "retryAfter": retry, "method": method,
                                   "at": now, "source": "digest-send"}, fh)
                except OSError:
                    pass
            break
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
