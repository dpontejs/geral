"""State leagues whose ge page uses the `tabela-context` format (e.g. the Pernambucano)."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from geral.stats.espn import StatsUnavailable
from geral.stats.ge_context import GEQL_URL
from geral.stats.ge_tables import GETablesClient
from geral.teams import Team

FIXTURES = Path(__file__).parent / "fixtures" / "ge_context"
TZ = ZoneInfo("America/Sao_Paulo")
PAGE = "https://ge.globo.com/pe/futebol/campeonato-pernambucano/"
FIRST_PHASE = "primeira-fase-pernambucano-2026-2027"

PETROLINA = Team(
    slug="petrolina",
    name="Petrolina",
    newsletter="Fera News",
    fans="petrolinenses",
    espn_id=99999,
    ge_url="https://ge.globo.com/pe/petrolina-regiao/futebol/times/petrolina/",
    news_query="Petrolina futebol",
    keywords=("petrolina",),
    accent="#141414",
    leagues=("bra.copa_do_nordeste",),
    ge_id=2890,
    ge_tables={"Pernambucano": PAGE},
)


def page(first_phase_current: bool = False) -> str:
    html = (FIXTURES / "page_pernambucano.html").read_text(encoding="utf-8")
    if first_phase_current:
        html = html.replace('"actual": true', '"actual": false').replace(
            f'"slug": "{FIRST_PHASE}", "actual": false', f'"slug": "{FIRST_PHASE}", "actual": true'
        )
    return html


def graphql(request: httpx.Request) -> httpx.Response:
    filter_ = json.loads(request.content)["variables"]["multisportMatchesByPhaseFilter"]
    path = FIXTURES / f"primeira-fase_r{filter_['round']}.json"
    if filter_["phaseSlug"] == FIRST_PHASE and path.exists():
        return httpx.Response(200, text=path.read_text(encoding="utf-8"))
    return httpx.Response(200, json={"data": {"multisportMatchesByPhase": []}})


@pytest.fixture
def ge() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(PAGE).mock(return_value=httpx.Response(200, text=page()))
        router.post(GEQL_URL).mock(side_effect=graphql)
        yield router


def make_client(now: datetime = datetime(2026, 11, 11, 12, 0, tzinfo=TZ)) -> GETablesClient:
    return GETablesClient(PETROLINA, client=httpx.Client(), clock=lambda: now)


def test_context_fixtures_from_rounds_and_brackets(ge) -> None:
    fixtures = make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))

    assert len(fixtures) == 6  # five group games and the round of 16
    assert {f.league for f in fixtures} == {"ge:Pernambucano"}
    knockout = fixtures[-1]
    assert (knockout.home, knockout.away) == ("Petrolina", "Chã Grande")
    assert knockout.kickoff == datetime(2026, 11, 11, 16, 0, tzinfo=TZ)
    assert (knockout.time_valid, knockout.state) == (True, "pre")


def test_context_rounds_query_the_phase_with_the_page_slugs(ge) -> None:
    make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))

    bodies = [json.loads(c.request.content) for c in ge.calls if c.request.method == "POST"]
    first = bodies[0]["variables"]["multisportMatchesByPhaseFilter"]
    assert first == {
        "phaseSlug": FIRST_PHASE,
        "championshipSlug": "campeonato-pernambucano",
        "championshipEditionSlug": "pernambucano-2026-2027",
        "sportSlug": "futebol",
        "modalitySlug": "futebol_de_campo",
        "categorySlug": "profissional",
        "round": 1,
    }
    filters = [b["variables"]["multisportMatchesByPhaseFilter"] for b in bodies]
    rounds = [f["round"] for f in filters if f["phaseSlug"] == FIRST_PHASE]
    assert rounds == [1, 2, 3, 4, 5, 6]  # the empty sixth round ends the phase


def test_context_last_match(ge) -> None:
    match = make_client().get_last_match(
        datetime(2026, 11, 7, tzinfo=TZ), datetime(2026, 11, 10, tzinfo=TZ)
    )

    assert match is not None
    assert (match.home, match.home_goals, match.away_goals, match.away) == (
        "FácilNet", 0, 0, "Petrolina",
    )  # fmt: skip
    assert match.competition == "Pernambucano"
    assert not match.is_home
    assert match.venue == "Clementino Lima"


def test_context_standings_our_group(ge) -> None:
    ge.get(PAGE).mock(return_value=httpx.Response(200, text=page(first_phase_current=True)))
    client = make_client()

    rows = client.get_standings()

    assert len(rows) == 6
    ours = next(r for r in rows if r.is_ours)
    assert (ours.position, ours.team, ours.points, ours.played, ours.won) == (
        1, "Petrolina", 13, 5, 4,
    )  # fmt: skip
    assert (ours.goals_for, ours.goals_against, ours.goals_diff) == (12, 2, 10)
    assert client.table_name == "Pernambucano"


def test_context_knockout_phase_has_no_standings(ge) -> None:
    assert make_client().get_standings() == []


def test_page_without_known_format_is_unavailable(ge) -> None:
    ge.get(PAGE).mock(return_value=httpx.Response(200, text="<html></html>"))

    with pytest.raises(StatsUnavailable):
        make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))


def test_context_graphql_error_on_a_past_phase_is_unavailable(ge) -> None:
    ge.post(GEQL_URL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "boom"}], "data": None})
    )

    with pytest.raises(StatsUnavailable):
        make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))


def test_context_ungrouped_round_matches_are_read(ge) -> None:
    grouped = json.loads((FIXTURES / "primeira-fase_r5.json").read_text(encoding="utf-8"))
    ungrouped = [
        {"__typename": "MatchEventKind", "match": event["match"]}
        for item in grouped["data"]["multisportMatchesByPhase"]
        for event in item["events"]
    ]

    def flat(request: httpx.Request) -> httpx.Response:
        filter_ = json.loads(request.content)["variables"]["multisportMatchesByPhaseFilter"]
        if filter_["phaseSlug"] == FIRST_PHASE and filter_["round"] == 1:
            return httpx.Response(200, json={"data": {"multisportMatchesByPhase": ungrouped}})
        return httpx.Response(200, json={"data": {"multisportMatchesByPhase": []}})

    ge.post(GEQL_URL).mock(side_effect=flat)

    fixtures = make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))

    assert ("FácilNet", "Petrolina") in [(f.home, f.away) for f in fixtures]


def test_context_query_reads_ungrouped_matches_inside_match() -> None:
    from geral.stats.ge_context import MATCHES_BY_PHASE

    ungrouped = MATCHES_BY_PHASE.split("... on MatchEventKind", 1)[1]
    assert ungrouped.lstrip(" {\n").startswith("match")


def match(**changes) -> dict:
    base = {
        "id": 1, "startDate": "2027-01-20", "startHour": "16:00:00", "moment": "FUTURE",
        "canceled": False,
        "firstContestant": {"id": 343, "popularName": "Náutico"},
        "secondContestant": {"id": 2890, "popularName": "Petrolina"},
        "scoreboard": {"home": None, "away": None, "penalty": None},
        "location": {"popularName": "Aflitos"},
    }  # fmt: skip
    return {**base, **changes}


@pytest.mark.parametrize(
    "changes",
    [
        {"id": 0},
        {"secondContestant": {"id": 0, "popularName": ""}},
        {"secondContestant": {"id": 2890, "popularName": ""}},
    ],
)
def test_context_tie_without_defined_teams_is_not_a_game(changes) -> None:
    from geral.stats.ge_context import _game

    with pytest.raises(ValueError):
        _game(match(**changes), "Pernambucano", TZ)


def test_context_canceled_match_is_postponed() -> None:
    from geral.stats.ge_context import _game

    game = _game(match(canceled=True, moment="PAST"), "Pernambucano", TZ)
    fixture = make_client(datetime(2027, 1, 20, 17, 0, tzinfo=TZ))._fixture(
        game, datetime(2027, 1, 20, 17, 0, tzinfo=TZ)
    )

    assert fixture.state == "postponed"


def test_context_past_match_without_score_is_not_started() -> None:
    from geral.stats.ge_context import _game

    assert not _game(match(moment="PAST"), "Pernambucano", TZ).started
    assert _game(match(moment="PRESENT"), "Pernambucano", TZ).started
    scored = match(moment="PAST", scoreboard={"home": 1, "away": 0, "penalty": None})
    assert _game(scored, "Pernambucano", TZ).started


def test_context_query_asks_for_canceled() -> None:
    from geral.stats.ge_context import MATCHES_BY_PHASE

    assert "canceled" in MATCHES_BY_PHASE


def test_context_empty_round_before_the_phase_total_does_not_end_it(ge) -> None:
    def gap(request: httpx.Request) -> httpx.Response:
        filter_ = json.loads(request.content)["variables"]["multisportMatchesByPhaseFilter"]
        if filter_["phaseSlug"] == FIRST_PHASE and filter_["round"] == 1:
            return httpx.Response(200, json={"data": {"multisportMatchesByPhase": []}})
        return graphql(request)

    ge.post(GEQL_URL).mock(side_effect=gap)

    fixtures = make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))

    assert len(fixtures) == 5  # rounds 2-5 (round 1 empty) and the round of 16


def test_context_without_current_phase_uses_the_last_one_with_data(ge) -> None:
    html = page().replace('"actual": true', '"actual": false')
    ge.get(PAGE).mock(return_value=httpx.Response(200, text=html))

    def later_phases_fail(request: httpx.Request) -> httpx.Response:
        filter_ = json.loads(request.content)["variables"]["multisportMatchesByPhaseFilter"]
        if filter_["phaseSlug"] != FIRST_PHASE:
            return httpx.Response(200, json={"errors": [{"message": "no phase"}], "data": None})
        return graphql(request)

    ge.post(GEQL_URL).mock(side_effect=later_phases_fail)

    fixtures = make_client().get_fixtures(datetime(2026, 10, 1, tzinfo=TZ))

    assert len(fixtures) == 6


def test_context_competition_tells_the_current_phase(ge) -> None:
    from geral.stats.ge_tables import load_competition

    competition = load_competition(httpx.Client(), "Pernambucano", PAGE, TZ)

    assert competition.phase == "Oitavas de final (Primeiro turno)"
    assert competition.phase_kind == "knockout"
