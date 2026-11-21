"""The Central's news tab: the four séries' ge feeds, with each story's opening paragraph.

See docs/features/central-noticias.md. No LLM and never the whole story: title, linha fina,
photo, the first paragraph and the link to read the rest on ge.
"""

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx

from geral.central.models import CentralSnapshot, NewsItem
from geral.collectors.base import create_http_client
from geral.collectors.ge import GECollector
from geral.general import SERIES
from geral.models import Article
from geral.processing.extract import DomainRateLimiter, extract_content

logger = logging.getLogger(__name__)

SLUGS = {"Série A": "a", "Série B": "b", "Série C": "c", "Série D": "d"}
WINDOW = timedelta(hours=48)
FEED_PAGES = 3
MAX_NEWS = 60
LEAD_CHARS = 320
NEWS_EVERY = timedelta(hours=1)


def news_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def first_paragraph(text: str | None, limit: int = LEAD_CHARS) -> str | None:
    """The text's first non-empty paragraph, cut at a word with an ellipsis past `limit`."""
    paragraph = next((line.strip() for line in (text or "").splitlines() if line.strip()), None)
    if paragraph is None or len(paragraph) <= limit:
        return paragraph
    return paragraph[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def collect_news(
    now: datetime,
    previous: list[NewsItem],
    series: dict[str, str] | None = None,
    fetch_feed: Callable[[str, str], list[Article]] | None = None,
    fetch_lead: Callable[[Article], str | None] | None = None,
    client: httpx.Client | None = None,
) -> list[NewsItem]:
    """The newest stories of every série; a série whose feed comes back empty keeps its old ones."""
    series = series if series is not None else SERIES
    if fetch_feed is None or fetch_lead is None:
        client = client or create_http_client()
        limiter = DomainRateLimiter()
        fetch_feed = fetch_feed or (
            lambda name, page: GECollector(url=page, client=client, max_pages=FEED_PAGES).collect(
                now - WINDOW, now
            )
        )
        fetch_lead = fetch_lead or (
            lambda a: first_paragraph(extract_content(a, client, limiter).content)
        )
    known = {item.url: item for item in previous}
    stories: dict[str, NewsItem] = {}
    for name, page in series.items():
        try:
            found = [a for a in fetch_feed(name, page) if _is_ge_story(a.url)]
        except Exception as e:
            logger.warning("Central news: %s feed failed: %s", name, e)
            found = []
        if not found:  # out of season or the feed failed: its stories stay until 48 h old
            for item in previous:
                if item.serie_name == name and item.published_at >= now - WINDOW:
                    stories.setdefault(item.url, item)
            continue
        for article in found:
            if article.url in stories:
                continue
            old = known.get(article.url)
            stories[article.url] = NewsItem(
                id=news_id(article.url),
                serie_slug=SLUGS[name],
                serie_name=name,
                title=article.title,
                summary=article.summary_hint,
                image_url=article.image_url,
                url=article.url,
                published_at=article.published_at,
                lead=old.lead if old else None,
            )
    newest = sorted(stories.values(), key=lambda n: n.published_at, reverse=True)[:MAX_NEWS]
    for item in newest:  # only the kept ones, and again when it failed before
        if item.lead is None:
            item.lead = _lead(fetch_lead, _article(item))
    return newest


def _is_ge_story(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return (
        parts.scheme == "https"
        and (host == "globo.com" or host.endswith(".globo.com"))
        and "/noticia/" in parts.path
    )


def _article(item: NewsItem) -> Article:
    return Article(
        url=item.url,
        title=item.title,
        source="ge",
        published_at=item.published_at,
        summary_hint=item.summary,
        image_url=item.image_url,
    )


def refresh_news(
    snapshot: CentralSnapshot,
    now: datetime,
    collect: Callable[[datetime, list[NewsItem]], list[NewsItem]],
) -> CentralSnapshot:
    """The snapshot with fresh news once an hour; on failure it keeps the old ones."""
    if snapshot.news_at is not None and now - snapshot.news_at < NEWS_EVERY:
        return snapshot
    try:
        stories = collect(now, snapshot.news)
    except Exception as e:
        logger.warning("Central: news not refreshed: %s", e)
        return snapshot
    return snapshot.model_copy(update={"news": stories, "news_at": now})


def _lead(fetch_lead: Callable[[Article], str | None], article: Article) -> str | None:
    try:
        return fetch_lead(article)
    except Exception as e:
        logger.warning("Central news: no first paragraph for %s: %s", article.url, e)
        return None
