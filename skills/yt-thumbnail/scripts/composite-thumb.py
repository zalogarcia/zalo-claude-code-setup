#!/usr/bin/env python3
"""Composite the REAL Zalo (a screened 4K video frame) onto a gpt-image-2 plate, so his face is never redrawn.

Usage:
  composite-thumb.py header <plate.png> <still.jpg> <mask.png> <out.png> --scale S --offset X Y
  composite-thumb.py social <plate.png> <still.jpg> <mask.png> <out.png> --face-px N --face-center X Y
  composite-thumb.py big    <plate.png> <still.jpg> <mask.png> <out.png> --face-px N [--avoid-orange]

header: the plate is a gpt-image-2 render of the same frame; the real frame is scaled and offset onto it
        (a +-1.5% scale and +-8 px local search refines the given transform), then the person is pasted
        with a slightly dilated, feathered mask so no sliver of the rendered man shows.
social: the plate has no person; the cut out is scaled so the face box is N px tall and its center lands
        on the given point.
big:    the plate has no person; the cut out is centered under the white number with the top of the hair
        overlapping the bottom 12 percent of the number.
The mask is Apple Vision person segmentation of the still (accurate). Thin spikes above the head (the
board's top bar) are removed with an opening; the lavalier mic is painted out for social and big.
Pure PIL (numpy on this Mac's python3 is the wrong architecture).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageStat

FACE_TOOL = os.environ.get("FACE_TOOL", "/tmp/ytwb/face")  # Vision face box helper (compile: swiftc -O scripts/face.swift -o /tmp/ytwb/face); prints "<name> x y w h"


def face_box(path):
    out = subprocess.run([FACE_TOOL, str(path)], capture_output=True, text=True).stdout.split()
    if len(out) < 5:
        sys.exit(f"no face found in {path}")
    return int(out[1]), int(out[2]), int(out[3])


MASK_LEVELS = None  # (lo, hi): alpha below lo -> 0, above hi -> 255, linear between; set by --mask-levels


def clean_mask(mask, face):
    if MASK_LEVELS:
        lo, hi = MASK_LEVELS
        mask = mask.point(lambda v: 0 if v <= lo else (255 if v >= hi else int((v - lo) * 255 / (hi - lo))))
    x, y, s = face
    box = (max(0, x - int(0.6 * s)), max(0, y - int(0.9 * s)), x + int(1.6 * s), y)
    sub = mask.crop(box).filter(ImageFilter.MinFilter(31)).filter(ImageFilter.MaxFilter(31))
    mask.paste(sub, box)
    return mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))


def remove_mic(img, face, mask):
    """Find the mic's green LED on his chest (inside the person mask) and clone plain tee over the mic."""
    x, y, s = face
    region = (x - int(0.8 * s), y + int(1.2 * s), x + int(1.8 * s), min(img.height, y + int(3.0 * s)))
    sub = img.crop(region)
    msub = mask.crop(region).load()
    px = sub.load()
    pts = [(i, j) for j in range(sub.height) for i in range(sub.width)
           if msub[i, j] > 150 and px[i, j][1] > 150
           and px[i, j][1] > px[i, j][0] + 18 and px[i, j][1] > px[i, j][2] + 40]
    if not pts:
        return img, None, mask
    cx = region[0] + sum(p[0] for p in pts) // len(pts)
    cy = region[1] + sum(p[1] for p in pts) // len(pts)
    w, h = int(0.36 * s), int(0.40 * s)
    tgt = (cx - w // 2, cy - h // 3, cx + w // 2, cy + 2 * h // 3)
    # clone source: plain tee beside the mic, on whichever side lies fully inside the person mask
    best = None
    for src_dx in (int(0.42 * s), -int(0.42 * s), int(0.60 * s), -int(0.60 * s)):
        sb = (tgt[0] + src_dx, tgt[1], tgt[2] + src_dx, tgt[3])
        if sb[0] < 0 or sb[2] > img.width:
            continue
        inside = ImageStat.Stat(mask.crop(sb)).mean[0]
        spread = ImageStat.Stat(img.crop(sb).convert("L")).stddev[0]
        score = (inside >= 250, -spread)
        if best is None or score > best[0]:
            best = (score, sb)
    patch = img.crop(best[1])
    m = Image.new("L", patch.size, 0)
    ImageDraw.Draw(m).ellipse((4, 4, patch.width - 4, patch.height - 4), fill=255)
    # tone match: the source's border ring to the target's border ring (the mic itself sits inside)
    ring = Image.new("L", patch.size, 255)
    ImageDraw.Draw(ring).ellipse((10, 10, patch.width - 10, patch.height - 10), fill=0)
    tmean = ImageStat.Stat(img.crop(tgt), ring).mean
    smean = ImageStat.Stat(patch, ring).mean
    patch = Image.merge("RGB", [ch.point(lambda v, d=tmean[k] - smean[k]: max(0, min(255, int(v + d))))
                                for k, ch in enumerate(patch.split())])
    m = m.filter(ImageFilter.GaussianBlur(max(2, w // 10)))
    img = img.copy()
    img.paste(patch, tgt[:2], m)
    # Vision leaves a hole in the mask at the bright LED: close it under the patch
    mask = mask.copy()
    hole = Image.new("L", mask.size, 0)
    hole.paste(m, tgt[:2])
    mask = ImageChops.lighter(mask, hole)
    return img, (cx, cy), mask


def keep_body(lmask, seed):
    """Keep only the part of the layer mask connected to the face (drops a hand or marker cut off by the frame)."""
    W, H = lmask.size
    small = lmask.resize((W // 4, H // 4)).point(lambda v: 255 if v > 64 else 0)
    sx, sy = max(0, min(small.width - 1, seed[0] // 4)), max(0, min(small.height - 1, seed[1] // 4))
    if small.getpixel((sx, sy)) != 255:
        return lmask
    ImageDraw.floodfill(small, (sx, sy), 128)
    body = small.point(lambda v: 255 if v == 128 else 0).filter(ImageFilter.MaxFilter(5))
    body = body.resize((W, H), Image.BILINEAR).filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(3))
    return ImageChops.multiply(lmask, body)


def place(plate, img, mask, scale, ox, oy):
    W, H = img.size
    nw, nh = int(W * scale), int(H * scale)
    im2 = img.resize((nw, nh), Image.LANCZOS)
    m2 = mask.resize((nw, nh), Image.LANCZOS)
    layer = Image.new("RGB", plate.size)
    lmask = Image.new("L", plate.size, 0)
    layer.paste(im2, (int(round(ox)), int(round(oy))))
    lmask.paste(m2, (int(round(ox)), int(round(oy))))
    return layer, lmask


def align(plate, img, mask, s0, ox0, oy0):
    """Refine scale and offset of the real frame onto the plate (person region, grey, half size)."""
    bb = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
    pg = plate.convert("L").resize((plate.width // 2, plate.height // 2))
    best = None
    for ds in (-0.015, -0.0075, 0, 0.0075, 0.015):
        sc = s0 * (1 + ds)
        crop = img.crop(bb).convert("L")
        cw, ch = int(crop.width * sc / 2), int(crop.height * sc / 2)
        small = crop.resize((cw, ch), Image.BILINEAR)
        msmall = mask.crop(bb).resize((cw, ch), Image.BILINEAR)
        for dx in range(-8, 9, 2):
            for dy in range(-8, 9, 2):
                px = (ox0 + dx + bb[0] * sc) / 2
                py = (oy0 + dy + bb[1] * sc) / 2
                region = pg.crop((int(px), int(py), int(px) + cw, int(py) + ch))
                diff = ImageChops.difference(region, small)
                score = ImageStat.Stat(diff, msmall).mean[0]
                if best is None or score < best[0]:
                    best = (score, sc, ox0 + dx, oy0 + dy)
    return best


def hframe(a):
    """Header from a DIFFERENT moment of the same static camera take: the whole real frame (room, board and
    man) graded to the plate's look, with the plate's headline band kept on top.

    --orig-still/--orig-mask: the frame the plate was rendered from (sets the alignment and the grade).
    --zoom Z: scale the finished frame by Z about the top center (keeps the headline, enlarges the face)."""
    plate = Image.open(a.plate).convert("RGB")
    W, H = plate.size
    orig = Image.open(a.orig_still).convert("RGB")
    omask = clean_mask(Image.open(a.orig_mask).convert("L"), face_box(a.orig_still))
    score, sc, ox, oy = align(plate, orig, omask, a.scale, a.offset[0], a.offset[1])
    new = Image.open(a.still).convert("RGB")
    nw, nh = int(orig.width * sc), int(orig.height * sc)
    def onto(im):
        layer = Image.new("RGB", (W, H))
        layer.paste(im.resize((nw, nh), Image.LANCZOS), (int(round(ox)), int(round(oy))))
        return layer
    Ao, An = onto(orig), onto(new)
    cover = Image.new("L", (W, H), 0)
    cover.paste(255, (int(round(ox)) + 2, int(round(oy)) + 2, int(round(ox)) + nw - 2, int(round(oy)) + nh - 2))
    # headline band: bright white or orange pixels in the top 40 percent of the plate
    pl = plate.load()
    # the orange headline word marks the headline line (white pixels would also catch the whiteboard)
    ys = sorted(j for j in range(0, int(H * 0.4), 2) for i in range(0, W, 4)
                if pl[i, j][0] > 230 and 60 < pl[i, j][1] < 125 and pl[i, j][2] < 45)
    top = [j for j in ys if j < ys[0] + 260]  # the headline line only, not red ink on the board below
    band_bottom = max(top) + 30
    # grade 1: per channel tone curve real -> plate, fitted below the band inside the frame
    fitm = cover.copy()
    ImageDraw.Draw(fitm).rectangle((0, 0, W, band_bottom + 40), fill=0)
    luts = []
    for k in range(3):
        a_ch, p_ch = Ao.getchannel(k).load(), plate.getchannel(k).load()
        fm = fitm.load()
        sums, cnts = [0] * 256, [0] * 256
        for j in range(0, H, 3):
            for i in range(0, W, 3):
                if fm[i, j]:
                    v = a_ch[i, j]
                    sums[v] += p_ch[i, j]
                    cnts[v] += 1
        lut, last = [], 0
        known = [(v, sums[v] / cnts[v]) for v in range(256) if cnts[v] >= 20]
        for v in range(256):
            lo = max([kv for kv in known if kv[0] <= v], default=known[0])
            hi = min([kv for kv in known if kv[0] >= v], default=known[-1])
            val = lo[1] if hi[0] == lo[0] else lo[1] + (hi[1] - lo[1]) * (v - lo[0]) / (hi[0] - lo[0])
            last = max(last, val)
            lut.append(int(min(255, last)))
        luts.extend(lut)
    Go = Ao.point(luts)
    Gn = An.point(luts)
    # grade 2: low frequency gain (vignette, local light) plate / graded original
    R = []
    for k in range(3):
        num = plate.getchannel(k).filter(ImageFilter.GaussianBlur(40))
        den = Go.getchannel(k).filter(ImageFilter.GaussianBlur(40))
        n_, d_ = num.load(), den.load()
        g = Image.new("L", (W, H))
        gp = g.load()
        for j in range(H):
            for i in range(W):
                d = max(8, d_[i, j])
                gp[i, j] = int(max(0.5, min(2.0, n_[i, j] / d)) * 100)
        R.append(g)
    chans = []
    for k in range(3):
        c = Gn.getchannel(k).load()
        g = R[k].load()
        o = Image.new("L", (W, H))
        op = o.load()
        for j in range(H):
            for i in range(W):
                op[i, j] = min(255, c[i, j] * g[i, j] // 100)
        chans.append(o)
    graded = Image.merge("RGB", chans)
    nface = face_box(a.still)
    nmask = clean_mask(Image.open(a.mask).convert("L"), nface)
    lm = Image.new("L", (W, H), 0)
    lm.paste(nmask.resize((nw, nh), Image.LANCZOS), (int(round(ox)), int(round(oy))))
    lm = lm.filter(ImageFilter.GaussianBlur(2))
    if a.frame_zoom and a.frame_zoom != 1:
        # enlarge the real scene only (the headline band stays native size) about an anchor point
        z, (ax, ay) = a.frame_zoom, a.frame_anchor
        def zoom(im):
            zw, zh = int(W * z), int(H * z)
            big = im.resize((zw, zh), Image.LANCZOS)
            x0, y0 = int(ax * z - ax), int(ay * z - ay)
            canvas = Image.new(im.mode, (W, H), 0)
            canvas.paste(big, (-x0, -y0))
            return canvas
        graded, An, lm, cover = zoom(graded), zoom(An), zoom(lm), zoom(cover)
    # paste the graded real frame below the band (feathered), keep the plate's headline band and edges
    w = Image.new("L", (W, H), 0)
    ImageDraw.Draw(w).rectangle((0, band_bottom, W, H), fill=255)
    cov = cover.filter(ImageFilter.MinFilter(25)).filter(ImageFilter.GaussianBlur(14))
    w = ImageChops.multiply(w.filter(ImageFilter.GaussianBlur(30)), cov)
    out = Image.composite(graded, plate, w)
    # the man himself is pasted as raw footage pixels (no grade), as in header mode, whole even in the band
    out = Image.composite(An, out, lm)
    if a.zoom and a.zoom != 1:
        zw, zh = int(W * a.zoom), int(H * a.zoom)
        big = out.resize((zw, zh), Image.LANCZOS)
        x0 = (zw - W) // 2
        out = big.crop((x0, 0, x0 + W, H))
    out.save(a.out)
    print(f"hframe: align diff {score:.2f} scale {sc:.4f} offset ({ox}, {oy}) band_bottom {band_bottom} zoom {a.zoom}")


def header(a):
    plate = Image.open(a.plate).convert("RGB")
    img = Image.open(a.still).convert("RGB")
    face = face_box(a.still)
    mask = clean_mask(Image.open(a.mask).convert("L"), face)
    s0, ox0, oy0 = a.scale, a.offset[0], a.offset[1]
    # local search on a half size grey copy, over the person's box
    bb = mask.point(lambda v: 255 if v > 128 else 0).getbbox()
    pg = plate.convert("L").resize((plate.width // 2, plate.height // 2))
    best = None
    for ds in (-0.015, -0.0075, 0, 0.0075, 0.015):
        sc = s0 * (1 + ds)
        crop = img.crop(bb).convert("L")
        cw, ch = int(crop.width * sc / 2), int(crop.height * sc / 2)
        small = crop.resize((cw, ch), Image.BILINEAR)
        msmall = mask.crop(bb).resize((cw, ch), Image.BILINEAR)
        for dx in range(-8, 9, 2):
            for dy in range(-8, 9, 2):
                px = (ox0 + dx + bb[0] * sc) / 2
                py = (oy0 + dy + bb[1] * sc) / 2
                region = pg.crop((int(px), int(py), int(px) + cw, int(py) + ch))
                diff = ImageChops.difference(region, small)
                score = ImageStat.Stat(diff, msmall).mean[0]
                if best is None or score < best[0]:
                    best = (score, sc, ox0 + dx, oy0 + dy)
    _, sc, ox, oy = best
    layer, lmask = place(plate, img, mask, sc, ox, oy)
    lmask = lmask.filter(ImageFilter.MaxFilter(13)).filter(ImageFilter.GaussianBlur(3))
    out = Image.composite(layer, plate, lmask)
    if a.zoom and a.zoom != 1:
        W, H = out.size
        zw, zh = int(W * a.zoom), int(H * a.zoom)
        x0 = (zw - W) // 2
        out = out.resize((zw, zh), Image.LANCZOS).crop((x0, 0, x0 + W, H))
    out.save(a.out)
    print(f"header: scale {sc:.4f} offset ({ox}, {oy}) diff {best[0]:.2f}")


def social(a):
    plate = Image.open(a.plate).convert("RGB")
    img = Image.open(a.still).convert("RGB")
    face = face_box(a.still)
    mask = clean_mask(Image.open(a.mask).convert("L"), face)
    img, mic, mask = remove_mic(img, face, mask)
    x, y, s = face
    sc = a.face_px / s
    ox = a.face_center[0] - (x + s / 2) * sc
    oy = a.face_center[1] - (y + s / 2) * sc
    layer, lmask = place(plate, img, mask, sc, ox, oy)
    out = Image.composite(layer, plate, lmask)
    # the quote stays in front of him: key the bright text out of the plate and lay it back on top
    qx0 = int(plate.width * 0.36)
    quote = plate.crop((qx0, 0, plate.width, plate.height))
    key = quote.convert("RGB").point(lambda v: v)
    r, g, b = key.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    alpha = mx.point(lambda v: 0 if v < 90 else (255 if v > 200 else int((v - 90) * 255 / 110)))
    out.paste(quote, (qx0, 0), alpha)
    out.save(a.out)
    print(f"social: scale {sc:.4f} offset ({ox:.0f}, {oy:.0f}) mic {mic}")


def big(a):
    plate = Image.open(a.plate).convert("RGB")
    img = Image.open(a.still).convert("RGB")
    face = face_box(a.still)
    mask = clean_mask(Image.open(a.mask).convert("L"), face)
    img, mic, mask = remove_mic(img, face, mask)
    # the white number: bright, unsaturated pixels in the top 70 percent
    pl = plate.load()
    top = int(plate.height * 0.7)
    xs, ys = [], []
    for j in range(0, top, 3):
        for i in range(0, plate.width, 3):
            r, g, b = pl[i, j]
            if r > 225 and g > 225 and b > 225:
                xs.append(i)
                ys.append(j)
    nx0, nx1, ny0, ny1 = min(xs), max(xs), min(ys), max(ys)
    x, y, s = face
    sc = a.face_px / s
    # top of the hair: first mask row above the face inside the face's columns
    mk = mask.load()
    hair_top = y
    for j in range(max(0, y - s), y):
        if any(mk[i, j] > 128 for i in range(x, x + s, 4)):
            hair_top = j
            break
    # orange label under the number (e.g. "DEMOS"): measured before the field is rebuilt, re-laid on top later
    lab = None
    if a.label_scale:
        lx, ly = [], []
        for j in range(ny1, plate.height, 2):
            for i in range(0, plate.width, 2):
                r, g, b = pl[i, j]
                if r > 200 and g < 150 and b < 110:
                    lx.append(i)
                    ly.append(j)
        if not lx:
            sys.exit("no orange label found under the number")
        lab = (min(lx) - 6, min(ly) - 6, max(lx) + 8, max(ly) + 8)
    target_top = ny1 - 0.12 * (ny1 - ny0)
    head_cx = a.face_x if a.face_x is not None else (nx0 + nx1) / 2
    ox = head_cx - (x + s / 2) * sc
    oy = target_top - hair_top * sc
    # lift the person a touch for the bright field
    img = ImageEnhance.Brightness(img).enhance(1.12)
    layer, lmask = place(plate, img, mask, sc, ox, oy)
    lmask = keep_body(lmask, (int((x + s / 2) * sc + ox), int((y + s / 2) * sc + oy)))
    # clean field: per row, the plate's own edge blue (left and right 40 px), plus one soft glow behind his head
    W, H = plate.size
    field = Image.new("RGB", (W, H))
    fd = ImageDraw.Draw(field)
    for j in range(H):
        l = plate.crop((0, j, 40, j + 1)).resize((1, 1), Image.BOX).getpixel((0, 0))
        rr = plate.crop((W - 40, j, W, j + 1)).resize((1, 1), Image.BOX).getpixel((0, 0))
        fd.line([(0, j), (W, j)], fill=tuple((l[k] + rr[k]) // 2 for k in range(3)))
    hx = int((x + s / 2) * sc + ox)
    hy = int((y + s / 2) * sc + oy)
    gl = Image.new("L", (W, H), 0)
    ImageDraw.Draw(gl).ellipse((hx - 520, hy - 300, hx + 520, H + 400), fill=255)
    gl = gl.filter(ImageFilter.GaussianBlur(160))
    field = Image.composite(Image.new("RGB", (W, H), (70, 175, 255)), field, gl.point(lambda v: int(v * 0.55)))
    # keep the plate (number and its shadow) down to just under the number, feathered into the clean field
    keep = Image.new("L", (W, H), 0)
    ImageDraw.Draw(keep).rectangle((0, 0, W, ny1 + 30), fill=255)
    keep = keep.filter(ImageFilter.GaussianBlur(25))
    base = Image.composite(plate, field, keep)
    if lab:
        crop = plate.crop(lab)
        r, _, b = crop.split()
        # alpha from the red channel: blue field r ~0 to 60, orange r ~250
        alpha = r.point(lambda v: 0 if v < 60 else (255 if v > 235 else int((v - 60) * 255 / 175)))
        k = a.label_scale
        nw, nh = int(crop.width * k), int(crop.height * k)
        alpha = alpha.resize((nw, nh), Image.LANCZOS)
        fill = Image.new("RGB", (nw, nh), (252, 88, 4))
        # erase the original label (and its halo) from the base with the clean field
        er = Image.new("L", (W, H), 0)
        er.paste(alpha_full := r.point(lambda v: 0 if v < 40 else 255), lab[:2])
        er = er.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(6))
        base = Image.composite(field, base, er)
        lx0 = lab[0] if a.label_x is None else a.label_x
        ly0 = int(ny1 + a.label_gap)
        sh = Image.new("L", (W, H), 0)
        sh.paste(alpha, (lx0 + 10, ly0 + 12))
        sh = sh.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.6))
        base = Image.composite(Image.new("RGB", (W, H), (0, 18, 70)), base, sh)
        base.paste(fill, (lx0, ly0), alpha)
        print(f"label: plate box {lab} scale {k} placed at ({lx0}, {ly0}) size {nw}x{nh}")
    out = Image.composite(layer, base, lmask)
    out.save(a.out)
    print(f"big: number box ({nx0},{ny0})-({nx1},{ny1}) scale {sc:.4f} offset ({ox:.0f}, {oy:.0f}) mic {mic}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["header", "hframe", "social", "big"])
    p.add_argument("plate")
    p.add_argument("still")
    p.add_argument("mask")
    p.add_argument("out")
    p.add_argument("--scale", type=float)
    p.add_argument("--offset", type=float, nargs=2)
    p.add_argument("--face-px", type=float)
    p.add_argument("--face-center", type=float, nargs=2)
    p.add_argument("--face-x", type=float, help="big: head center x (default: under the number's center)")
    p.add_argument("--label-scale", type=float, help="big: keep the plate's orange label, scaled by this")
    p.add_argument("--label-x", type=int, help="big: label left x (default: where the plate had it)")
    p.add_argument("--label-gap", type=float, default=28, help="big: px between number bottom and label top")
    p.add_argument("--mask-levels", type=int, nargs=2, help="alpha below LO -> 0, above HI -> 255")
    p.add_argument("--orig-still", help="hframe: the frame the plate was rendered from")
    p.add_argument("--orig-mask", help="hframe: person mask of --orig-still")
    p.add_argument("--zoom", type=float, default=1.0, help="header/hframe: scale the finished image about the top center")
    p.add_argument("--frame-zoom", type=float, default=1.0, help="hframe: enlarge the real scene only, headline unchanged")
    p.add_argument("--frame-anchor", type=float, nargs=2, default=(1024, 870), help="hframe: fixed point of --frame-zoom")
    a = p.parse_args()
    global MASK_LEVELS
    MASK_LEVELS = tuple(a.mask_levels) if a.mask_levels else None
    {"header": header, "hframe": hframe, "social": social, "big": big}[a.mode](a)


if __name__ == "__main__":
    main()
