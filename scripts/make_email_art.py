"""Draw the edição geral's field art (docs/features/identidade-geral.md).

campo-topo.png: the striped grass behind the e-mail's top, with the chalk arc in the corner. It is
a background (mail clients don't scale those), so it is drawn at its 1x size, tall enough for a
long headline; below it the cell's plain green carries on.
meio-campo.png: the halfway line with the centre circle, between séries (2x, shown 600x28).

    python scripts/make_email_art.py src/geral/static/geral
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PITCH, PITCH_2 = (0x1F, 0x7A, 0x3D), (0x24, 0x8A, 0x46)
WASH = (0xD3, 0xE2, 0xC6)
CHALK = (255, 255, 255, 180)  # the portal's rgba(255, 255, 255, .7)
SS = 4  # supersampling, for smooth chalk


def top(width: int = 600, height: int = 900, stripe: int = 75) -> Image.Image:
    im = Image.new("RGB", (width * SS, height * SS), PITCH)
    d = ImageDraw.Draw(im)
    for i, x in enumerate(range(0, width, stripe)):
        if i % 2:
            d.rectangle([x * SS, 0, (x + stripe) * SS, height * SS], fill=PITCH_2)
    chalk = Image.new("RGBA", im.size, (0, 0, 0, 0))
    cx, cy, r = width - 40, 20, 125
    ImageDraw.Draw(chalk).ellipse(
        [(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], outline=CHALK, width=4 * SS
    )
    im.paste(chalk, (0, 0), chalk)
    return im.resize((width, height), Image.LANCZOS)


def halfway(width: int = 1200, height: int = 56) -> Image.Image:
    im = Image.new("RGB", (width * SS, height * SS), WASH)
    d = ImageDraw.Draw(im)
    mid, line, r = height // 2, 6, 22
    d.rectangle([0, (mid - line // 2) * SS, width * SS, (mid + line // 2) * SS], fill="white")
    c = width // 2
    d.ellipse([(c - r) * SS, (mid - r) * SS, (c + r) * SS, (mid + r) * SS], fill=WASH,
              outline="white", width=line * SS)  # fmt: skip
    return im.resize((width, height), Image.LANCZOS)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    top().save(out / "campo-topo.png", optimize=True)
    halfway().save(out / "meio-campo.png", optimize=True)
    print(f"campo-topo.png and meio-campo.png in {out}")
