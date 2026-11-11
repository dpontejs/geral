from datetime import date
from pathlib import Path

import pytest

from geral.games.quanto_foi import convert, load_matches

FIXTURES = Path(__file__).parent / "fixtures" / "brasileirao"


@pytest.fixture
def matches(tmp_path) -> list:
    data = tmp_path / "brasileirao.csv"
    full = (FIXTURES / "full.csv").read_text(encoding="utf-8")
    goals = (FIXTURES / "gols.csv").read_text(encoding="utf-8")
    data.write_text(convert(full, goals), encoding="utf-8")
    return load_matches(data)


def by_id(matches, match_id):
    return next(m for m in matches if m.id == match_id)


def test_convert_keeps_scores_and_attaches_scorers(matches) -> None:
    flu = by_id(matches, 4607)

    assert len(matches) == 9
    assert (flu.home, flu.away, flu.home_goals, flu.away_goals) == (
        "Fluminense",
        "Figueirense",
        3,
        0,
    )
    assert flu.day == date(2014, 4, 19) and flu.round == 1 and flu.stadium == "Maracanã"
    assert flu.home_scorers == ("Rafael Sóbis", "Fred", "Nirley da Silva Fonseca (contra)")
    assert flu.away_scorers == ()
    assert flu.home_coach == "C. Borges dos Santos"


def test_convert_orders_stoppage_time_goals_last(matches) -> None:
    assert by_id(matches, 4733).home_scorers == ("Paolo Guerrero", "Petros")


def test_convert_writes_club_names_with_accents(matches) -> None:
    nautico = by_id(matches, 1965)

    assert (nautico.home, nautico.away) == ("Náutico", "São Paulo")
    assert nautico.home_coach == "" and nautico.home_scorers == ()
