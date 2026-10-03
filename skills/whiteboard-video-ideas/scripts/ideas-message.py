#!/usr/bin/env python3
"""Stage 1 of whiteboard-video-ideas: the ideas as ONE plain Telegram text, no boards.

Usage: python3 ideas-message.py <spec.json> <out.txt> [--desc-dir <dir>]
Per idea: "#N Title", the hook, a one line why (the evidence) and the reel line, then
"Reply with 3 numbers to shoot." Uses "why_short" when present, else "why".
--desc-dir also writes <dir>/LF<N>.md per idea, the description for its Linear Idea card.
Needs per video: num, title, hook, why (or why_short), reel_headline.
"""
import json
import sys
from pathlib import Path

REQUIRED = ("num", "title", "hook", "reel_headline")


def main() -> int:
    args = sys.argv[1:]
    desc_dir = None
    if "--desc-dir" in args:
        i = args.index("--desc-dir")
        if i + 1 >= len(args):
            print("FAILED: --desc-dir needs a directory", file=sys.stderr)
            return 2
        desc_dir = Path(args[i + 1])
        del args[i : i + 2]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    spec = json.loads(Path(args[0]).read_text())
    if not spec.get("videos"):
        print("FAILED: spec has no videos", file=sys.stderr)
        return 2
    for v in spec["videos"]:
        missing = [k for k in REQUIRED if k not in v] + ([] if ("why" in v or "why_short" in v) else ["why"])
        if missing:
            print(f"FAILED: video {v.get('num', '?')} missing {', '.join(missing)}", file=sys.stderr)
            return 2
    n = len(spec["videos"])
    lines = [f"{n} new whiteboard video ideas:", ""]
    for v in spec["videos"]:
        why = v.get("why_short") or v["why"]
        block = [
            f"#{v['num']} {v['title']}",
            f"Hook: {v['hook']}",
            f"Why: {why}",
            f"Reel: \"{v['reel_headline']}\"",
        ]
        lines += block + [""]
        if desc_dir:
            desc_dir.mkdir(parents=True, exist_ok=True)
            code = v.get("code", f"LF{v['num']}")
            (desc_dir / f"{code}.md").write_text("\n\n".join(block) + "\n\nIdea only: no board or beats yet. They are made when Zalo picks it.\n")
    lines.append("Reply with 3 numbers to shoot.")
    text = "\n".join(lines)
    if len(text) > 4096:
        print(f"FAILED: {len(text)} chars, Telegram caps a message at 4096; add a one line why_short per idea", file=sys.stderr)
        return 2
    Path(args[1]).write_text(text)
    print(f"wrote {args[1]} ({len(chr(10).join(lines))} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
