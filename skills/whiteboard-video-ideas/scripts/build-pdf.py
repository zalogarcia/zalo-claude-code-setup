#!/usr/bin/env python3
"""Build the whiteboard PDF ("like last time"): a cover page, then one Letter page per video
with the title, hook, beats, close, reel line and the board cropped large enough to copy.

Usage: python3 build-pdf.py <spec.json> <out.pdf>
Spec "kind": "ideas" (cover lists the ideas to pick from) or "plan" (cover lists today's
shoot order, long form then its reel). Boards are read from <spec dir>/<folder>/board.png
(or the video's "board" key, relative to the spec dir) and cropped to the writing surface.
Set "cover": false in the spec to skip the cover page (one page per video only).
Rendered with headless Chrome --print-to-pdf, which writes the file and then hangs, so the
process is killed once the PDF size is stable.
"""
import base64
import html
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

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

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CROP = (92, 170, 1152, 890)  # writing surface of the 1152x1536 board photo

CSS = """
@page { size: Letter; margin: 0.55in 0.6in; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #111; margin: 0; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
.kicker { font-size: 9pt; font-weight: 700; letter-spacing: 0.12em; color: #444; text-transform: uppercase; }
h1 { font-size: 21pt; margin: 4px 0 10px; line-height: 1.15; }
h2 { font-size: 12pt; margin: 16px 0 6px; padding-bottom: 4px; border-bottom: 1.5px solid #111; }
ul, ol { margin: 0; padding-left: 18px; }
li { font-size: 10pt; line-height: 1.35; margin: 2px 0; }
.step { color: #555; white-space: nowrap; }
.small { font-size: 8.5pt; color: #444; margin-top: 6px; }
.board { margin-top: 10px; text-align: center; }
.board img { width: 100%; max-height: 4.75in; object-fit: contain; border: 1px solid #ddd; }
.cap { font-size: 8pt; color: #444; text-align: center; margin-top: 2px; }
.draw { font-size: 8.5pt; color: #222; margin-top: 4px; line-height: 1.3; }
.reel { margin-top: 8px; border: 1.5px solid #111; border-radius: 6px; padding: 6px 10px; font-size: 10pt; }
.keys { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; font-size: 10pt; }
.sw { display: inline-block; width: 16px; height: 16px; border-radius: 3px; vertical-align: middle; margin-right: 8px; }
.idea { font-size: 10pt; margin: 6px 0; }
.idea b { font-size: 10.5pt; }
"""

GUIDE = [
    "Boards: about 6 words each, colors per the key above.",
    "Long form: horizontal, about 8 to 10 minutes, draw while you talk, one point at a time, "
    "a 2 second pause between points so every point can also be cut into a reel later.",
    "Reel: phone vertical, step closer, 30 to 45 seconds, the hook in the first 2 seconds, one idea, "
    "end with \"link in bio to try it\".",
    "Light from the sides and shoot a little off center (the board is glossy); keep the wall outlet out of the frame.",
    "Every long form ends the same way: try the demo, link below.",
]


def e(s: str) -> str:
    return html.escape(s, quote=False)


def board_uri(root: Path, v: dict) -> str:
    src = root / v.get("board", f"{v['folder']}/board.png")
    im = Image.open(src).convert("RGB")
    if im.size == (1152, 1536):
        im = im.crop(CROP)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def cover(spec: dict) -> str:
    out = [f'<div class="page"><div class="kicker">{e(spec["kicker"])}</div><h1>{e(spec["date_label"])}</h1>']
    if spec.get("intro"):
        out.append(f'<p class="idea">{e(spec["intro"])}</p>')
    if spec["kind"] == "plan":
        out.append("<h2>Today's order of shoots</h2><ol>")
        for v in spec["videos"]:
            out.append(f"<li><b>{e(v['code'])}: {e(v['title'])}</b></li>")
            out.append(f"<li>Reel (same board): \"{e(v['reel_headline'])}\", 30 to 45 s</li>")
        out.append('</ol><div class="small">Each reel is filmed right after its long form, on the same board.</div>')
    else:
        out.append(f"<h2>Pick 3 of these {len(spec['videos'])}</h2>")
        for v in spec["videos"]:
            out.append(f'<div class="idea"><b>#{v["num"]} {e(v["title"])}</b><br>Hook: {e(v["hook"])}</div>')
    out.append(
        '<h2>Color key</h2><div class="keys">'
        '<div><span class="sw" style="background:#111"></span>Black = the business</div>'
        '<div><span class="sw" style="background:#1f5fd6"></span>Blue = the customer</div>'
        '<div><span class="sw" style="background:#d62828"></span>Red = the problem or money lost</div>'
        '<div><span class="sw" style="background:#1e9e45"></span>Green = the fix or booked</div></div>'
    )
    out.append("<h2>Filming guide</h2><ul>" + "".join(f"<li>{e(g)}</li>" for g in GUIDE) + "</ul></div>")
    return "".join(out)


def draw_line(v: dict) -> str:
    steps = [d for d in v.get("draw", []) if d.get("step") not in (None, "", "none")]
    if not steps:
        return ""
    parts = [f'{e(d["step"])} {e(d["what"])} ({e(d["marker"])})' for d in steps]
    return '<div class="draw"><b>Draw order:</b> ' + " &nbsp;".join(parts) + "</div>"


def video_page(spec: dict, root: Path, i: int, v: dict) -> str:
    n = len(spec["videos"])
    if spec["kind"] == "plan":
        kicker = f"{v['code']} · LONG FORM {i} OF {n} · THEN THE REEL"
    else:
        kicker = f"#{v['num']} · IDEA {i} OF {n} · {v['length'].upper()} · THEN A REEL"
    items = [f"<li><b>Hook:</b> {e(v['hook'])}</li>"]
    for b in v["beats"]:
        step = f' <span class="step">{e(b["s"])}</span>' if b.get("s") else ""
        items.append(f"<li>{e(b['t'])}{step}</li>")
    items.append(f"<li><b>Close:</b> {e(v['close'])}</li>")
    return (
        f'<div class="page"><div class="kicker">{e(kicker)}</div><h1>{e(v["title"])}</h1>'
        f'<ul>{"".join(items)}</ul>'
        f'<div class="board"><img src="{board_uri(root, v)}"></div>'
        f'<div class="cap">Board: {e(v["board_words"])}</div>'
        f'{draw_line(v)}'
        f'<div class="reel"><b>Reel (same board):</b> "{e(v["reel_headline"])}", 30 to 45 s. {e(v["reel_idea"])}</div>'
        "</div>"
    )


def render(html_text: str, out_pdf: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="wbpdf-"))
    src = tmp / "plan.html"
    src.write_text(html_text)
    profile = tmp / "profile"
    if out_pdf.exists():
        out_pdf.unlink()
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
         f"--print-to-pdf={out_pdf}", src.as_uri()],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    last, stable = -1, 0
    for _ in range(120):  # up to 60 s
        time.sleep(0.5)
        size = out_pdf.stat().st_size if out_pdf.exists() else -1
        if proc.poll() is not None:
            break
        stable = stable + 1 if size > 0 and size == last else 0
        if stable >= 3:
            break
        last = size
    if proc.poll() is None:
        proc.kill()
    subprocess.run(["pkill", "-f", f"user-data-dir={profile}"], check=False)
    shutil.rmtree(tmp, ignore_errors=True)
    if not out_pdf.exists() or out_pdf.stat().st_size == 0:
        raise SystemExit(f"FAILED: Chrome wrote no PDF at {out_pdf}")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    spec_path, out_pdf = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
    if not out_pdf.parent.is_dir():
        print(f"FAILED: output folder {out_pdf.parent} does not exist", file=sys.stderr)
        return 2
    spec = json.loads(spec_path.read_text())
    err = check_spec(spec)
    if err:
        print(err, file=sys.stderr)
        return 2
    root = spec_path.parent
    for v in spec["videos"]:
        board = root / v.get("board", f"{v['folder']}/board.png")
        if not board.exists():
            print(f"FAILED: no board for video {v['num']} at {board}", file=sys.stderr)
            return 2
    pages = ([cover(spec)] if spec.get("cover", True) else []) + [
        video_page(spec, root, i, v) for i, v in enumerate(spec["videos"], 1)
    ]
    doc = f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'
    render(doc, out_pdf)
    print(f"wrote {out_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
