"""Announcements for the next edition of every team (`geral novidade`).

One note at a time. It goes in the "Novidades" box on top of each team's first edition built
after it was written, and stops for a team once that team publishes an edition: the sent one is
published on the page right after sending, so no team gets it twice and none needs marking.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS edition_notes (
    id INTEGER PRIMARY KEY,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cancelled INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(frozen=True)
class Note:
    text: str
    created_at: datetime


class NoteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def create(self, text: str, now: datetime) -> Note:
        """The new note replaces any earlier one still pending."""
        with closing(self._connect()) as db, db:
            db.execute("UPDATE edition_notes SET cancelled = 1")
            db.execute(
                "INSERT INTO edition_notes (text, created_at) VALUES (?, ?)",
                (text.strip(), now.isoformat()),
            )
        return Note(text.strip(), now)

    def cancel(self) -> None:
        with closing(self._connect()) as db, db:
            db.execute("UPDATE edition_notes SET cancelled = 1")

    def latest(self) -> Note | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT text, created_at FROM edition_notes WHERE cancelled = 0"
                " ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return Note(row[0], datetime.fromisoformat(row[1])) if row else None

    def pending(self, last_published: datetime | None) -> str | None:
        """The note, unless the team already published an edition after it was written."""
        note = self.latest()
        if note is None or (last_published is not None and last_published >= note.created_at):
            return None
        return note.text
