from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from resenha.collectors.base import get_collectors
from resenha.collectors.google_news import GoogleNewsCollector, google_news_url
from resenha.teams import get_team

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "google_news.xml"
GOOGLE_NEWS_RSS_URL = google_news_url("Flamengo futebol")


@pytest.fixture
def rss_fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


@respx.mock
def test_google_news_collector_success(rss_fixture: str) -> None:
    respx.get(GOOGLE_NEWS_RSS_URL).mock(return_value=httpx.Response(200, text=rss_fixture))

    collector = GoogleNewsCollector(rss_url=GOOGLE_NEWS_RSS_URL)
    tz = ZoneInfo("America/Sao_Paulo")

    start = datetime(2026, 10, 10, 0, 0, 0, tzinfo=tz)
    end = datetime(2026, 10, 15, 23, 59, 59, tzinfo=tz)

    articles = collector.collect(start, end)
    assert len(articles) > 0

    first = articles[0]
    assert first.source.startswith("google_news:")
    assert first.url.startswith("https://news.google.com")
    assert first.title
    assert first.published_at.tzinfo is not None
    assert start <= first.published_at <= end


@respx.mock
def test_google_news_collector_date_filtering(rss_fixture: str) -> None:
    respx.get(GOOGLE_NEWS_RSS_URL).mock(return_value=httpx.Response(200, text=rss_fixture))

    collector = GoogleNewsCollector(rss_url=GOOGLE_NEWS_RSS_URL)
    tz = ZoneInfo("America/Sao_Paulo")

    # Narrow window: only on 14/10 between 10:00 and 11:00 BRT (13:00 to 14:00 UTC)
    start = datetime(2026, 10, 14, 10, 0, 0, tzinfo=tz)
    end = datetime(2026, 10, 14, 11, 0, 0, tzinfo=tz)

    articles = collector.collect(start, end)
    for article in articles:
        assert start <= article.published_at <= end


@respx.mock
def test_google_news_collector_error_resilience() -> None:
    respx.get(GOOGLE_NEWS_RSS_URL).mock(return_value=httpx.Response(500))

    collector = GoogleNewsCollector(rss_url=GOOGLE_NEWS_RSS_URL)
    tz = ZoneInfo("America/Sao_Paulo")
    start = datetime(2026, 10, 10, 0, 0, 0, tzinfo=tz)
    end = datetime(2026, 10, 15, 0, 0, 0, tzinfo=tz)

    articles = collector.collect(start, end)
    assert articles == []


def test_get_collectors_registry() -> None:
    vasco = get_team("vasco")
    collectors = get_collectors(vasco)
    google = next(c for c in collectors if c.name == "google_news")
    assert google.rss_url == google_news_url(vasco.news_query)
