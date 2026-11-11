import xml.etree.ElementTree as ET

from geral.web.scoreboard import COLS, ROWS, TICKS, animation_svg, layers


def test_every_layer_fits_the_board_and_has_a_valid_window() -> None:
    for layer in layers():
        assert layer.dots, layer.name
        assert all(0 <= x < COLS and 0 <= y < ROWS for x, y in layer.dots), layer.name
        assert 0 <= layer.start < layer.end <= TICKS, layer.name


def test_keeper_kicker_and_ball_are_on_the_board_at_every_tick() -> None:
    for actor in ("keeper", "kicker", "ball"):
        poses = [layer for layer in layers() if layer.name.startswith(actor)]
        for tick in range(TICKS):
            visible = [p.name for p in poses if p.start <= tick < p.end]
            assert len(visible) == 1, (actor, tick, visible)


def test_the_play_ends_in_a_goal_with_the_kicker_celebrating() -> None:
    final = {layer.name for layer in layers() if layer.end == TICKS}

    assert {"keeper-fallen", "kicker-celebrate", "gol"} <= final


def test_svg_is_well_formed_and_described_for_screen_readers() -> None:
    svg = ET.fromstring(animation_svg())

    title = svg.find("{http://www.w3.org/2000/svg}title")
    assert svg.get("role") == "img"
    assert title is not None and "gol" in title.text.lower()


def test_svg_holds_still_on_the_goal_when_motion_is_reduced() -> None:
    svg = animation_svg()

    assert "prefers-reduced-motion: reduce" in svg
    assert 'class="layer end"' in svg
