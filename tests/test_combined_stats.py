from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fakes import FLAMENGO

from geral.models import FormResult, MatchPreview, MatchStats, NextMatch, StandingRow, TeamMoment
from geral.schedule import Fixture
from geral.stats.combined import CombinedStatsClient, stats_client_for
from geral.stats.espn import ESPNStatsClient, StatsUnavailable
from geral.teams import get_team

TZ = ZoneInfo("America/Sao_Paulo")


def at(day: int, hour: int = 16) -> datetime:
    return datetime(2027, 4, day, hour, 0, tzinfo=TZ)


def fixture(match_id: str, league: str, day: int) -> Fixture:
    return Fixture(
        match_id=match_id, league=league, kickoff=at(day), time_valid=True, state="pre",
        home="ABC", away="X",
    )  # fmt: skip


def stats(fixture_id: int, competition: str, day: int) -> MatchStats:
    return MatchStats(
        fixture_id=fixture_id, competition=competition, date=at(day), home="ABC", away="X",
        home_goals=1, away_goals=0,
    )  # fmt: skip


def form(day: int, competition: str) -> FormResult:
    return FormResult(result="V", opponent="X", score="1-0", competition=competition, date=at(day))


class Fake:
    def __init__(self, **answers) -> None:
        self.answers = answers
        self.calls: list[tuple] = []
        self.table_name = answers.get("table_name")

    def __getattr__(self, name):
        def method(*args):
            self.calls.append((name, *args))
            answer = self.answers.get(name)
            if isinstance(answer, Exception):
                raise answer
            return answer

        return method


def test_stats_client_for_team_without_ge_tables_is_espn() -> None:
    assert isinstance(stats_client_for(FLAMENGO), ESPNStatsClient)


def test_stats_client_for_team_with_ge_tables_is_combined() -> None:
    assert isinstance(stats_client_for(get_team("abc")), CombinedStatsClient)


def test_combined_fixtures_merge_espn_and_ge() -> None:
    espn = Fake(get_fixtures=[fixture("401", "bra.copa_do_nordeste", 10)])
    ge = Fake(get_fixtures=[fixture("355", "ge:Série C", 5), fixture("356", "ge:Série C", 12)])

    fixtures = CombinedStatsClient(espn, ge).get_fixtures(at(1))

    assert [f.match_id for f in fixtures] == ["355", "401", "356"]


@pytest.mark.parametrize("down", ["espn", "ge"])
def test_combined_unavailable_when_one_source_fails(down) -> None:
    sources = {
        "espn": Fake(get_fixtures=[fixture("401", "bra.copa_do_nordeste", 10)]),
        "ge": Fake(get_fixtures=[fixture("355", "ge:Série C", 5)]),
    }
    sources[down] = Fake(get_fixtures=StatsUnavailable("down"))

    with pytest.raises(StatsUnavailable):
        CombinedStatsClient(sources["espn"], sources["ge"]).get_fixtures(at(1))


def test_combined_last_match_is_the_most_recent_of_both() -> None:
    espn = Fake(get_last_match=stats(401, "Copa do Nordeste", 8))
    ge = Fake(get_last_match=stats(355, "Série C", 9))

    match = CombinedStatsClient(espn, ge).get_last_match(at(1), at(10))

    assert match.fixture_id == 355


def test_combined_last_match_when_one_has_none() -> None:
    espn = Fake(get_last_match=stats(401, "Copa do Nordeste", 8))
    ge = Fake(get_last_match=None)

    assert CombinedStatsClient(espn, ge).get_last_match(at(1), at(10)).fixture_id == 401


def test_combined_next_match_is_the_earliest() -> None:
    espn = Fake(get_next_match=NextMatch(opponent="Y", competition="Copa do Nordeste", date=at(12)))
    ge = Fake(get_next_match=NextMatch(opponent="Z", competition="Série C", date=at(11)))

    assert CombinedStatsClient(espn, ge).get_next_match(at(10)).opponent == "Z"


def test_combined_standings_from_ge_when_espn_has_no_table() -> None:
    row = StandingRow(
        position=1, team="ABC", points=3, played=1, won=1, drawn=0, lost=0, goals_diff=1,
        is_ours=True,
    )  # fmt: skip
    espn = Fake(get_standings=[])
    ge = Fake(get_standings=[row], table_name="Série C")
    client = CombinedStatsClient(espn, ge)

    assert client.get_standings() == [row]
    assert client.table_name == "Série C"
    assert espn.calls == []  # ABC has no ESPN `league`


def test_combined_moment_merges_forms_newest_first() -> None:
    espn = Fake(
        get_moment=TeamMoment(form=[form(8, "Copa do Nordeste"), form(2, "Copa do Nordeste")])
    )
    ge = Fake(
        get_moment=TeamMoment(form=[form(9, "Série C"), form(6, "Série C"), form(4, "Série C"),
                                    form(3, "Série C")], league="Série C"),
    )  # fmt: skip

    moment = CombinedStatsClient(espn, ge).get_moment(at(10), [])

    assert [f.date.day for f in moment.form] == [9, 8, 6, 4, 3]
    assert moment.league == "Série C"


def test_combined_moment_none_when_both_none() -> None:
    assert (
        CombinedStatsClient(Fake(get_moment=None), Fake(get_moment=None)).get_moment(at(10), [])
        is None
    )


def test_combined_preview_routes_by_league() -> None:
    espn = Fake(get_preview=MatchPreview(opponent="Y"))
    ge = Fake(get_preview=MatchPreview(opponent="Z"))
    client = CombinedStatsClient(espn, ge)

    assert client.get_preview("355", "ge:Série C").opponent == "Z"
    assert client.get_preview("401", "bra.copa_do_nordeste").opponent == "Y"


def test_combined_ge_failure_keeps_espn_calendar_when_espn_has_the_main_league() -> None:
    espn = Fake(get_fixtures=[fixture("401", "bra.2", 10)])
    ge = Fake(get_fixtures=StatsUnavailable("ge down"))

    fixtures = CombinedStatsClient(espn, ge, get_team("nautico")).get_fixtures(at(1))

    assert [f.match_id for f in fixtures] == ["401"]


def test_combined_ge_failure_is_unavailable_when_ge_has_the_main_league() -> None:
    espn = Fake(get_fixtures=[fixture("401", "bra.copa_do_nordeste", 10)])
    ge = Fake(get_fixtures=StatsUnavailable("ge down"))

    with pytest.raises(StatsUnavailable):
        CombinedStatsClient(espn, ge, get_team("abc")).get_fixtures(at(1))


def test_nautico_follows_the_pernambucano_on_ge() -> None:
    nautico = get_team("nautico")

    assert nautico.ge_id == 343
    assert nautico.ge_tables == {
        "Pernambucano": "https://ge.globo.com/pe/futebol/campeonato-pernambucano/"
    }
    assert isinstance(stats_client_for(nautico), CombinedStatsClient)
