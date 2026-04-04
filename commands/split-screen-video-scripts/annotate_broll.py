#!/usr/bin/env python3
"""Add red arrows, circles, and green arrows to B-roll images.

Usage:
    python3 annotate_broll.py <image_path> <annotation_type> <params...>

Annotation types:
    red_arrow   <start_x%> <start_y%> <end_x%> <end_y%> [head_size] [shaft_width]
    red_circle  <center_x%> <center_y%> <radius%> [width]
    green_arrow <start_x%> <start_y%> <end_x%> <end_y%> [head_size] [shaft_width]

All coordinates are percentages (0-100) of image dimensions.
Saves annotated version to <image_path> (overwrites original).
To preserve originals, copy them first.

Examples:
    python3 annotate_broll.py assets/broll_gutter.png red_arrow 12 85 42 35
    python3 annotate_broll.py assets/broll_hand.png red_circle 48 52 22
    python3 annotate_broll.py assets/broll_shingle.png green_arrow 25 5 25 30
"""

from PIL import Image, ImageDraw
import math
import os
import sys


def draw_3d_arrow(img, start, end, color=(220, 30, 30), head_size=60, shaft_width=28):
    """Draw a 3D-style arrow with shadow and highlight effect."""
    draw = ImageDraw.Draw(img)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx*dx + dy*dy)
    if length == 0:
        return

    ux, uy = dx/length, dy/length
    px, py = -uy, ux
    head_base_x = end[0] - ux * head_size
    head_base_y = end[1] - uy * head_size
    sx, sy = 4, 4
    hw = shaft_width / 2
    hh = head_size * 0.7

    # Shadow
    shadow_pts = [
        (start[0]+px*hw+sx, start[1]+py*hw+sy),
        (head_base_x+px*hw+sx, head_base_y+py*hw+sy),
        (head_base_x+px*hh+sx, head_base_y+py*hh+sy),
        (end[0]+sx, end[1]+sy),
        (head_base_x-px*hh+sx, head_base_y-py*hh+sy),
        (head_base_x-px*hw+sx, head_base_y-py*hw+sy),
        (start[0]-px*hw+sx, start[1]-py*hw+sy),
    ]
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).polygon(shadow_pts, fill=(40, 0, 0, 160))
    img.paste(Image.alpha_composite(Image.new('RGBA', img.size, (0,0,0,0)), overlay), (0,0), overlay)

    # Main arrow
    arrow_pts = [
        (start[0]+px*hw, start[1]+py*hw),
        (head_base_x+px*hw, head_base_y+py*hw),
        (head_base_x+px*hh, head_base_y+py*hh),
        (end[0], end[1]),
        (head_base_x-px*hh, head_base_y-py*hh),
        (head_base_x-px*hw, head_base_y-py*hw),
        (start[0]-px*hw, start[1]-py*hw),
    ]
    draw = ImageDraw.Draw(img)
    draw.polygon([(x-2, y-2) for x, y in arrow_pts], fill=(100, 0, 0))
    draw.polygon(arrow_pts, fill=color)

    # Highlight stripe
    hl_pts = [
        (start[0]+px*hw*0.3, start[1]+py*hw*0.3),
        (head_base_x+px*hw*0.3, head_base_y+py*hw*0.3),
        (head_base_x+px*hw*0.8, head_base_y+py*hw*0.8),
        (start[0]+px*hw*0.8, start[1]+py*hw*0.8),
    ]
    hl = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).polygon(hl_pts, fill=(255, 120, 120, 100))
    img.paste(Image.alpha_composite(Image.new('RGBA', img.size, (0,0,0,0)), hl), (0,0), hl)


def draw_circle_annotation(img, center, radius, color=(220, 30, 30), width=8):
    """Draw a thick circle with shadow."""
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        [center[0]-radius+3, center[1]-radius+3, center[0]+radius+3, center[1]+radius+3],
        outline=(40, 0, 0, 180), width=width+2
    )
    draw.ellipse(
        [center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius],
        outline=color, width=width
    )


def draw_green_arrow(img, start, end, head_size=50, shaft_width=22):
    """Draw a green arrow for positive highlights."""
    draw_3d_arrow(img, start, end, color=(80, 210, 50), head_size=head_size, shaft_width=shaft_width)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    image_path = sys.argv[1]
    annotation_type = sys.argv[2]

    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found")
        sys.exit(1)

    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    if annotation_type == "red_arrow":
        sx = float(sys.argv[3]) / 100 * w
        sy = float(sys.argv[4]) / 100 * h
        ex = float(sys.argv[5]) / 100 * w
        ey = float(sys.argv[6]) / 100 * h
        hs = int(sys.argv[7]) if len(sys.argv) > 7 else 70
        sw = int(sys.argv[8]) if len(sys.argv) > 8 else 32
        draw_3d_arrow(img, (sx, sy), (ex, ey), head_size=hs, shaft_width=sw)
        print(f"Added red arrow to {image_path}")

    elif annotation_type == "red_circle":
        cx = float(sys.argv[3]) / 100 * w
        cy = float(sys.argv[4]) / 100 * h
        r = float(sys.argv[5]) / 100 * min(w, h)
        lw = int(sys.argv[6]) if len(sys.argv) > 6 else 10
        draw_circle_annotation(img, (cx, cy), int(r), width=lw)
        print(f"Added red circle to {image_path}")

    elif annotation_type == "green_arrow":
        sx = float(sys.argv[3]) / 100 * w
        sy = float(sys.argv[4]) / 100 * h
        ex = float(sys.argv[5]) / 100 * w
        ey = float(sys.argv[6]) / 100 * h
        hs = int(sys.argv[7]) if len(sys.argv) > 7 else 55
        sw = int(sys.argv[8]) if len(sys.argv) > 8 else 24
        draw_green_arrow(img, (sx, sy), (ex, ey), head_size=hs, shaft_width=sw)
        print(f"Added green arrow to {image_path}")

    else:
        print(f"Unknown annotation type: {annotation_type}")
        print("Valid types: red_arrow, red_circle, green_arrow")
        sys.exit(1)

    img.save(image_path)
    print(f"Saved: {image_path} ({w}x{h})")


if __name__ == "__main__":
    main()
