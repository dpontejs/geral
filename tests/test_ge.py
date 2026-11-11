from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from geral.collectors.base import get_collectors
from geral.collectors.ge import GECollector
from geral.teams import get_team

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURES / "ge_flamengo.html"
GE_FLAMENGO_URL = "https://ge.globo.com/futebol/times/flamengo/"


@pytest.fixture
def ge_html_fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_ge_collector_parse_html(ge_html_fixture: str) -> None:
    collector = GECollector(url=GE_FLAMENGO_URL)
    tz = ZoneInfo("America/Sao_Paulo")

    start = datetime(2026, 10, 10, 0, 0, 0, tzinfo=tz)
    end = datetime(2026, 10, 15, 23, 59, 59, tzinfo=tz)

    articles = collector.parse_html(ge_html_fixture, start, end)

    # Acceptance: extracts at least 5 articles with absolute URL
    assert len(articles) >= 5
    for article in articles:
        assert article.source == "ge"
        assert article.title
        assert article.url.startswith("https://ge.globo.com/")
        assert article.published_at.tzinfo is not None


@respx.mock
def test_ge_collector_network_success(ge_html_fixture: str) -> None:
    respx.get(GE_FLAMENGO_URL).mock(return_value=httpx.Response(200, text=ge_html_fixture))

    collector = GECollector(url=GE_FLAMENGO_URL)
    tz = ZoneInfo("America/Sao_Paulo")

    start = datetime(2026, 10, 10, 0, 0, 0, tzinfo=tz)
    end = datetime(2026, 10, 15, 23, 59, 59, tzinfo=tz)

    articles = collector.collect(start, end)
    assert len(articles) >= 5


@respx.mock
def test_ge_collector_network_error() -> None:
    respx.get(GE_FLAMENGO_URL).mock(return_value=httpx.Response(500))

    collector = GECollector(url=GE_FLAMENGO_URL)
    tz = ZoneInfo("America/Sao_Paulo")
    start = datetime(2026, 10, 10, 0, 0, 0, tzinfo=tz)
    end = datetime(2026, 10, 15, 0, 0, 0, tzinfo=tz)

    articles = collector.collect(start, end)
    assert articles == []


def test_ge_collector_registry() -> None:
    collectors = get_collectors(get_team("nautico"))
    assert any(c.name == "ge" for c in collectors)


@respx.mock
def test_ge_collector_uses_team_page() -> None:
    abc = get_team("abc")
    route = respx.get(abc.ge_url).mock(
        return_value=httpx.Response(200, text=(FIXTURES / "ge_abc.html").read_text("utf-8"))
    )
    tz = ZoneInfo("America/Sao_Paulo")

    articles = GECollector(url=abc.ge_url).collect(
        datetime(2026, 10, 1, tzinfo=tz), datetime(2026, 11, 10, 23, 59, tzinfo=tz)
    )

    assert route.called
    # The feed also lists regional news; the pipeline's relevance filter drops those.
    assert sum("/rn/futebol/times/abc/noticia/" in a.url for a in articles) >= 5


GE_ABC_URL = "https://ge.globo.com/rn/futebol/times/abc/"
ABC_FEED = (
    "https://falkor-cda.bastian.globo.com/tenants/ge/instances/"
    "4b8faafe-65bb-4857-8f02-b73ede244276/posts/page/{n}"
)
TZ = ZoneInfo("America/Sao_Paulo")


def feed_page(n: int) -> httpx.Response:
    return httpx.Response(200, text=(FIXTURES / "ge_feed" / f"abc_page{n}.json").read_text())


@pytest.fixture
def abc_feed() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.get(GE_ABC_URL).mock(
            return_value=httpx.Response(200, text=(FIXTURES / "ge_abc.html").read_text())
        )
        for n in (1, 2):
            router.get(ABC_FEED.format(n=n)).mock(return_value=feed_page(n))
        router.get(ABC_FEED.format(n=3)).mock(return_value=httpx.Response(200, json={"items": []}))
        yield router


def collect_abc(start: datetime, end: datetime) -> list:
    return GECollector(url=GE_ABC_URL, client=httpx.Client()).collect(start, end)


def test_ge_collector_reads_the_team_feed(abc_feed) -> None:
    articles = collect_abc(
        datetime(2026, 11, 5, tzinfo=TZ), datetime(2026, 11, 11, 23, 0, tzinfo=TZ)
    )

    wallyson = next(a for a in articles if a.title.startswith("Wallyson renova"))
    assert wallyson.published_at == datetime(2026, 11, 11, 13, 42, 15, 244000, tzinfo=TZ)
    assert wallyson.url.startswith("https://ge.globo.com/rn/futebol/times/abc/noticia/2026/11/11/")
    assert wallyson.summary_hint.startswith("Ídolo do ABC")
    assert wallyson.image_url and wallyson.image_url.startswith("https://")
    assert wallyson.source == "ge"
    assert all(a.published_at >= datetime(2026, 11, 5, tzinfo=TZ) for a in articles)
    assert len(articles) == 5
    assert [str(c.request.url) for c in abc_feed.calls][-1] == ABC_FEED.format(n=1)


def test_ge_feed_follows_pages_until_the_window_start(abc_feed) -> None:
    articles = collect_abc(
        datetime(2026, 10, 20, tzinfo=TZ), datetime(2026, 10, 29, 23, 0, tzinfo=TZ)
    )

    assert ABC_FEED.format(n=2) in [str(c.request.url) for c in abc_feed.calls]
    assert any(a.published_at.date() == datetime(2026, 10, 28).date() for a in articles)
    assert len({a.url for a in articles}) == len(articles)


def test_ge_feed_down_falls_back_to_the_page(abc_feed) -> None:
    abc_feed.get(ABC_FEED.format(n=1)).mock(return_value=httpx.Response(503))
    html = (FIXTURES / "ge_abc.html").read_text()
    collector = GECollector(url=GE_ABC_URL, client=httpx.Client())
    start, end = datetime(2026, 1, 1, tzinfo=TZ), datetime(2026, 12, 31, tzinfo=TZ)

    assert collector.collect(start, end) == collector.parse_html(html, start, end)


def test_ge_page_without_feed_uses_the_page() -> None:
    html = (
        '<div class="feed-post"><a class="feed-post-link" href="https://ge.globo.com/rn/futebol/'
        'times/abc/noticia/2026/11/10/abc-treina.ghtml">ABC treina forte para 2027</a></div>'
    )
    with respx.mock() as router:
        router.get(GE_ABC_URL).mock(return_value=httpx.Response(200, text=html))

        articles = collect_abc(datetime(2026, 11, 9, tzinfo=TZ), datetime(2026, 11, 11, tzinfo=TZ))

    assert [a.title for a in articles] == ["ABC treina forte para 2027"]
