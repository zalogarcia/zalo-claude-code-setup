#!/usr/bin/env python3
"""Write beats.md per video, plus an optional index .md, from one ideas spec JSON.

Usage: python3 write-beats.py <spec.json> [--index <out.md>]
The spec's directory is the content root; each video's beats.md goes to <root>/<folder>/beats.md.
Spec shape: see ../SKILL.md "Spec fields". Every string must already be free of em and en dashes.
"""
import json
import sys
from pathlib import Path

REQUIRED = ("num", "code", "folder", "title", "formula", "research", "why", "hook", "beats", "close",
            "reel_headline", "reel_idea", "length", "board_words", "draw")


def check_spec(spec: dict) -> str:
    """Return an error line for the first missing key, or an empty string."""
    for k in ("kind", "kicker", "date_label", "videos"):
        if k not in spec:
            return f"FAILED: spec missing top level key {k}"
    for v in spec["videos"]:
        missing = [k for k in REQUIRED if k not in v]
        if missing:
            return f"FAILED: video {v.get('num', '?')} missing {', '.join(missing)}"
    return ""


def beats_md(v: dict) -> str:
    lines = [f"# Video {v['num']} ({v['code']}): {v['title']}", ""]
    if v.get("board_note"):
        lines += [v["board_note"], ""]
    lines += [
        "## Title",
        "",
        f"**{v['title']}**",
        "",
        f"Formula: {v['formula']}",
        "",
    ]
    if v.get("alt_titles"):
        lines += ["Alt titles for the 3 title split test: " + "; ".join(v["alt_titles"]), ""]
    lines += [
        "## Why it will pull views",
        "",
        f"Research question {v['research']} in `../research-2026-09-24.md`. {v['why']}",
        "",
        "## Hook (first 5 seconds)",
        "",
        v["hook"],
        "",
        "## Beats",
        "",
    ]
    for b in v["beats"]:
        step = f"{b['s']} " if b.get("s") else ""
        lines.append(f"- {step}{b['t']}")
    lines += [
        "",
        "## Close (AI demo CTA)",
        "",
        v["close"],
        "",
        "## Reel (30 to 45 s, vertical, same board, filmed right after)",
        "",
        f"Headline: \"{v['reel_headline']}\". {v['reel_idea']}",
        "",
        "## Length",
        "",
        f"Long form {v['length']}; reel 30 to 45 seconds.",
        "",
        f"## Board words",
        "",
        v["board_words"],
        "",
        "## Draw order",
        "",
        "| Step | What you draw | Marker | Draw it during |",
        "| --- | --- | --- | --- |",
    ]
    for d in v["draw"]:
        lines.append(f"| {d['step']} | {d['what']} | {d['marker']} | {d['during']} |")
    lines.append("")
    if v.get("notes"):
        lines += ["## Notes", ""] + [f"- {n}" for n in v["notes"]] + [""]
    lines.append(
        "Color key: black = the business, blue = the customer and the call, "
        "red = the problem or money lost, green = the fix or booked."
    )
    return "\n".join(lines) + "\n"


def index_md(spec: dict) -> str:
    lines = [f"# {spec['kicker'].title()}, {spec['date_label']}", "", spec.get("intro", ""), ""]
    for v in spec["videos"]:
        lines += [
            f"## #{v['num']} {v['title']}",
            "",
            f"- Hook: {v['hook']}",
            f"- Why: {v['why']}",
            f"- Board: {v['board_words']} (`{v['folder']}/board.png`)",
            f"- Reel: \"{v['reel_headline']}\"",
            f"- Beats: `{v['folder']}/beats.md`",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    spec_path = Path(args[0])
    index_out = None
    if "--index" in args:
        i = args.index("--index")
        if i + 1 >= len(args):
            print("FAILED: --index needs an output path", file=sys.stderr)
            return 2
        index_out = Path(args[i + 1])
    spec = json.loads(spec_path.read_text())
    err = check_spec(spec)
    if err:
        print(err, file=sys.stderr)
        return 2
    root = spec_path.parent
    for v in spec["videos"]:
        folder = root / v["folder"]
        folder.mkdir(exist_ok=True)
        (folder / "beats.md").write_text(beats_md(v))
        print(f"wrote {folder / 'beats.md'}")
    if index_out:
        index_out.write_text(index_md(spec))
        print(f"wrote {index_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
