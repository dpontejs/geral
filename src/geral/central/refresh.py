"""Rebuilds the Central snapshot every few minutes, in a thread of the web app."""

import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from geral.central.build import build_snapshot
from geral.central.models import CentralSnapshot, NewsItem
from geral.central.news import collect_news, refresh_news
from geral.central.store import load_snapshot, save_snapshot
from geral.collectors.base import DEFAULT_TIMEOUT, USER_AGENT
from geral.config import Settings

logger = logging.getLogger(__name__)

BRASILIA = ZoneInfo("America/Sao_Paulo")
ROUND_URL = re.compile(r"/rodada/\d+/jogos/?$")
SETTLED = timedelta(days=3)  # a round played this long ago keeps its scores


class FinishedRoundsTransport(httpx.BaseTransport):
    """Keeps ge round pages whose games all have a score and are days old: they never change.

    A refresh reads every round of the A, B and C (~100 pages); with this, only the open ones.
    """

    def __init__(self, inner: httpx.BaseTransport, clock: Callable[[], datetime]) -> None:
        self._inner = inner
        self._clock = clock
        self._kept: dict[str, bytes] = {}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in self._kept:
            return httpx.Response(
                200, content=self._kept[url], headers={"content-type": "application/json"}
            )
        response = self._inner.handle_request(request)
        if request.method == "GET" and ROUND_URL.search(request.url.path):
            response.read()
            if response.status_code == 200 and self._settled(response.content):
                self._kept[url] = response.content
        return response

    def _settled(self, body: bytes) -> bool:
        try:
            games = json.loads(body)
        except ValueError:
            return False
        limit = (self._clock() - SETTLED).date()
        return bool(games) and all(
            g.get("placar_oficial_mandante") is not None
            and g.get("placar_oficial_visitante") is not None
            and date.fromisoformat(str(g.get("data_realizacao"))[:10]) <= limit
            for g in games
        )

    def close(self) -> None:
        self._inner.close()


def snapshot_path(settings: Settings) -> Path:
    """CENTRAL_SNAPSHOT, or central.json next to the SQLite (the same Docker volume)."""
    if settings.CENTRAL_SNAPSHOT:
        return Path(settings.CENTRAL_SNAPSHOT)
    return Path(settings.SUBSCRIBERS_DB).with_name("central.json")


class Refresher:
    def __init__(
        self,
        path: Path,
        interval: int,
        build: Callable[[datetime, CentralSnapshot | None], CentralSnapshot] = build_snapshot,
        clock: Callable[[], datetime] = lambda: datetime.now(BRASILIA),
        news: Callable[[datetime, list[NewsItem]], list[NewsItem]] | None = None,
    ) -> None:
        self.path = Path(path)
        self.interval = interval
        self._build = build
        self._clock = clock
        self._stop = threading.Event()
        self._news = news or (lambda at, old: collect_news(at, old, client=self._client))
        # One client for the app's life: finished ge rounds are fetched once.
        transport = FinishedRoundsTransport(httpx.HTTPTransport(), clock)
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """One rebuild; on any error the old snapshot stays and it is logged."""
        try:
            now = self._clock()
            snapshot = self._build(now, load_snapshot(self.path), client=self._client)
            save_snapshot(self.path, snapshot)  # tables first: news can take minutes
        except Exception:
            logger.exception("Central refresh failed; keeping %s", self.path)
            return False
        try:
            with_news = refresh_news(snapshot, now, self._news)
            if with_news is not snapshot:
                save_snapshot(self.path, with_news)
        except Exception:
            logger.exception("Central news refresh failed; the tables were saved")
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="central-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._client.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval)
