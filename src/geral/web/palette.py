"""A team's own pages (its edition and its games) wear the club's colours in the grass's place.

Only the field changes: the striped top and the frame (header, footer, board borders) take the
club's colours and the plain middle a concrete tinted with them. Paper, ticket and the yellow lamps
of the board stay, so the page is still the Geral. The portal keeps its green pitch.
"""

from dataclasses import dataclass

from markupsafe import Markup

from geral.teams import Team

CONCRETE = "#E4E0D8"  # the plain field of a team's page, before the club's tint
WHITE, BLACK = "#FFFFFF", "#000000"


def _rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def mix(a: str, b: str, amount: float) -> str:
    """`a` with `amount` (0 to 1) of `b`."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * amount):02X}" for x, y in zip(ra, rb, strict=True))


def _luminance(color: str) -> float:
    def channel(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = map(channel, _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio, 1 to 21."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@dataclass(frozen=True)
class ClubPalette:
    turf: str  # header, footer, board frames: the club's dark colour
    pitch: str  # the striped top: the club's colour
    pitch_2: str  # its other stripe
    wash: str  # the plain field in the middle

    def style(self) -> Markup:
        r, g, b = _rgb(self.turf)
        return Markup(
            '<style id="club-colours">:root { '
            f"--turf: {self.turf}; --pitch: {self.pitch}; --pitch-2: {self.pitch_2}; "
            f"--wash: {self.wash}; "
            f"--on-grass: 0 1px 2px {self.turf}, 0 0 6px rgba({r}, {g}, {b}, .6); }}</style>"
        )


def club_palette(team: Team | None) -> ClubPalette | None:
    if team is None:
        return None
    accent = team.accent
    # Mown stripes: a lighter one, or a darker one when white titles would fade on it (red).
    stripe = mix(accent, WHITE, 0.09)
    if contrast(stripe, WHITE) < 4.5:
        stripe = mix(accent, BLACK, 0.14)
    return ClubPalette(
        turf=team.dark or mix(accent, BLACK, 0.55),
        pitch=accent,
        pitch_2=stripe,
        wash=mix(CONCRETE, accent, 0.04),
    )
