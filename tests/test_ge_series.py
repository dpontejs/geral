from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from ge_series import mock_series

from geral.general import SERIES
from geral.stats.ge_tables import load_competition

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def ge() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        mock_series(router)
        yield router


def load(name: str):
    return load_competition(httpx.Client(), name, SERIES[name], TZ)


def test_ge_standing_keeps_band_name(ge) -> None:
    table = load("Série A").groups[0]
    assert table[0].band == "Libertadores"
    assert table[19].band == "Rebaixados"
    assert table[11].band == "Sul-Americana"
    assert table[12].band is None
    assert table[0].crest.startswith("https://")


def test_competition_keeps_every_phase(ge) -> None:
    serie_c = load("Série C")
    assert [p.kind for p in serie_c.phases] == ["points", "groups", "knockout"]
    assert serie_c.current == 2
    assert serie_c.phases[1].bands == ["Finalistas e Série B", "Série B"]
    assert serie_c.phases[0].groups[0][0].band == "Classificados"
    assert serie_c.phases[2].groups is None


def test_game_knows_phase_round_and_tie(ge) -> None:
    serie_a = load("Série A")
    round_36 = [g for g in serie_a.games if g.round == 36]
    assert len(round_36) == 10
    assert round_36[0].phase == serie_a.phases[0].name
    assert round_36[0].home_crest.startswith("https://")
    playoffs = [g for g in load("Série B").games if g.tie == "Playoff de acesso 1"]
    assert len(playoffs) == 2
    assert {g.phase for g in playoffs} == {"Playoffs de acesso"}
