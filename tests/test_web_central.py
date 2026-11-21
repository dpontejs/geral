from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from ge_series import mock_series
from webkit import make_client

from geral.central.build import build_snapshot
from geral.central.models import TeamNextMatch
from geral.central.store import save_snapshot

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=TZ)


@pytest.fixture(scope="module")
def snapshot():
    with respx.mock(assert_all_called=False) as router:
        mock_series(router)
        nxt = [
            TeamNextMatch(
                team_slug="vasco",
                team_name="Vasco",
                opponent="Palmeiras",
                kickoff=datetime(2026, 11, 22, 16, tzinfo=TZ),
                competition="Série A",
            )
        ]
        return build_snapshot(NOW, None, client=httpx.Client(), next_matches=lambda now: nxt)


@pytest.fixture
def central(store, mailer, clock, tmp_path, snapshot):
    path = tmp_path / "central.json"
    save_snapshot(path, snapshot)
    return make_client(store, mailer, clock, CENTRAL_SNAPSHOT=str(path))


def test_central_page_renders_each_status(central) -> None:
    serie_a = central.get("/central?serie=a").text
    assert "Libertadores" in serie_a and "Flamengo" in serie_a
    assert 'data-round="36"' in serie_a
    assert "Palmeiras" in serie_a  # Vasco's next match
    serie_b = central.get("/central?serie=b").text
    assert "Playoff de acesso 1" in serie_b and "Novorizontino" in serie_b
    serie_c = central.get("/central?serie=c").text
    assert "Campeão" in serie_c and "Maringá" in serie_c and "Subiram" in serie_c


def test_central_default_serie_is_first_running(central) -> None:
    page = central.get("/central").text
    assert 'aria-current="page" href="/central?serie=a"' in page


def test_central_unknown_serie_falls_back(central) -> None:
    response = central.get("/central?serie=z")
    assert response.status_code == 200
    assert 'aria-current="page" href="/central?serie=a"' in response.text


def test_central_page_without_snapshot(store, mailer, clock, tmp_path) -> None:
    client = make_client(store, mailer, clock, CENTRAL_SNAPSHOT=str(tmp_path / "none.json"))
    response = client.get("/central")
    assert response.status_code == 200
    assert "em atualização" in response.text


def test_home_links_to_central(central) -> None:
    home = central.get("/").text
    assert 'href="/central"' in home
    assert "Flamengo" in home  # the Série A leader in the Central block
    assert "Maringá" in home  # the Série C champion
