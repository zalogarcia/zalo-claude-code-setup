#!/usr/bin/env python3
"""Contact sheet of the boards in a spec: a grid of cropped boards, "#N short title" under each.

Usage: python3 contact-sheet.py <spec.json> <out.png> [--cols 3]
Uses each video's "short" (falls back to "title") and <spec dir>/<folder>/board.png.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CROP = (92, 170, 1152, 890)
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    spec_path, out = Path(args[0]), Path(args[1])
    cols = 3
    if "--cols" in args:
        i = args.index("--cols")
        if i + 1 >= len(args) or not args[i + 1].isdigit() or int(args[i + 1]) < 1:
            print("FAILED: --cols needs a positive number", file=sys.stderr)
            return 2
        cols = int(args[i + 1])
    spec = json.loads(spec_path.read_text())
    for v in spec.get("videos", []):
        missing = [k for k in ("num", "folder", "title") if k not in v]
        if missing:
            print(f"FAILED: video {v.get('num', '?')} missing {', '.join(missing)}", file=sys.stderr)
            return 2
    if not spec.get("videos"):
        print("FAILED: spec has no videos", file=sys.stderr)
        return 2
    root = spec_path.parent
    tile_w, tile_h, label_h, pad = 700, 476, 64, 24
    vids = spec["videos"]
    rows = (len(vids) + cols - 1) // cols
    sheet = Image.new("RGB", (pad + cols * (tile_w + pad), pad + rows * (tile_h + label_h + pad)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT, 34, index=1)  # Helvetica Neue Bold
    for i, v in enumerate(vids):
        src = root / v.get("board", f"{v['folder']}/board.png")
        if not src.exists():
            print(f"FAILED: no board for video {v['num']} at {src}", file=sys.stderr)
            return 2
        im = Image.open(src).convert("RGB")
        if im.size == (1152, 1536):
            im = im.crop(CROP)
        im = im.resize((tile_w, tile_h))
        x = pad + (i % cols) * (tile_w + pad)
        y = pad + (i // cols) * (tile_h + label_h + pad)
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + tile_h + 12), f"#{v['num']} {v.get('short', v['title'])}", fill="black", font=font)
    sheet.save(out)
    print(f"wrote {out} {sheet.size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
