"""Findings of the branch review, each pinned by a test (docs/features/central.md)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from ge_series import mock_series

from geral.central.build import build_snapshot, serie_view
from geral.central.models import CentralSnapshot
from geral.central.refresh import FinishedRoundsTransport
from geral.central.store import load_snapshot, save_snapshot
from geral.general import SERIES
from geral.models import StandingRow
from geral.stats.ge_models import Competition, Game, Phase
from geral.stats.ge_tables import load_competition

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=TZ)


def game(id_, round_, day, scored=True, phase="Fase única", tie=None, home="A", away="B"):
    kickoff = datetime(2026, 1, 1, 16, tzinfo=TZ) + timedelta(days=day)
    goals = (1, 0) if scored else (None, None)
    return Game(
        id_,
        "Série A",
        kickoff,
        True,
        home,
        away,
        1,
        2,
        *goals,
        None,
        phase=phase,
        round=round_,
        tie=tie,
    )


def row(pos: int) -> StandingRow:
    return StandingRow(
        position=pos, team=f"T{pos}", points=10, played=1, won=0, drawn=0, lost=0, goals_diff=0
    )


def test_truncated_snapshot_is_none(tmp_path) -> None:
    path = tmp_path / "central.json"
    save_snapshot(path, CentralSnapshot(updated_at=NOW, series=[], next_matches=[]))
    path.write_bytes(path.read_bytes()[:-5] + "é".encode()[:1])  # cut inside a character
    assert load_snapshot(path) is None


def test_two_writers_never_share_a_temp_file(tmp_path, monkeypatch) -> None:
    names = []
    real = type(tmp_path).replace

    def spy(self, target):
        names.append(self.name)
        return real(self, target)

    monkeypatch.setattr(type(tmp_path), "replace", spy)
    snap = CentralSnapshot(updated_at=NOW, series=[])
    save_snapshot(tmp_path / "central.json", snap)
    save_snapshot(tmp_path / "central.json", snap)
    assert len(set(names)) == 2


def test_serie_without_phases_keeps_previous_version() -> None:
    with respx.mock(assert_all_called=False) as router:
        mock_series(router)
        first = build_snapshot(NOW, None, client=httpx.Client(), next_matches=lambda now: [])
    import geral.central.build as build

    def no_phases(client, name, page, tz):  # the tabela-context format has no phases
        return Competition(name, [])

    with respx.mock(assert_all_called=False) as router, pytest.MonkeyPatch.context() as mp:
        mock_series(router)
        mp.setattr(build, "load_competition", no_phases)
        second = build_snapshot(NOW, first, client=httpx.Client(), next_matches=lambda now: [])
    assert second.series == first.series


def test_final_with_an_undated_second_leg_has_no_champion() -> None:
    first_leg = game(1, None, 300, phase="Final", tie="Final", home="X", away="Y")
    comp = Competition(
        "Série C",
        [first_leg],
        current=0,
        phases=[Phase("Final", "knockout", [], None, {"Final": 2})],
    )
    view = serie_view(comp, "c", NOW)
    assert view.status == "knockout"
    assert view.ties[0].winner is None and view.summary is None


def test_current_round_ignores_a_postponed_straggler() -> None:
    games = [game(i, 12, 80 + i, scored=i != 1) for i in range(1, 11)]  # one round-12 game moved
    games += [game(100 + i, 36, 320, scored=False) for i in range(10)]
    comp = Competition(
        "Série A", games, current=0, phases=[Phase("Fase única", "points", [], [[row(1), row(2)]])]
    )
    assert serie_view(comp, "a", NOW).current_round == 36


def test_current_round_stays_while_a_round_is_half_played() -> None:
    games = [game(i, 36, 323, scored=i <= 6) for i in range(1, 11)]
    games += [game(100 + i, 37, 327, scored=False) for i in range(10)]
    comp = Competition(
        "Série A", games, current=0, phases=[Phase("Fase única", "points", [], [[row(1), row(2)]])]
    )
    assert serie_view(comp, "a", NOW).current_round == 36


def test_band_without_name_does_not_break_the_loader() -> None:
    with respx.mock(assert_all_called=False) as router:
        mock_series(router, only=("Série A",))
        route = next(r for r in router.routes if "classificacao" in str(r.pattern))
        data = route.return_value.json()
        data["faixas_classificacao"].append({"cor": "#123456", "id": 1})
        route.return_value = httpx.Response(200, json=data)
        comp = load_competition(httpx.Client(), "Série A", SERIES["Série A"], TZ)
    assert comp.groups[0][0].band == "Libertadores"


def test_finished_rounds_are_fetched_once() -> None:
    old = [
        {
            "data_realizacao": "2026-08-01",
            "placar_oficial_mandante": 1,
            "placar_oficial_visitante": 0,
        }
    ]
    new = [
        {
            "data_realizacao": "2026-11-22",
            "placar_oficial_mandante": None,
            "placar_oficial_visitante": None,
        }
    ]
    with respx.mock() as router:
        done = router.get("https://api.test/tabela/x/fase/f/rodada/1/jogos/").mock(
            return_value=httpx.Response(200, json=old)
        )
        open_ = router.get("https://api.test/tabela/x/fase/f/rodada/2/jogos/").mock(
            return_value=httpx.Response(200, json=new)
        )
        client = httpx.Client(
            transport=FinishedRoundsTransport(httpx.HTTPTransport(), clock=lambda: NOW)
        )
        for _ in range(3):
            assert client.get("https://api.test/tabela/x/fase/f/rodada/1/jogos/").json() == old
            client.get("https://api.test/tabela/x/fase/f/rodada/2/jogos/")
    assert done.call_count == 1 and open_.call_count == 3


def test_next_matches_are_fetched_hourly() -> None:
    calls = []

    def nxt(now):
        calls.append(now)
        return []

    with respx.mock(assert_all_called=False) as router:
        mock_series(router, only=("Série A",))
        series = {"Série A": SERIES["Série A"]}
        first = build_snapshot(NOW, None, client=httpx.Client(), next_matches=nxt, series=series)
        later = NOW + timedelta(minutes=50)
        second = build_snapshot(
            later, first, client=httpx.Client(), next_matches=nxt, series=series
        )
        build_snapshot(
            NOW + timedelta(minutes=61),
            second,
            client=httpx.Client(),
            next_matches=nxt,
            series=series,
        )
    assert calls == [NOW, NOW + timedelta(minutes=61)]
    assert second.next_matches_at == NOW
