from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from resenha.collectors.base import get_collectors
from resenha.collectors.ge import GECollector
from resenha.teams import get_team

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
