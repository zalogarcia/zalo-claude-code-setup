#!/usr/bin/env python3
"""Generate yellow-bar subtitle overlay PNGs for split-screen videos.

Usage:
    python3 generate_subtitles.py <project_dir> [speed]

Args:
    project_dir: Directory containing subtitles.srt and assets/ folder
    speed: Playback speed multiplier (default: 1.2)

Outputs:
    assets/subs/sub_01.png ... sub_NN.png (transparent RGBA overlays)
    Prints FFmpeg overlay timing for the build script
"""

from PIL import Image, ImageDraw, ImageFont
import os
import re
import sys

# --- Configuration ---
WIDTH = 1080
HEIGHT = 1920
BAR_CENTER_Y = 960  # Split line between top B-roll and bottom presenter

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_SIZE = 48
PADDING_X = 32
PADDING_Y = 14
CORNER_RADIUS = 14
MARGIN = 40  # Minimum margin on each side of screen
MAX_BAR_W = WIDTH - (MARGIN * 2)  # = 1000px
YELLOW = (255, 224, 0, 255)
TEXT_COLOR = (0, 0, 0, 255)


def parse_srt(path):
    with open(path, 'r') as f:
        content = f.read()
    blocks = re.split(r'\n\n+', content.strip())
    subs = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        idx = int(lines[0])
        times = lines[1]
        text = '\n'.join(lines[2:])
        match = re.match(r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)', times)
        if match:
            g = match.groups()
            start = int(g[0])*3600 + int(g[1])*60 + int(g[2]) + int(g[3])/1000
            end = int(g[4])*3600 + int(g[5])*60 + int(g[6]) + int(g[7])/1000
            subs.append({'idx': idx, 'start': start, 'end': end, 'text': text})
    return subs


def wrap_text(text, font, max_text_width):
    """Word-wrap text to fit within max_text_width pixels."""
    dummy = Image.new('RGBA', (1, 1))
    dd = ImageDraw.Draw(dummy)
    input_lines = text.split('\n')
    wrapped_lines = []
    for line in input_lines:
        bbox = dd.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        if line_w <= max_text_width:
            wrapped_lines.append(line)
        else:
            words = line.split()
            current = ""
            for word in words:
                test = (current + " " + word).strip()
                bbox = dd.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] <= max_text_width:
                    current = test
                else:
                    if current:
                        wrapped_lines.append(current)
                    current = word
            if current:
                wrapped_lines.append(current)
    return '\n'.join(wrapped_lines)


def create_subtitle_image(text, idx, out_dir):
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    max_text_width = MAX_BAR_W - (PADDING_X * 2)
    wrapped = wrap_text(text, font, max_text_width)

    dummy = Image.new('RGBA', (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.multiline_textbbox((0, 0), wrapped, font=font, align='center')
    text_y_offset = bbox[1]
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    bar_w = min(tw + PADDING_X * 2, MAX_BAR_W)
    bar_h = th + PADDING_Y * 2

    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bar_x = (WIDTH - bar_w) // 2
    bar_y = BAR_CENTER_Y - bar_h // 2

    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
        radius=CORNER_RADIUS, fill=YELLOW
    )

    text_x = bar_x + PADDING_X - bbox[0]
    text_y = bar_y + PADDING_Y - text_y_offset
    draw.multiline_text((text_x, text_y), wrapped, font=font, fill=TEXT_COLOR, align='center')

    out_path = os.path.join(out_dir, f"sub_{idx:02d}.png")
    img.save(out_path)
    print(f"Created: {out_path} (bar {bar_w}x{bar_h}, margin {bar_x}px)")
    return out_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_subtitles.py <project_dir> [speed]")
        sys.exit(1)

    project_dir = sys.argv[1]
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2

    srt_path = os.path.join(project_dir, "subtitles.srt")
    out_dir = os.path.join(project_dir, "assets", "subs")
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(srt_path):
        print(f"Error: {srt_path} not found")
        sys.exit(1)

    subs = parse_srt(srt_path)
    print(f"Parsed {len(subs)} subtitles from {srt_path}")

    for sub in subs:
        create_subtitle_image(sub['text'], sub['idx'], out_dir)

    print(f"\n# FFmpeg overlay timing (after {speed}x speed):")
    for sub in subs:
        s = sub['start'] / speed
        e = sub['end'] / speed
        print(f"# Sub {sub['idx']:2d}: {s:.2f} - {e:.2f}  | {sub['text'][:50]}")


if __name__ == "__main__":
    main()
