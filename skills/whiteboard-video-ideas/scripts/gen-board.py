#!/usr/bin/env python3
"""Generate one whiteboard board image: gpt-image-2 images.edit on Zalo's board photo.

Usage: python3 gen-board.py <prompt.txt> <out.png> [--photo <board-photo.jpg>]
Settings (measured, see memory whiteboard-youtube-direction.md): size 1152x1536 (3:4),
quality high, stream=True with partial_images=2 (the non streaming call is cut at 60 s).
The first line of the prompt file may be "INPUT: <file>" and is stripped before sending.
Needs OPENAI_API_KEY. gpt-image-2 only (never nano-banana).
Run several in parallel with `&` and `wait` inside ONE foreground command (about 100 s each).
"""
import base64
import sys
from pathlib import Path

from openai import OpenAI

PHOTO = Path.home() / "dev/claude-telegram-bridge/inbox/1790268071550_photo_18080.jpg"


def main() -> int:
    args = sys.argv[1:]
    photo = PHOTO
    if "--photo" in args:
        i = args.index("--photo")
        if i + 1 >= len(args):
            print("FAILED: --photo needs a path", file=sys.stderr)
            return 2
        photo = Path(args[i + 1]).expanduser()
        del args[i : i + 2]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    prompt_path, out_path = Path(args[0]), Path(args[1])
    if not photo.exists():
        print(f"FAILED: board photo not found at {photo}", file=sys.stderr)
        return 2
    lines = prompt_path.read_text().splitlines()
    if lines and lines[0].startswith("INPUT:"):
        lines = lines[1:]
    prompt = "\n".join(lines).strip()

    client = OpenAI()
    with photo.open("rb") as fh:
        stream = client.images.edit(
            model="gpt-image-2",
            image=fh,
            prompt=prompt,
            size="1152x1536",
            quality="high",
            stream=True,
            partial_images=2,
        )
        final_b64 = None
        for event in stream:
            if getattr(event, "type", "") == "image_edit.completed":
                final_b64 = event.b64_json
    if not final_b64:
        print(f"FAILED: no completed image for {prompt_path.name}", file=sys.stderr)
        return 1
    out_path.write_bytes(base64.b64decode(final_b64))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
