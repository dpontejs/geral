"""Special-edition banners (`geral especial`): a title won, on top of one team's next edition.

Like the "Novidades" note (notes.py), it lasts until the team publishes an edition, so it goes
out once without any marking; unlike it, each team has its own.
"""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS edition_banners (
    team TEXT PRIMARY KEY,
    kicker TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class BannerStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def create(self, team: str, kicker: str, title: str, now: datetime) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO edition_banners (team, kicker, title, created_at) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (team) DO UPDATE SET kicker = excluded.kicker,"
                " title = excluded.title, created_at = excluded.created_at",
                (team, kicker.strip(), title.strip(), now.isoformat()),
            )

    def cancel(self, team: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM edition_banners WHERE team = ?", (team,))

    def pending(self, team: str, last_published: datetime | None) -> tuple[str, str] | None:
        """(kicker, title), unless the team published an edition after the banner was set."""
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT kicker, title, created_at FROM edition_banners WHERE team = ?", (team,)
            ).fetchone()
        if row is None:
            return None
        if last_published is not None and last_published >= datetime.fromisoformat(row[2]):
            return None
        return row[0], row[1]
