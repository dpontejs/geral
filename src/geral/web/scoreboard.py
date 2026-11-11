"""The goal animation of the portal's scoreboard, drawn lamp by lamp like the old Maracanã board.

The board is a grid of COLS x ROWS lamps. Each sprite pose is a layer of lit lamps shown during a
window of ticks; CSS keyframes switch the layers on and off, so the page needs no JavaScript.
With reduced motion the board holds still on the last frame: the goal.
"""

from dataclasses import dataclass
from functools import cache

COLS, ROWS = 64, 20
TICKS = 50  # one play every TICKS * TICK_MS
TICK_MS = 100
PITCH = 7  # px between lamps in the viewBox

KEEPER_STAND = """
...XXX...
..X...X..
..X.X.X..
...XXX...
....X....
..XXXXXXX
..X.X....
..X.X....
...XXX...
...X.X...
...X.X...
...X.X...
..XX.XX..
"""

KEEPER_DIVE = """
X........
.X.XXX...
..X...X..
..XX.XX..
...XXX...
....XX...
....XXX..
....X.X..
....XXX..
.....X.X.
.....X..X
....X...X
....X....
"""

KEEPER_FALLEN = """
..XXX....
.X...X...
.X.X.X...
..XXX....
..XXXX...
.X.XX.X..
.X.XXXXXX
XX.....XX
"""

KICKER_STAND = """
...XXX...
..X...X..
..X.X.X..
...XXX...
....X....
XXXXXXX..
....X.X..
....X.X..
...XXX...
...X.X...
...X.X...
...X.X...
..XX.XX..
"""

KICKER_KICK = """
...XXX...
..X...X..
..X.X.X..
...XXX...
....X....
.XXXXXXX.
X...X...X
....X....
...XXX...
..X..X...
.X...X...
X....X...
.....XX..
"""

KICKER_CELEBRATE = """
.......XX
...XXX.X.
..X...XX.
..X.X.X..
...XXXX..
....X....
...XXX...
..X.X....
....X....
...XXX...
...X.X...
...X.X...
..XX.XX..
"""

GOL = """
.XXX...XXX..X....
X...X.X...X.X....
X.....X...X.X....
X.XXX.X...X.X....
X...X.X...X.X....
X...X.X...X.X....
.XXX...XXX..XXXXX
"""

BALL = "XX\nXX"


@dataclass(frozen=True)
class Layer:
    name: str
    dots: tuple[tuple[int, int], ...]
    start: int
    end: int


def sprite(art: str, x: int, y: int | None = None) -> tuple[tuple[int, int], ...]:
    """Lit lamps of `art` placed with its top-left at (x, y); by default it stands on the floor."""
    rows = art.strip().splitlines()
    top = ROWS - len(rows) if y is None else y
    return tuple(
        (x + dx, top + dy) for dy, row in enumerate(rows) for dx, ch in enumerate(row) if ch == "X"
    )


def goal() -> tuple[tuple[int, int], ...]:
    """The goal seen from the side, as on the old board: diagonal back post, crossbar, post."""
    top, left, right = 4, 7, 14
    bar = [(x, top) for x in range(left, right + 1)]
    post = [(right, y) for y in range(top, ROWS)]
    back = [(left - round((y - top) * 5 / (ROWS - 1 - top)), y) for y in range(top, ROWS)]
    return tuple(dict.fromkeys(bar + post + back))


def ball_path() -> list[tuple[int, int]]:
    """From the kicker's foot, over the keeper, into the top corner, then down the net."""
    (x0, y0), (x1, y1) = (44, 17), (9, 6)
    flight = []
    for step in range(10):
        t = step / 9
        flight.append((round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t - 14 * t * (1 - t))))
    drop = [(9, 9), (8, 12), (8, 15), (7, 18)]
    return flight + drop


@cache
def layers() -> tuple[Layer, ...]:
    kick, keeper_down = 10, 24
    path = ball_path()
    flight_start = kick + 2
    # The goal lights up when the ball comes to rest in the net.
    goal_tick = flight_start + len(path) - 1
    balls = [Layer("ball-foot", sprite(BALL, 44, 17), 0, flight_start)]
    for i, (x, y) in enumerate(path[:-1]):
        balls.append(Layer(f"ball-{i}", sprite(BALL, x, y), flight_start + i, flight_start + i + 1))
    balls.append(Layer("ball-net", sprite(BALL, *path[-1]), goal_tick, TICKS))
    return (
        Layer("goal", goal(), 0, TICKS),
        Layer("keeper-stand", sprite(KEEPER_STAND, 17), 0, kick + 6),
        Layer("keeper-dive", sprite(KEEPER_DIVE, 15, 1), kick + 6, keeper_down),
        Layer("keeper-fallen", sprite(KEEPER_FALLEN, 17), keeper_down, TICKS),
        Layer("kicker-stand", sprite(KICKER_STAND, 46), 0, kick),
        Layer("kicker-kick", sprite(KICKER_KICK, 46), kick, kick + 4),
        Layer("kicker-wait", sprite(KICKER_STAND, 46), kick + 4, goal_tick),
        Layer("kicker-celebrate", sprite(KICKER_CELEBRATE, 46), goal_tick, TICKS),
        Layer("gol", sprite(GOL, 24, 2), goal_tick, TICKS),
        *balls,
    )


def _keyframes(name: str, layer: Layer) -> str:
    def pct(tick: int) -> str:
        return f"{tick * 100 / TICKS:g}%"

    frames = [f"0%{{opacity:{1 if layer.start == 0 else 0}}}"]
    if layer.start > 0:
        frames.append(f"{pct(layer.start)}{{opacity:1}}")
    if layer.end < TICKS:
        frames.append(f"{pct(layer.end)}{{opacity:0}}")
    return f"@keyframes {name}{{{''.join(frames)}}}"


def _circles(dots: tuple[tuple[int, int], ...], r: float) -> str:
    half = PITCH / 2
    return "".join(
        f'<circle cx="{x * PITCH + half:g}" cy="{y * PITCH + half:g}" r="{r}"/>' for x, y in dots
    )


@cache
def animation_svg() -> str:
    width, height = COLS * PITCH, ROWS * PITCH
    css, groups = [], []
    for i, layer in enumerate(layers()):
        if layer.start == 0 and layer.end == TICKS:
            groups.append(f'<g class="lit">{_circles(layer.dots, 2.7)}</g>')
            continue
        name = f"lance-{i}"
        css.append(_keyframes(name, layer))
        kind = "layer end" if layer.end == TICKS else "layer"
        groups.append(
            f'<g class="{kind}" style="animation-name:{name}">{_circles(layer.dots, 2.7)}</g>'
        )
    duration = TICKS * TICK_MS
    css.append(
        f".lance .layer{{opacity:0;animation:{duration}ms step-end infinite}}"
        "@media (prefers-reduced-motion: reduce){.lance .layer{animation:none}"
        ".lance .layer.end{opacity:1}}"
    )
    return (
        f'<svg class="lance" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="lance-title">'
        '<title id="lance-title">Placar eletrônico: o atacante chuta, o goleiro voa e é gol</title>'
        f"<style>{''.join(css)}</style>"
        '<defs><pattern id="lance-off" width="7" height="7" patternUnits="userSpaceOnUse">'
        '<circle cx="3.5" cy="3.5" r="2.1" fill="#1D1C18"/></pattern></defs>'
        f'<rect width="{width}" height="{height}" fill="url(#lance-off)"/>'
        f'<g fill="#FFC21A">{"".join(groups)}</g>'
        "</svg>"
    )
