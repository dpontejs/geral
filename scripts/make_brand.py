"""Cut a Nano Banana mascot circle and compose the newsletter brand images (Urubu News format)."""

import os
import sys
from collections import Counter

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PAPER, INK, GREY = (0xF4, 0xEF, 0xE6), (0x1C, 0x1C, 0x1C), (0x6B, 0x6B, 0x6B)
# Oswald (OFL): https://github.com/google/fonts/raw/main/ofl/oswald/Oswald%5Bwght%5D.ttf
FONT = "fonts/Oswald.ttf"


def hexrgb(h):
    return tuple(int(h[i : i + 2], 16) for i in (1, 3, 5))


def cut_mascot(path, circle=False):
    """Mascot on a transparent square (512x512).

    Nano Banana paints a fake transparency checkerboard (light, unsaturated). Everything
    light and grey that is connected to the image border is background; the mascot may
    leave its circle (the ABC elephant's trunk), so the cut follows the drawing, not a circle.
    """
    im = Image.open(path).convert("RGB")
    im.thumbnail((1400, 1400), Image.LANCZOS)  # originals are up to 2752 px; 512 is the output
    w, h = im.size
    px = im.load()
    # The checkerboard's two tones, read on the image border.
    border = [(x, y) for x in range(w) for y in (0, h - 1)]
    border += [(x, y) for y in range(h) for x in (0, w - 1)]
    counts = Counter(tuple(c // 8 * 8 for c in px[p]) for p in border)
    tones = sorted((t for t, _ in counts.most_common(2)), key=sum)  # [grey, white]

    def near(p, tone):
        return all(abs(a - b) <= 20 for a, b in zip(p, tone, strict=True))

    grey = Image.new("L", (w, h), 0)
    light = Image.new("L", (w, h), 0)
    gp, lp = grey.load(), light.load()
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if near(p, tones[0]):
                gp[x, y] = 255
            elif near(p, tones[1]):
                lp[x, y] = 255
    # A light pixel is background only next to the grey squares: the mascot's own white
    # (the ABC elephant's body) is far from any checker grey.
    near_grey = grey.filter(ImageFilter.MaxFilter(31))
    marks = Image.composite(light, Image.new("L", (w, h), 0), near_grey)
    marks = Image.composite(Image.new("L", (w, h), 255), marks, grey)
    mp = marks.load()
    for seed in border:
        if mp[seed] == 255:
            ImageDraw.floodfill(marks, seed, 128, thresh=0)
    alpha = marks.point(lambda v: 0 if v == 128 else 255)
    # Inside the circle nothing is background (the elephant's white body has checker-grey
    # shading); outside it only what touches the mascot stays (trunk, tusks), not stray specks.
    disc = _disc(im)
    if circle:  # the mascot fits in its circle: cut exactly there, whatever the background does
        alpha = disc
    alpha = Image.composite(Image.new("L", (w, h), 255), alpha, disc)
    ImageDraw.floodfill(alpha, (w // 2, h // 2), 200, thresh=0)
    alpha = alpha.point(lambda v: 255 if v == 200 else 0).filter(ImageFilter.MinFilter(3))
    out = im.convert("RGBA")
    out.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.6)))
    left, top, right, bottom = alpha.getbbox()
    side = max(right - left, bottom - top) + 8
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    offset = ((side - (right - left)) // 2, (side - (bottom - top)) // 2)
    square.paste(out.crop((left, top, right, bottom)), offset)
    return square.resize((512, 512), Image.LANCZOS)


def _disc(im):
    """Mask of the mascot's circle: the rows and columns dense with dark or saturated ink."""
    w, h = im.size
    px = im.load()

    def ink(p):
        return max(p) < 80 or max(p) - min(p) > 60

    rows = [sum(ink(px[x, y]) for x in range(0, w, 2)) for y in range(h)]
    cols = [sum(ink(px[x, y]) for y in range(0, h, 2)) for x in range(w)]
    ys = [y for y, n in enumerate(rows) if n > 0.25 * max(rows)]
    xs = [x for x, n in enumerate(cols) if n > 0.25 * max(cols)]
    side = min(ys[-1] - ys[0], xs[-1] - xs[0])
    cx, cy = (xs[0] + xs[-1]) // 2, (ys[0] + ys[-1]) // 2
    mask = Image.new("L", (w, h), 0)
    r = int(side / 2 * 1.035)  # ink stops inside the thin white ring; include it
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    return mask


def font(size, weight=700):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def wordmark(icon, first, second, c1, c2, size=(640, 255), icon_h=205, paper=PAPER):
    """Icon + name, centered; the name is as big as fits, up to half the icon's height."""
    canvas = Image.new("RGB", size, paper)
    ic = icon.resize((icon_h, icon_h), Image.LANCZOS)
    pad = (size[1] - icon_h) // 2
    gap = icon_h // 18
    draw = ImageDraw.Draw(canvas)
    first, second = first.upper(), second.upper()
    avail = size[0] - 2 * pad - icon_h - gap
    s = icon_h
    while s > 30:
        f = font(s)
        w1 = draw.textlength(first + (" " if second else ""), font=f)
        w2 = draw.textlength(second, font=f)
        top, bottom = draw.textbbox((0, 0), first, font=f)[1::2]
        if w1 + w2 <= avail and bottom - top <= icon_h * 0.5:
            break
        s -= 2
    x = int((size[0] - (icon_h + gap + w1 + w2)) // 2)
    canvas.paste(ic, (x, pad), ic)
    y = (size[1] - (bottom - top)) // 2 - top
    draw.text((x + icon_h + gap, y), first, font=f, fill=c1)
    draw.text((x + icon_h + gap + w1, y), second, font=f, fill=c2)
    return canvas


def og(logo, tagline, paper=PAPER):
    canvas = Image.new("RGB", (1200, 630), paper)
    lg = logo.resize((960, 383), Image.LANCZOS)
    canvas.paste(lg, (120, 70))
    draw = ImageDraw.Draw(canvas)
    f = font(40, 400)
    w = draw.textlength(tagline, font=f)
    draw.text(((1200 - w) / 2, 500), tagline, font=f, fill=GREY)
    return canvas


def save_small(im, path, colors=48):
    if im.mode == "RGBA":
        im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)
    else:
        im.convert("RGB").quantize(colors=colors).save(path, optimize=True)


if __name__ == "__main__":
    src, out, first, second, c1, c2, team = sys.argv[1:8]
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[8:])
    circle = "circle" in opts
    paper = hexrgb(opts["paper"]) if "paper" in opts else PAPER  # the hub: --paper=#EFE4CC
    tagline = opts.get("tagline", f"Notícias do {team}, antes e depois de cada jogo")
    os.makedirs(out, exist_ok=True)
    icon = cut_mascot(src, circle)
    save_small(icon, f"{out}/icon-512.png", 64)
    logo = wordmark(
        icon, first, second, hexrgb(c1), hexrgb(c2), size=(1280, 510), icon_h=410, paper=paper
    )
    save_small(logo.resize((640, 255), Image.LANCZOS), f"{out}/logo-email.png")
    save_small(og(logo, tagline, paper), f"{out}/og-image.png")
    for f in ("icon-512", "logo-email", "og-image"):
        print(f, os.path.getsize(f"{out}/{f}.png") // 1024, "KB")
