from datetime import datetime, timedelta
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
            ),
            TeamNextMatch(
                team_slug="palmeiras",
                team_name="Palmeiras",
                opponent="Flamengo",
                other_slug="flamengo",
                kickoff=datetime(2026, 11, 21, 16, 30, tzinfo=TZ),
                competition="Série A",
            ),
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
    assert 'src="/static/flamengo/icon-512.png"' in serie_a  # a derby shows both of ours
    serie_b = central.get("/central?serie=b").text
    assert "Playoff de acesso 1" in serie_b and "Novorizontino" in serie_b
    serie_c = central.get("/central?serie=c").text
    assert "Campeão" in serie_c and "Maringá" in serie_c and "Subiram" in serie_c


def test_central_default_serie_is_first_running(central) -> None:
    page = central.get("/central").text
    assert 'aria-current="page" data-swap href="/central?serie=a"' in page


def test_central_unknown_serie_falls_back(central) -> None:
    response = central.get("/central?serie=z")
    assert response.status_code == 200
    assert 'aria-current="page" data-swap href="/central?serie=a"' in response.text


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


def news_snapshot(snapshot):
    from geral.central.models import NewsItem

    items = [
        NewsItem(
            id="aaaaaaaaaaaa",
            serie_slug="a",
            serie_name="Série A",
            title="Flamengo vence e abre vantagem",
            summary="Rubro-negro chega a 79 pontos",
            image_url="https://s2-ge.glbimg.com/fla.jpg",
            url="https://ge.globo.com/futebol/noticia/2026/11/21/fla.ghtml",
            published_at=datetime(2026, 11, 21, 11, tzinfo=TZ),
            lead="O Flamengo venceu o Palmeiras neste sábado.",
        ),
        NewsItem(
            id="bbbbbbbbbbbb",
            serie_slug="b",
            serie_name="Série B",
            title="Vila Nova encara o Atlético-GO no playoff",
            url="https://ge.globo.com/futebol/noticia/2026/11/21/vila.ghtml",
            published_at=datetime(2026, 11, 21, 10, tzinfo=TZ),
        ),
    ]
    return snapshot.model_copy(update={"news": items, "news_at": NOW})


@pytest.fixture
def with_news(store, mailer, clock, tmp_path, snapshot):
    path = tmp_path / "central.json"
    save_snapshot(path, news_snapshot(snapshot))
    return make_client(store, mailer, clock, CENTRAL_SNAPSHOT=str(path))


def test_news_page_lists_and_filters(with_news) -> None:
    page = with_news.get("/central/noticias").text
    assert "<title>Notícias · Central · Geral</title>" in page
    assert page.count("central.js") == 1
    assert "Flamengo vence e abre vantagem" in page and "Vila Nova encara" in page
    assert 'src="https://s2-ge.glbimg.com/fla.jpg"' in page
    assert 'href="/central/noticias/aaaaaaaaaaaa"' in page
    only_b = with_news.get("/central/noticias?serie=b").text
    assert "Vila Nova encara" in only_b and "Flamengo vence" not in only_b


def test_news_reading_page(with_news) -> None:
    page = with_news.get("/central/noticias/aaaaaaaaaaaa").text
    assert "Flamengo vence e abre vantagem" in page
    assert "Rubro-negro chega a 79 pontos" in page
    assert "O Flamengo venceu o Palmeiras neste sábado." in page
    assert 'href="https://ge.globo.com/futebol/noticia/2026/11/21/fla.ghtml"' in page
    assert "Continue lendo no ge" in page


def test_news_reading_page_unknown_id_is_404(with_news) -> None:
    assert with_news.get("/central/noticias/zzzzzzzzzzzz").status_code == 404


def test_central_tabs_link_both_pages(with_news) -> None:
    assert 'href="/central/noticias"' in with_news.get("/central").text
    assert 'href="/central"' in with_news.get("/central/noticias").text


def test_home_shows_latest_headlines(with_news) -> None:
    home = with_news.get("/").text
    assert 'href="/central/noticias/aaaaaaaaaaaa"' in home


@pytest.fixture
def many_news(store, mailer, clock, tmp_path, snapshot):
    from geral.central.models import NewsItem

    items = [
        NewsItem(
            id=f"{i:012d}",
            serie_slug="a" if i % 2 else "b",
            serie_name="Série A" if i % 2 else "Série B",
            title=f"Manchete número {i}",
            url=f"https://ge.globo.com/futebol/noticia/2026/11/21/n{i}.ghtml",
            published_at=datetime(2026, 11, 21, 11, tzinfo=TZ) - timedelta(minutes=i),
        )
        for i in range(30)
    ]
    path = tmp_path / "central.json"
    save_snapshot(path, snapshot.model_copy(update={"news": items, "news_at": NOW}))
    return make_client(store, mailer, clock, CENTRAL_SNAPSHOT=str(path))


def test_news_are_paged_by_twelve(many_news) -> None:
    first = many_news.get("/central/noticias").text
    assert "Manchete número 11<" in first and "Manchete número 12<" not in first
    assert 'href="/central/noticias?pagina=2"' in first
    third = many_news.get("/central/noticias?pagina=3").text
    assert "Manchete número 24<" in third and "Manchete número 29<" in third
    assert "Manchete número 23<" not in third
    assert 'href="/central/noticias?pagina=2"' in third


def test_news_pages_keep_the_serie_and_clamp(many_news) -> None:
    only_a = many_news.get("/central/noticias?serie=a&pagina=2").text  # 15 of A: 12 + 3
    assert only_a.count('class="news-card"') == 3
    assert 'href="/central/noticias?serie=a&amp;pagina=1"' in only_a
    assert many_news.get("/central/noticias?pagina=99").status_code == 200
    assert "Manchete número 29<" in many_news.get("/central/noticias?pagina=99").text
    assert "Manchete número 0<" in many_news.get("/central/noticias?pagina=abc").text


def test_central_links_swap_in_place(with_news) -> None:
    page = with_news.get("/central").text
    assert "data-central" in page and "/static/geral/central.js" in page
    assert 'data-swap href="/central/noticias"' in page
