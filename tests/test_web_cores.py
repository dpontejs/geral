"""Each team's pages wear the club's colours in the grass's place; the portal stays green."""

import re
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from webkit import make_client, publish

from geral.teams import load_teams
from geral.web.palette import club_palette, contrast

DAY = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
PORTAL_TURF = "#0E3320"


@pytest.fixture
def site(store, mailer, clock):
    clock.now = DAY
    return make_client(store, mailer, clock)


def theme(page: str) -> str:
    return re.search(r'<meta name="theme-color" content="([^"]+)">', page).group(1)


def test_team_page_wears_the_club_colours(site) -> None:
    publish(site, "nautico")
    nautico = club_palette(load_teams()["nautico"])

    page = site.get("/t/nautico").text

    assert "--pitch: #C60000;" in page
    assert f"--turf: {nautico.turf};" in page
    assert theme(page) == nautico.turf


def test_team_game_wears_the_club_colours_and_the_geral_game_does_not(site) -> None:
    vasco = site.get("/jogos/craque-do-dia/vasco").text
    geral = site.get("/jogos/craque-do-dia").text

    assert "--pitch: #141414;" in vasco
    assert theme(geral) == PORTAL_TURF and "club-colours" not in geral


@pytest.mark.parametrize("path", ["/", "/jogos", "/pedir"])
def test_portal_pages_stay_green(site, path) -> None:
    page = site.get(path).text

    assert theme(page) == PORTAL_TURF
    assert "club-colours" not in page


def test_flamengo_frames_its_red_in_black() -> None:
    flamengo = club_palette(load_teams()["flamengo"])

    assert flamengo.pitch == "#A51C24" and flamengo.turf == "#141414"


@pytest.mark.parametrize("slug", sorted(load_teams()))
def test_every_club_palette_keeps_the_page_readable(slug) -> None:
    p = club_palette(load_teams()[slug])

    assert contrast(p.turf, "#EFE4CC") >= 7  # header, footer: paper text on the frame
    assert contrast(p.pitch, "#FFFFFF") >= 4.5  # titles and chalk on the stripes
    assert contrast(p.pitch_2, "#FFFFFF") >= 4.5
    assert contrast(p.wash, "#14231A") >= 10  # body text on the plain field


def test_no_team_means_no_palette() -> None:
    assert club_palette(None) is None


def test_dark_colour_must_be_hex() -> None:
    team = load_teams()["flamengo"]

    with pytest.raises(ValidationError):
        type(team).model_validate(team.model_dump() | {"dark": "black"})


def test_general_edition_page_stays_green(site) -> None:
    publish(site, "geral")

    page = site.get("/t/geral").text

    assert theme(page) == PORTAL_TURF and "club-colours" not in page
