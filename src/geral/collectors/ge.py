import logging
import re
from datetime import datetime, time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from dateutil.parser import isoparse
from selectolax.lexbor import LexborHTMLParser

from geral.collectors.base import create_http_client
from geral.models import Article

logger = logging.getLogger(__name__)

# The team page loads its news from this feed (one instance per page, read on every run).
FEED_INSTANCE = re.compile(
    r"falkor-cda\.bastian\.globo\.com/tenants/ge/instances/([0-9a-f-]{36})/posts"
)
FEED_PAGE_URL = (
    "https://falkor-cda.bastian.globo.com/tenants/ge/instances/{instance}/posts/page/{n}"
)
MAX_FEED_PAGES = 3


class GECollector:
    """The team's news on ge: the page's JSON feed, or the page's headlines when it fails."""

    name: str = "ge"

    def __init__(
        self,
        url: str,
        client: httpx.Client | None = None,
        tz_name: str = "America/Sao_Paulo",
        max_pages: int = MAX_FEED_PAGES,
    ) -> None:
        self.url = url
        self.max_pages = max_pages
        # Team news live under the page path: /pe/futebol/times/nautico/noticia/...
        self.path = urlsplit(url).path
        self._client = client
        self.tz = ZoneInfo(tz_name)

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return create_http_client()

    def collect(self, start: datetime, end: datetime) -> list[Article]:
        """Scrape the team's ge.globo page and extract articles within time window."""
        client = self._get_client()
        try:
            response = client.get(self.url)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            logger.error("Failed to fetch ge.globo page %s: %s", self.url, e)
            return []

        instance = FEED_INSTANCE.search(html)
        if instance is not None:
            try:
                return self.collect_feed(client, instance.group(1), start, end)
            except Exception as e:
                logger.warning("ge feed failed for %s, reading the page instead: %s", self.url, e)
        return self.parse_html(html, start, end)

    def collect_feed(
        self, client: httpx.Client, instance: str, start: datetime, end: datetime
    ) -> list[Article]:
        """Feed items published in [start, end], paging until the page's last item is older."""
        articles: dict[str, Article] = {}
        for n in range(1, self.max_pages + 1):
            response = client.get(FEED_PAGE_URL.format(instance=instance, n=n))
            response.raise_for_status()
            items = response.json().get("items") or []
            dates = []
            for item in items:
                article = self._feed_article(item)
                if article is None:
                    continue
                dates.append(article.published_at)
                if start <= article.published_at <= end:
                    articles.setdefault(article.url, article)
            # Pinned posts open the page; the last item is the oldest of the regular ones.
            if not items or not dates or dates[-1] < start:
                break
        return list(articles.values())

    def _feed_article(self, item: dict) -> Article | None:
        content = item.get("content") or {}
        url, title, published = content.get("url"), content.get("title"), item.get("publication")
        if not (url and title and published):
            return None  # videos and other blocks without a story
        image = ((content.get("image") or {}).get("sizes") or {}).get("L") or {}
        return Article(
            url=url,
            title=title.strip(),
            source="ge",
            published_at=isoparse(published).astimezone(self.tz),
            summary_hint=content.get("summary") or None,
            image_url=image.get("url"),
        )

    def parse_html(self, html: str, start: datetime, end: datetime) -> list[Article]:
        """Parse HTML string and extract Article models within [start, end]."""
        tree = LexborHTMLParser(html)
        articles: list[Article] = []
        seen_urls: set[str] = set()

        target_tz = self.tz
        start_tz = start.astimezone(target_tz) if start.tzinfo else start.replace(tzinfo=target_tz)
        end_tz = end.astimezone(target_tz) if end.tzinfo else end.replace(tzinfo=target_tz)

        # 1. First parse feed-post blocks if present (richer card metadata)
        post_nodes = tree.css(".feed-post")
        for post in post_nodes:
            link_node = post.css_first("a.feed-post-link")
            if not link_node:
                continue

            href = link_node.attributes.get("href", "")
            if not href or href in seen_urls:
                continue

            url = self._normalize_url(href)
            title = link_node.text(strip=True)
            if not title or len(title) < 8:
                continue

            time_node = post.css_first("span.feed-post-datetime")
            time_text = time_node.text(strip=True) if time_node else None

            published_at = self._extract_date_from_url(url, target_tz)
            if not (start_tz.date() <= published_at.date() <= end_tz.date()):
                continue

            seen_urls.add(href)
            seen_urls.add(url)
            articles.append(
                Article(
                    url=url,
                    title=title,
                    source="ge",
                    published_at=published_at,
                    summary_hint=time_text,
                )
            )

        # 2. Also inspect other headline links to news under the team's path
        for a in tree.css("a"):
            href = a.attributes.get("href", "")
            if not href:
                continue

            if not ("/noticia/" in href and self.path in self._normalize_url(href)):
                continue

            url = self._normalize_url(href)
            if url in seen_urls or href in seen_urls:
                continue

            title = a.text(strip=True)
            if not title or len(title) < 10:
                continue

            published_at = self._extract_date_from_url(url, target_tz)
            if not (start_tz.date() <= published_at.date() <= end_tz.date()):
                continue

            seen_urls.add(href)
            seen_urls.add(url)
            articles.append(
                Article(
                    url=url,
                    title=title,
                    source="ge",
                    published_at=published_at,
                )
            )

        return articles

    def _normalize_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return "https://ge.globo.com" + href
        return href

    def _extract_date_from_url(self, url: str, tz: ZoneInfo) -> datetime:
        # Match /noticia/YYYY/MM/DD/
        match = re.search(r"/noticia/(\d{4})/(\d{2})/(\d{2})/", url)
        if match:
            year, month, day = map(int, match.groups())
            return datetime.combine(datetime(year, month, day).date(), time(12, 0, 0), tzinfo=tz)
        return datetime.now(tz)
