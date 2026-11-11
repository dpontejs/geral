import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from geral.stats.espn import StatsUnavailable
from geral.stats.ge_tables import GE_TABLES_API, GETablesClient
from geral.teams import Team

FIXTURES = Path(__file__).parent / "fixtures" / "ge_tables"
TZ = ZoneInfo("America/Sao_Paulo")

POTIGUAR_PAGE = "https://ge.globo.com/rn/futebol/campeonato-potiguar/"
SERIE_D_PAGE = "https://ge.globo.com/futebol/brasileirao-serie-d/"
POTIGUAR = f"{GE_TABLES_API}/51e46731-98b0-499f-b7e7-7d53554e30e4/fase"
SERIE_D = f"{GE_TABLES_API}/5b2a5692-2d5c-47e8-8b24-be84447b62fd/fase"

ABC = Team(
    slug="abc",
    name="ABC",
    newsletter="Elefante News",
    fans="abecedistas",
    espn_id=9965,
    ge_url="https://ge.globo.com/rn/futebol/times/abc/",
    news_query='"ABC" futebol Natal',
    keywords=("abc",),
    accent="#141414",
    leagues=("bra.copa_do_nordeste",),
    ge_id=350,
    ge_tables={"Potiguar": POTIGUAR_PAGE},
)
ABC_WITH_SERIE_D = ABC.model_copy(update={"ge_tables": {"Série D": SERIE_D_PAGE}})


def body(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def json_response(name: str) -> httpx.Response:
    return httpx.Response(200, text=body(name), headers={"content-type": "application/json"})


@pytest.fixture
def ge() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(POTIGUAR_PAGE).mock(
            return_value=httpx.Response(200, text=body("page_potiguar.html"))
        )
        for phase, file in (
            ("primeira-fase-potiguar-2026", "primeira-fase"),
            ("quartas-de-final-potiguar-2026", "quartas-de-final"),
            ("semifinal-potiguar-2026", "semifinal"),
            ("final-potiguar-2026", "final"),
        ):
            router.get(f"{POTIGUAR}/{phase}/classificacao/").mock(
                return_value=json_response(f"potiguar_{file}.json")
            )
        for n in range(1, 8):
            router.get(f"{POTIGUAR}/primeira-fase-potiguar-2026/rodada/{n}/jogos/").mock(
                return_value=json_response(f"potiguar_primeira-fase_r{n}.json")
            )
        router.get(f"{POTIGUAR}/primeira-fase-potiguar-2026/rodada/8/jogos/").mock(
            return_value=httpx.Response(200, json=[])
        )
        router.get(SERIE_D_PAGE).mock(
            return_value=httpx.Response(200, text=body("page_seried.html"))
        )
        router.get(f"{SERIE_D}/primeira-fase-brasileiro-seried-2026/classificacao/").mock(
            return_value=json_response("seried_primeira-fase.json")
        )
        for n in range(1, 12):
            router.get(f"{SERIE_D}/primeira-fase-brasileiro-seried-2026/rodada/{n}/jogos/").mock(
                return_value=json_response(f"seried_primeira-fase_r{n}.json")
            )
        yield router


def make_client(team: Team = ABC, now: datetime | None = None) -> GETablesClient:
    clock = (lambda: now) if now else (lambda: datetime(2026, 11, 11, 12, 0, tzinfo=TZ))
    return GETablesClient(team, client=httpx.Client(), clock=clock)


def test_ge_fixtures_from_points_and_knockout(ge) -> None:
    fixtures = make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert [f.match_id for f in fixtures] == [
        "347371", "347375", "347377", "347381", "347386", "347389", "347395",
        "350512", "350513", "350925", "350926",
    ]  # fmt: skip
    final = fixtures[-1]
    assert final.league == "ge:Potiguar"
    assert (final.home, final.away) == ("ABC", "América-RN")
    assert final.kickoff == datetime(2026, 3, 21, 16, 0, tzinfo=TZ)
    assert final.time_valid and final.state == "post"


def test_ge_fixtures_from_group_phase_stop_at_the_first_empty_round(ge) -> None:
    fixtures = make_client(ABC_WITH_SERIE_D).get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert len(fixtures) == 10
    assert {f.league for f in fixtures} == {"ge:Série D"}
    rounds = [str(c.request.url) for c in ge.calls if "/rodada/" in str(c.request.url)]
    assert rounds[-1].endswith("/rodada/11/jogos/")  # the first empty round ends the phase


def test_ge_reads_tuuid_from_page_each_run(ge) -> None:
    make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))
    make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    pages = [c for c in ge.calls if str(c.request.url) == POTIGUAR_PAGE]
    assert len(pages) == 2
    assert any("51e46731-98b0-499f-b7e7-7d53554e30e4" in str(c.request.url) for c in ge.calls)


def test_ge_fixtures_drop_matches_older_than_a_week(ge) -> None:
    fixtures = make_client().get_fixtures(datetime(2026, 3, 20, tzinfo=TZ))

    assert [f.match_id for f in fixtures] == ["350513", "350925", "350926"]


def test_ge_unplayed_match_is_pre(ge) -> None:
    client = make_client(now=datetime(2026, 3, 21, 10, 0, tzinfo=TZ))

    final = client.get_fixtures(datetime(2026, 3, 21, 10, 0, tzinfo=TZ))[-1]

    assert final.match_id == "350926"
    assert final.state == "pre"


def test_ge_last_match_has_score_and_competition(ge) -> None:
    client = make_client()

    match = client.get_last_match(
        datetime(2026, 3, 15, tzinfo=TZ), datetime(2026, 3, 22, 8, 0, tzinfo=TZ)
    )

    assert match is not None
    assert match.fixture_id == 350926
    assert (match.home, match.home_goals, match.away_goals, match.away) == (
        "ABC", 1, 1, "América-RN",
    )  # fmt: skip
    assert match.competition == "Potiguar"
    assert match.is_home
    assert match.venue == "Arena das Dunas"
    assert match.home_logo == ABC.logo and match.away_logo is None


def test_ge_last_match_none_outside_the_window(ge) -> None:
    client = make_client()

    assert (
        client.get_last_match(datetime(2026, 5, 1, tzinfo=TZ), datetime(2026, 5, 8, tzinfo=TZ))
        is None
    )


def test_ge_next_match(ge) -> None:
    client = make_client(now=datetime(2026, 3, 19, 8, 0, tzinfo=TZ))

    upcoming = client.get_next_match(datetime(2026, 3, 19, 8, 0, tzinfo=TZ))

    assert upcoming is not None
    assert upcoming.opponent == "América-RN"
    assert upcoming.competition == "Potiguar"
    assert upcoming.date == datetime(2026, 3, 21, 16, 0, tzinfo=TZ)
    assert upcoming.is_home
    assert upcoming.match_id == "350926"


def test_ge_standings_our_group_only(ge) -> None:
    rows = make_client(ABC_WITH_SERIE_D).get_standings()

    assert len(rows) == 6
    ours = next(r for r in rows if r.is_ours)
    assert (ours.position, ours.team, ours.points, ours.played) == (1, "ABC", 23, 10)
    assert (ours.won, ours.drawn, ours.lost, ours.goals_diff) == (7, 2, 1, 9)
    assert (ours.goals_for, ours.goals_against) == (15, 6)


def test_ge_table_name_is_the_competition(ge) -> None:
    client = make_client(ABC_WITH_SERIE_D)
    client.get_standings()

    assert client.table_name == "Série D"


def test_ge_knockout_has_no_standings(ge) -> None:
    assert make_client().get_standings() == []


def test_ge_moment_form_newest_first(ge) -> None:
    client = make_client()

    moment = client.get_moment(datetime(2026, 3, 22, tzinfo=TZ), [])

    assert moment is not None
    assert [f.score for f in moment.form] == ["1-1", "1-1", "3-1", "3-1", "1-1"]
    assert [f.result for f in moment.form] == ["E", "E", "V", "V", "E"]
    assert moment.form[0].opponent == "América-RN"
    assert moment.form[0].competition == "Potiguar"


def test_ge_preview_forms_and_head_to_head(ge) -> None:
    client = make_client(now=datetime(2026, 3, 19, 8, 0, tzinfo=TZ))

    preview = client.get_preview("350926", "ge:Potiguar")

    assert preview is not None
    assert preview.opponent == "América-RN"
    assert [f.score for f in preview.team_form][:2] == ["1-1", "3-1"]
    assert preview.opponent_form[0].opponent == "ABC"
    assert [f.score for f in preview.head_to_head] == ["1-1", "0-0"]  # newest first, our side


def test_ge_page_down_raises_unavailable_on_fixtures(ge) -> None:
    ge.get(POTIGUAR_PAGE).mock(return_value=httpx.Response(503))

    with pytest.raises(StatsUnavailable):
        make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))


def test_ge_api_down_other_methods_degrade(ge) -> None:
    ge.get(f"{POTIGUAR}/final-potiguar-2026/classificacao/").mock(return_value=httpx.Response(500))
    client = make_client()
    end = datetime(2026, 3, 22, tzinfo=TZ)

    assert client.get_last_match(datetime(2026, 3, 15, tzinfo=TZ), end) is None
    assert client.get_next_match(end) is None
    assert client.get_standings() == []
    assert client.get_moment(end, []) is None
    assert client.get_preview("350926", "ge:Potiguar") is None


def test_ge_undefined_knockout_game_is_skipped(ge) -> None:
    final = json.loads(body("potiguar_final.json"))
    tbd = final["secao"][0]["chave"][0]["jogos"][0]
    tbd["equipes"] = {"mandante": None, "visitante": None}
    ge.get(f"{POTIGUAR}/final-potiguar-2026/classificacao/").mock(
        return_value=httpx.Response(200, json=final)
    )

    fixtures = make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert len(fixtures) == 10


def mock_final(ge, change) -> None:
    """Serve the Potiguar final with `change` applied to ABC x América-RN (the second leg)."""
    final = json.loads(body("potiguar_final.json"))
    for section in final["secao"]:
        for tie in section["chave"]:
            for game in tie["jogos"]:
                if game["id"] == 350926:
                    change(game)
    ge.get(f"{POTIGUAR}/final-potiguar-2026/classificacao/").mock(
        return_value=httpx.Response(200, json=final)
    )


def test_ge_match_without_time_is_next_all_day_but_opens_no_bolao(ge) -> None:
    mock_final(
        ge,
        lambda g: g.update(
            hora_realizacao=None,
            placar_oficial_mandante=None,
            placar_oficial_visitante=None,
            jogo_ja_comecou=False,
        ),
    )
    morning = datetime(2026, 3, 21, 8, 0, tzinfo=TZ)
    client = make_client(now=morning)

    upcoming = client.get_next_match(morning)
    final = client.get_fixtures(morning)[-1]

    assert upcoming is not None and upcoming.opponent == "América-RN"
    assert upcoming.match_id is None  # no kickoff time, no deadline for the bets
    assert (final.time_valid, final.state) == (False, "pre")


def test_ge_unplayed_match_hours_later_is_postponed(ge) -> None:
    mock_final(
        ge,
        lambda g: g.update(
            placar_oficial_mandante=None, placar_oficial_visitante=None, jogo_ja_comecou=False
        ),
    )
    later = datetime(2026, 3, 21, 20, 0, tzinfo=TZ)

    final = make_client(now=later).get_fixtures(later)[-1]

    assert final.state == "postponed"


def test_ge_started_match_is_in(ge) -> None:
    mock_final(ge, lambda g: g.update(placar_oficial_mandante=0, placar_oficial_visitante=0))
    during = datetime(2026, 3, 21, 16, 30, tzinfo=TZ)

    assert make_client(now=during).get_fixtures(during)[-1].state == "in"


def test_ge_phases_after_the_current_one_enter_the_calendar(ge) -> None:
    page = (
        body("page_potiguar.html")
        .replace('"atual":true', '"atual":false')
        .replace('"nome":"Semifinal","slug"', '"nome":"Semifinal","atual":true,"slug"')
    )
    ge.get(POTIGUAR_PAGE).mock(return_value=httpx.Response(200, text=page))

    fixtures = make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert fixtures[-1].match_id == "350926"


def test_ge_failing_future_phase_is_left_out(ge) -> None:
    page = (
        body("page_potiguar.html")
        .replace('"atual":true', '"atual":false')
        .replace('"nome":"Semifinal","slug"', '"nome":"Semifinal","atual":true,"slug"')
    )
    ge.get(POTIGUAR_PAGE).mock(return_value=httpx.Response(200, text=page))
    ge.get(f"{POTIGUAR}/final-potiguar-2026/classificacao/").mock(return_value=httpx.Response(404))

    fixtures = make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert fixtures[-1].match_id == "350513"


def test_ge_points_rounds_go_past_ultima_until_an_empty_one(ge) -> None:
    first = json.loads(body("potiguar_primeira-fase.json"))
    first["rodada"] = {"atual": 5, "ultima": 5}
    ge.get(f"{POTIGUAR}/primeira-fase-potiguar-2026/classificacao/").mock(
        return_value=httpx.Response(200, json=first)
    )

    fixtures = make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert len(fixtures) == 11


def test_ge_game_without_names_is_skipped(ge) -> None:
    mock_final(ge, lambda g: g["equipes"]["visitante"].update(nome_popular=None))

    fixtures = make_client().get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))

    assert "350926" not in [f.match_id for f in fixtures]


def test_ge_unexpected_error_in_fixtures_is_unavailable(ge, monkeypatch) -> None:
    client = make_client()

    def boom(game, now):
        raise RuntimeError("bad data")

    monkeypatch.setattr(client, "_fixture", boom)

    with pytest.raises(StatsUnavailable):
        client.get_fixtures(datetime(2026, 1, 1, tzinfo=TZ))
