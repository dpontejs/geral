from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from ge_series import mock_series

from geral.central.build import build_snapshot, decide, serie_view
from geral.central.models import CentralSnapshot, MatchView, TieView
from geral.central.store import load_snapshot, save_snapshot
from geral.general import SERIES
from geral.stats.ge_models import Competition, Game, Phase
from geral.stats.ge_tables import load_competition

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=TZ)


@pytest.fixture
def ge() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        mock_series(router)
        yield router


def view(name: str, slug: str, now: datetime = NOW):
    return serie_view(load_competition(httpx.Client(), name, SERIES[name], TZ), slug, now)


def leg(home, away, hg, ag, day, pens=(None, None)) -> MatchView:
    return MatchView(
        home=home,
        away=away,
        home_goals=hg,
        away_goals=ag,
        kickoff=datetime(2026, 9, day, 16, tzinfo=TZ),
        time_valid=True,
        status="post" if hg is not None else "pre",
        home_penalties=pens[0],
        away_penalties=pens[1],
    )


def test_points_serie_groups_games_by_round(ge) -> None:
    serie_a = view("Série A", "a")
    assert serie_a.status == "points"
    assert serie_a.current_round == 36
    assert len(serie_a.rounds[36]) == 10
    assert serie_a.table[0].team == "Flamengo"
    assert serie_a.bands == ["Libertadores", "Pré-Libertadores", "Sul-Americana", "Rebaixados"]
    assert serie_a.summary is None


def test_knockout_serie_has_ties_with_aggregate(ge) -> None:
    serie_b = view("Série B", "b")
    assert serie_b.status == "knockout"
    assert [t.name for t in serie_b.ties] == ["Playoff de acesso 1", "Playoff de Acesso 2"]
    first = serie_b.ties[0]
    assert (first.home, first.away) == ("Atlético-GO", "Vila Nova")
    assert len(first.legs) == 2 and first.home_agg is None and first.winner is None
    assert serie_b.table[0].team == "Novorizontino"  # the final table stays under the playoffs


def test_single_leg_and_two_leg_aggregate() -> None:
    two = TieView.of(
        "Final", [leg("ASA", "Uberlândia", 0, 2, 6), leg("Uberlândia", "ASA", 1, 1, 13)]
    )
    assert (two.home, two.away, two.home_agg, two.away_agg) == ("ASA", "Uberlândia", 1, 3)
    assert decide(two) == "Uberlândia"
    one = TieView.of("Final", [leg("Maringá", "Ferroviária", 2, 1, 6)])
    assert (one.home_agg, one.away_agg) == (2, 1) and decide(one) == "Maringá"


def test_tie_decided_on_penalties() -> None:
    tie = TieView.of(
        "Quartas 2", [leg("Goiatuba", "ASA", 0, 0, 8), leg("ASA", "Goiatuba", 1, 1, 16, (5, 4))]
    )
    assert decide(tie) == "ASA"


def test_level_tie_without_penalties_goes_to_second_leg_host() -> None:
    tie = TieView.of(
        "Playoff 2",
        [leg("São José-RS", "Goiatuba", 0, 0, 1), leg("Goiatuba", "São José-RS", 1, 1, 8)],
    )
    assert decide(tie) == "Goiatuba"


def test_unfinished_tie_has_no_winner() -> None:
    tie = TieView.of("Playoff", [leg("A", "B", 2, 0, 1), leg("B", "A", None, None, 8)])
    assert (tie.home_agg, tie.away_agg) == (2, 0) and decide(tie) is None


def test_finished_serie_summary(ge) -> None:
    serie_c = view("Série C", "c")
    assert serie_c.status == "over"
    summary = serie_c.summary
    assert (summary.champion, summary.runner_up) == ("Maringá", "Ferroviária")
    assert sorted(summary.promoted) == ["Ferroviária", "Inter de Limeira", "Maringá", "Santa Cruz"]
    assert len(summary.relegated) == 2


def test_serie_d_promotes_quarter_and_playoff_winners(ge) -> None:
    summary = view("Série D", "d").summary
    assert (summary.champion, summary.runner_up) == ("Uberlândia", "ASA")
    assert sorted(summary.promoted) == [
        "ABC",
        "ASA",
        "Gama",
        "Goiatuba",
        "Nacional-AM",
        "Uberlândia",
    ]
    assert summary.relegated == []


def test_finished_league_summary_uses_table() -> None:
    rows = [
        {
            "position": i,
            "team": f"T{i}",
            "points": 40 - i,
            "played": 2,
            "won": 0,
            "drawn": 0,
            "lost": 0,
            "goals_diff": 0,
            "band": "Rebaixados" if i > 3 else None,
        }
        for i in range(1, 5)
    ]
    from geral.models import StandingRow

    game = Game(
        1,
        "Série A",
        datetime(2026, 12, 6, 16, tzinfo=TZ),
        True,
        "T1",
        "T2",
        1,
        2,
        1,
        0,
        None,
        phase="Fase única",
        round=1,
    )
    comp = Competition(
        "Série A",
        [game],
        phases=[Phase("Fase única", "points", ["Rebaixados"], [[StandingRow(**r) for r in rows]])],
        current=0,
        phase_kind="points",
    )
    summary = serie_view(comp, "a", datetime(2026, 12, 8, tzinfo=TZ)).summary
    assert (summary.champion, summary.runner_up, summary.relegated) == ("T1", "T2", ["T4"])


def test_unscheduled_game_is_pre_without_time() -> None:
    game = Game(
        1,
        "Série A",
        datetime(2026, 12, 6, tzinfo=TZ),
        False,
        "A",
        "B",
        1,
        2,
        None,
        None,
        None,
        round=38,
    )
    match = MatchView.of(game, NOW)
    assert match.status == "pre" and match.time_valid is False


def test_serie_failure_keeps_previous_version(ge) -> None:
    first = build_snapshot(NOW, None, client=httpx.Client(), next_matches=lambda now: [])
    ge.get(SERIES["Série B"]).mock(return_value=httpx.Response(500))
    second = build_snapshot(NOW, first, client=httpx.Client(), next_matches=lambda now: [])
    assert [s.name for s in second.series] == list(SERIES)
    assert second.series[1] == first.series[1]


def test_snapshot_roundtrip_json(ge, tmp_path) -> None:
    snap = build_snapshot(NOW, None, client=httpx.Client(), next_matches=lambda now: [])
    path = tmp_path / "central.json"
    save_snapshot(path, snap)
    assert load_snapshot(path) == snap
    assert load_snapshot(tmp_path / "missing.json") is None
    assert isinstance(snap, CentralSnapshot)


def test_next_matches_skip_a_failing_team(monkeypatch) -> None:
    from geral.central import build
    from geral.models import NextMatch

    class Client:
        def __init__(self, team) -> None:
            self.team = team

        def get_next_match(self, now):
            if self.team.slug == "vasco":
                raise RuntimeError("espn down")
            return NextMatch(opponent="Rival", competition="Série A", date=NOW)

    monkeypatch.setattr(build, "stats_client_for", lambda team, tz: Client(team))
    matches = build.team_next_matches(NOW)
    slugs = {m.team_slug for m in matches}
    assert "vasco" not in slugs and "flamengo" in slugs


def test_next_matches_show_a_derby_between_our_teams_once(monkeypatch) -> None:
    from geral.central import build
    from geral.models import NextMatch

    names = {"palmeiras": "Palmeiras", "flamengo": "Flamengo"}

    class Client:
        def __init__(self, team) -> None:
            self.team = team

        def get_next_match(self, now):
            if self.team.slug not in names:
                return None
            other = names["flamengo" if self.team.slug == "palmeiras" else "palmeiras"]
            return NextMatch(
                opponent=other,
                competition="Série A",
                date=NOW,
                is_home=self.team.slug == "palmeiras",
            )

    monkeypatch.setattr(build, "stats_client_for", lambda team, tz: Client(team))
    matches = build.team_next_matches(NOW)
    assert len(matches) == 1
    assert (matches[0].team_name, matches[0].opponent, matches[0].is_home) == (
        "Palmeiras",
        "Flamengo",
        True,
    )
