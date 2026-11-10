from datetime import datetime
from typing import Protocol

import httpx

from resenha.models import Article
from resenha.teams import Team

USER_AGENT = "resenha/0.1 (+contato@resenha.local)"
DEFAULT_TIMEOUT = 15.0


def create_http_client() -> httpx.Client:
    """Create a configured HTTP client for collectors."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    )


class Collector(Protocol):
    """Protocol defining news collector interface."""

    name: str

    def collect(self, start: datetime, end: datetime) -> list[Article]:
        """Collect articles within the given time window."""
        ...


def get_collectors(team: Team) -> list[Collector]:
    """The team's news collectors."""
    from resenha.collectors.ge import GECollector
    from resenha.collectors.google_news import GoogleNewsCollector, google_news_url

    return [
        GoogleNewsCollector(rss_url=google_news_url(team.news_query)),
        GECollector(url=team.ge_url),
    ]
