import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from resenha.__main__ import app
from resenha.models import NextMatch
from resenha.summarizer.pipeline import render_prompt
from resenha.teams import Team, UnknownTeam, get_team, load_teams

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_load_teams_validates_catalog():
    teams = load_teams()

    assert {"vasco", "palmeiras", "abc", "nautico"} <= teams.keys()
    for slug, team in teams.items():
        assert team.slug == slug
        assert HEX.match(team.accent)
        assert team.espn_id > 0
        assert team.leagues


def test_catalog_brands():
    teams = load_teams()

    assert teams["vasco"].newsletter == "Almirante News"
    assert teams["palmeiras"].newsletter == "Porco News"
    assert teams["abc"].newsletter == "Elefante News"
    assert teams["nautico"].newsletter == "Timbu News"


def test_get_team_unknown_lists_valid_slugs():
    with pytest.raises(UnknownTeam) as exc:
        get_team("xyz")

    assert "vasco" in str(exc.value)


def test_load_teams_rejects_duplicate_espn_id(tmp_path):
    catalog = tmp_path / "teams.toml"
    entry = """
[{slug}]
name = "Time"
newsletter = "Time News"
fans = "torcedores"
espn_id = 1
ge_url = "https://ge.globo.com/futebol/times/time/"
news_query = "Time futebol"
keywords = ["time"]
accent = "#000000"
leagues = ["bra.1"]
"""
    catalog.write_text(entry.format(slug="a") + entry.format(slug="b"), encoding="utf-8")

    with pytest.raises(ValueError, match="espn_id"):
        load_teams(catalog)


def test_team_mentions_matches_keywords():
    team = get_team("nautico")

    assert team.mentions("Timbu vence em casa")
    assert team.mentions("NÁUTICO anuncia reforço")
    assert not team.mentions("Sport vence o clássico")


def test_team_short_word_keyword_needs_word_boundary():
    team = get_team("abc")

    assert team.mentions("ABC empata em Natal")
    assert not team.mentions("Programa abcdário do futebol")


def test_team_logo_comes_from_espn():
    assert get_team("vasco").logo == "https://a.espncdn.com/i/teamlogos/soccer/500/3454.png"


def test_team_is_frozen():
    team = get_team("vasco")
    with pytest.raises(ValidationError):
        team.name = "Outro"  # type: ignore[misc]
    assert isinstance(team, Team)


def test_source_has_no_hardcoded_club() -> None:
    # Every club-specific word comes from teams.toml; the code and prompts are generic.
    source = Path(__file__).parents[1] / "src" / "resenha"
    leftovers = [
        f"{path.relative_to(source)}:{n}"
        for path in source.rglob("*")
        if path.suffix in {".py", ".md", ".j2"}
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"flamengo|urubu|rubro-negr|mengão", line, re.IGNORECASE)
    ]
    assert leftovers == []


def test_prompts_name_the_team() -> None:
    nautico = get_team("nautico")
    match = NextMatch(
        opponent="Sport",
        competition="Série B",
        date=datetime(2026, 11, 14, 16, tzinfo=UTC),
        is_home=True,
    )

    prompt = render_prompt(
        "intro", team=nautico, topics=[], last_match=None, label="Pré-jogo", next_match=match
    )

    assert '"Timbu News", sobre o Náutico' in prompt
    assert "Náutico x Sport" in prompt


def test_unknown_team_exits_2_listing_valid_slugs(tmp_path) -> None:
    result = CliRunner().invoke(app, ["preview", "--team", "xyz", "--edition", "news"])

    assert result.exit_code == 2
    assert "nautico" in result.output
