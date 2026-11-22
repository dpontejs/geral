"""`geral especial`: a banner (a title won) on top of a team's next edition."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fakes import FLAMENGO
from typer.testing import CliRunner
from webkit import AUTH, NOW

import geral.__main__ as cli
from geral.config import get_settings
from geral.models import Edition, MatchStats, Newsletter, StandingRow
from geral.render.renderer import render
from geral.send.recipients import make_banner
from geral.web.banners import BannerStore

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def banners(store) -> BannerStore:
    return BannerStore(store.path)


def test_banner_is_for_one_team_until_it_publishes(client, store, banners) -> None:
    banners.create("flamengo", "Campeão brasileiro 2026", "É campeão!", NOW)

    mine = client.get("/api/teams/flamengo/banner", headers=AUTH).json()
    other = client.get("/api/teams/vasco/banner", headers=AUTH).json()
    store.set_latest_edition("flamengo", "Pós", "<p>", "t", NOW + timedelta(hours=1))
    after = client.get("/api/teams/flamengo/banner", headers=AUTH).json()

    assert mine == {"kicker": "Campeão brasileiro 2026", "title": "É campeão!"}
    assert other == {"kicker": None, "title": None}
    assert after == {"kicker": None, "title": None}
    assert client.get("/api/teams/flamengo/banner").status_code == 401


def test_especial_command_creates_and_cancels(tmp_path, monkeypatch) -> None:
    db = tmp_path / "subs.db"
    monkeypatch.setenv("SUBSCRIBERS_DB", str(db))
    get_settings.cache_clear()

    made = CliRunner().invoke(
        cli.app, ["especial", "--team", "flamengo", "Campeão brasileiro 2026"]
    )
    pending = BannerStore(db).pending("flamengo", None)
    gone = CliRunner().invoke(cli.app, ["especial", "--team", "flamengo", "--cancelar"])

    assert made.exit_code == 0 and "próxima edição" in made.output
    assert pending == ("Campeão brasileiro 2026", "É campeão!")
    assert gone.exit_code == 0 and BannerStore(db).pending("flamengo", None) is None
    assert CliRunner().invoke(cli.app, ["especial", "--team", "nada", "x"]).exit_code != 0


def newsletter() -> Newsletter:
    return Newsletter(
        team=FLAMENGO,
        edition=Edition(
            kind="post",
            start=datetime(2026, 11, 21, tzinfo=TZ),
            end=datetime(2026, 11, 22, 13, tzinfo=TZ),
            label="Pós-jogo — 22/11/2026",
        ),
        intro="Festa.",
        last_match=MatchStats(
            fixture_id=1,
            competition="Brasileirão",
            date=datetime(2026, 11, 21, 16, 30, tzinfo=TZ),
            home="Palmeiras",
            away="Flamengo",
            home_goals=1,
            away_goals=1,
            venue="Allianz Parque",
            is_home=False,
        ),
        standings=[
            StandingRow(
                position=1,
                team="Flamengo",
                points=80,
                played=36,
                won=24,
                drawn=8,
                lost=4,
                goals_diff=43,
                is_ours=True,
            )
        ],
    )


def test_banner_takes_the_numbers_from_the_table_and_the_score() -> None:
    banner = make_banner(newsletter(), "Campeão brasileiro 2026", "É campeão!")
    assert banner.stats == [("80", "pontos"), ("24", "vitórias"), ("+43", "saldo")]
    assert banner.subtitle == "Palmeiras 1 × 1 Flamengo · Allianz Parque"


def test_banner_renders_in_html_and_text() -> None:
    n = newsletter()
    n.banner = make_banner(n, "Campeão brasileiro 2026", "É campeão!")
    html, text = render(n)
    assert "Campeão brasileiro 2026" in html and "É campeão!" in html and "+43" in html
    assert "CAMPEÃO BRASILEIRO 2026" in text and "É campeão!" in text
