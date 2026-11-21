"""Rebuilds the Central snapshot every few minutes, in a thread of the web app."""

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from geral.central.build import build_snapshot
from geral.central.models import CentralSnapshot
from geral.central.store import load_snapshot, save_snapshot
from geral.config import Settings

logger = logging.getLogger(__name__)

BRASILIA = ZoneInfo("America/Sao_Paulo")


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
    ) -> None:
        self.path = Path(path)
        self.interval = interval
        self._build = build
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """One rebuild; on any error the old snapshot stays and it is logged."""
        try:
            snapshot = self._build(self._clock(), load_snapshot(self.path))
            save_snapshot(self.path, snapshot)
            return True
        except Exception:
            logger.exception("Central refresh failed; keeping %s", self.path)
            return False

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="central-refresh", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval)
