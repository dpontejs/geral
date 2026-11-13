import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "src" / "geral"
JOGOS_CSS = ROOT / "static" / "geral" / "jogos.css"
CONFIRM_EMAIL = ROOT / "web" / "templates" / "email" / "confirm.html.j2"
OLD_GREYS = ("#5E5B55", "#8E8B84")  # the concrete frames and stripes of the old look


@pytest.mark.parametrize("path", ["/", "/pedir", "/confirm?token=nao-existe"])
def test_pages_stand_on_the_pitch(client, path) -> None:
    page = client.get(path, follow_redirects=True).text

    assert '<meta name="theme-color" content="#0E3320">' in page
    assert re.search(r"\.wall \{[^}]*var\(--pitch\)", page)
    assert re.search(r"header \{[^}]*var\(--turf\)", page)
    for grey in OLD_GREYS:
        assert grey not in page


def test_portal_break_is_on_the_pitch_too(client) -> None:
    page = client.get("/").text

    assert re.search(r'<section class="[^"]*intervalo[^"]*wall', page)


def test_game_boards_use_the_turf_frame() -> None:
    css = JOGOS_CSS.read_text()

    assert re.search(r"\.match \{[^}]*var\(--turf\)", css)
    for grey in OLD_GREYS:
        assert grey not in css


def test_confirm_email_uses_the_pitch_stripe_and_turf_button() -> None:
    html = CONFIRM_EMAIL.read_text()

    assert "#1F7A3D" in html
    assert "#0E3320" in html
    for grey in OLD_GREYS:
        assert grey not in html


def test_general_edition_wears_the_pitch() -> None:
    from fakes import FakeLLMClient
    from test_general_edition import END, START, WEEKS, responder

    from geral.general import GENERAL_EDITION
    from geral.general.edition import build_general
    from geral.general.render import COLORS, render_general

    html, _ = render_general(build_general(START, END, WEEKS, FakeLLMClient(responder)))

    assert GENERAL_EDITION.accent == "#1F7A3D"
    assert "#8E8B84" not in COLORS.values()
    # CSS is inlined: each series header and the stripe under the logo carry the colour.
    assert re.search(r'bgcolor="#0E3320">S\u00e9rie A<', html)
    assert "background-color: #1F7A3D;" in html


def test_small_text_on_the_striped_grass_gets_a_shadow_to_stay_readable(client) -> None:
    page = client.get("/").text
    css = JOGOS_CSS.read_text()

    assert re.search(r"\.intervalo\.wall \.head p \{[^}]*text-shadow", page)
    for rule in (".how", ".credit", ".tries .n"):
        assert re.search(re.escape(rule) + r" \{[^}]*text-shadow", css), rule


def test_the_middle_is_a_marked_field(client) -> None:
    page = client.get("/").text

    # Striped grass only at the top and the break; the rest is plain, lighter grass.
    assert re.search(r"body \{[^}]*background: var\(--wash\)", page)
    assert re.search(r"\.why \{[^}]*background: var\(--turf\)", page)
    # The ticket sits in the penalty area, and the halfway line splits it from the teams.
    signup = page.split('class="signup"')[1].split('id="torcidas"')[0]
    assert 'class="area"' in signup and 'class="arc"' in signup
    assert 'class="halfway"' in signup
