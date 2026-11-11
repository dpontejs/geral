from datetime import date, timedelta
from pathlib import Path

import pytest

from geral.games.quanto_foi import LAUNCH, by_number, convert, load_matches, pool, puzzle

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


def test_geral_pool_keeps_only_memorable_matches(matches) -> None:
    ids = {m.id for m in pool(matches, "geral")}

    # classics among the big 12, 4+ goals or a 3+ goal margin
    assert ids == {1, 4607, 5075, 4733, 57, 596}


def test_team_pool_only_has_the_team_matches(matches) -> None:
    assert {m.id for m in pool(matches, "vasco")} == {1, 5075}
    assert {m.id for m in pool(matches, "nautico")} == {1953, 1965}


def test_puzzle_is_the_same_for_everyone_on_a_day(matches) -> None:
    day = date(2026, 11, 20)

    assert puzzle(pool(matches, "geral"), day) == puzzle(
        pool(list(reversed(matches)), "geral"), day
    )
    assert puzzle(pool(matches, "geral"), day).number == (day - LAUNCH).days + 1


def test_puzzle_does_not_repeat_until_the_pool_ends(matches) -> None:
    games = pool(matches, "geral")
    days = [LAUNCH + timedelta(days=i) for i in range(len(games))]

    assert len({puzzle(games, day).match.id for day in days}) == len(games)
    assert puzzle(games, LAUNCH) == by_number(games, 1)
