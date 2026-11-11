"""Cut a Nano Banana mascot circle and compose the newsletter brand images (Urubu News format)."""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

PAPER, INK, GREY = (0xF4, 0xEF, 0xE6), (0x1C, 0x1C, 0x1C), (0x6B, 0x6B, 0x6B)
# Oswald (OFL): https://github.com/google/fonts/raw/main/ofl/oswald/Oswald%5Bwght%5D.ttf
FONT = "fonts/Oswald.ttf"


def hexrgb(h):
    return tuple(int(h[i : i + 2], 16) for i in (1, 3, 5))


def cut_circle(path):
    """Bounding box of the dark disc (the fake checkerboard is light grey) -> RGBA 512x512."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()

    def dark(p):
        return max(p) < 60

    rows = [y for y in range(h) if sum(dark(px[x, y]) for x in range(0, w, 2)) > 20]
    cols = [x for x in range(w) if sum(dark(px[x, y]) for y in range(0, h, 2)) > 20]
    top, bottom, left, right = rows[0], rows[-1], cols[0], cols[-1]
    side = max(bottom - top, right - left)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    box = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
    disc = im.crop(box).resize((1024, 1024), Image.LANCZOS)
    mask = Image.new("L", (4096, 4096), 0)
    ImageDraw.Draw(mask).ellipse((8, 8, 4088, 4088), fill=255)
    out = disc.convert("RGBA")
    out.putalpha(mask.resize((1024, 1024), Image.LANCZOS))
    return out.resize((512, 512), Image.LANCZOS)


def font(size, weight=700):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def wordmark(icon, first, second, c1, c2, size=(640, 255), icon_h=205):
    canvas = Image.new("RGB", size, PAPER)
    ic = icon.resize((icon_h, icon_h), Image.LANCZOS)
    pad = (size[1] - icon_h) // 2
    canvas.paste(ic, (pad, pad), ic)
    draw = ImageDraw.Draw(canvas)
    x0 = pad + icon_h + 22
    avail = size[0] - x0 - pad
    s = 120
    while True:
        f = font(s)
        w1 = draw.textlength(first.upper() + " ", font=f)
        w2 = draw.textlength(second.upper(), font=f)
        if w1 + w2 <= avail or s < 30:
            break
        s -= 2
    asc, desc = f.getmetrics()
    bbox = draw.textbbox((0, 0), first.upper(), font=f)
    y = (size[1] - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((x0, y), first.upper() + " ", font=f, fill=c1)
    draw.text((x0 + w1, y), second.upper(), font=f, fill=c2)
    return canvas


def og(logo, tagline):
    canvas = Image.new("RGB", (1200, 630), PAPER)
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
    os.makedirs(out, exist_ok=True)
    icon = cut_circle(src)
    save_small(icon, f"{out}/icon-512.png", 64)
    logo = wordmark(icon, first, second, hexrgb(c1), hexrgb(c2), size=(1280, 510), icon_h=410)
    save_small(logo.resize((640, 255), Image.LANCZOS), f"{out}/logo-email.png")
    save_small(og(logo, f"Notícias do {team}, antes e depois de cada jogo"), f"{out}/og-image.png")
    for f in ("icon-512", "logo-email", "og-image"):
        print(f, os.path.getsize(f"{out}/{f}.png") // 1024, "KB")
