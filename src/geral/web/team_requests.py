"""Team requests: people ask for a team the Geral lacks (docs/features/pedido-de-time.md).

One vote per person per team: the requester is the e-mail or, without one, a keyed hash of the
IP. Names are grouped by a normalized key and shown as the form most people typed. The e-mail is
kept only to tell that person when the team is born; the public list never shows it.
"""

import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_requests (
    team_key TEXT NOT NULL,
    team_name TEXT NOT NULL,
    requester TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (team_key, requester)
);
"""


def team_key(name: str) -> str:
    """'Sampaio  Corrêa!' -> 'sampaio correa'."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


@dataclass(frozen=True)
class RequestedTeam:
    key: str
    name: str  # the form most requesters typed
    votes: int
    emails: list[str]


class TeamRequestStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def add(self, name: str, requester: str, email: str | None, now: datetime) -> None:
        """Count `requester`'s vote for the team; asking again only fills a missing e-mail."""
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO team_requests (team_key, team_name, requester, email, created_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT (team_key, requester) DO UPDATE SET"
                " email = COALESCE(excluded.email, team_requests.email)",
                (team_key(name), name.strip(), requester, email, now.isoformat()),
            )

    def top(self, limit: int = 10) -> list[RequestedTeam]:
        """Most requested teams first (ties: the earliest asked), with the e-mails given."""
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT team_key, team_name, email, created_at FROM team_requests"
                " ORDER BY created_at"
            ).fetchall()
        groups: dict[str, list[tuple[str, str | None]]] = {}
        for key, name, email, _ in rows:
            groups.setdefault(key, []).append((name, email))
        teams = [
            RequestedTeam(
                key=key,
                name=Counter(name for name, _ in entries).most_common(1)[0][0],
                votes=len(entries),
                emails=[email for _, email in entries if email],
            )
            for key, entries in groups.items()
        ]
        return sorted(teams, key=lambda t: -t.votes)[:limit]  # stable: earliest first on ties

    def position(self, key: str) -> tuple[int, RequestedTeam] | None:
        ranking = self.top(limit=10_000)
        return next(((i, t) for i, t in enumerate(ranking, 1) if t.key == key), None)
