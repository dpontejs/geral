"""Team requests: people ask for a team the Geral lacks (docs/features/pedido-de-time.md).

One vote per network per team: the voter is a keyed hash of the IP (an IPv6 /64 counts as one),
so made-up e-mails do not add votes. The e-mail, when given, is kept on the vote only to tell that
person when the team is born; the public list never shows it, and only teams past a minimum of
votes appear in public (a single person cannot put a name on the home page).
"""

import ipaddress
import re
import sqlite3
import unicodedata
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PUBLIC_MIN_VOTES = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_requests (
    team_key TEXT NOT NULL,
    team_name TEXT NOT NULL,
    voter TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (team_key, voter)
);
"""


def team_key(name: str) -> str:
    """'Sampaio  Corrêa!' -> 'sampaio correa'; empty when no Latin letter or digit is left."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


def network(ip: str) -> str:
    """The voter's network: the IPv4 address, or the IPv6 /64 (one home or phone line)."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


@dataclass(frozen=True)
class RequestedTeam:
    key: str
    name: str  # the form most voters typed
    votes: int
    emails: list[str]


class TeamRequestStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def add(self, name: str, voter: str, email: str | None, now: datetime) -> bool:
        """Count `voter`'s vote for the team (True: a new vote); asking again fills the e-mail."""
        with closing(self._connect()) as db, db:
            seen = db.execute(
                "SELECT 1 FROM team_requests WHERE team_key = ? AND voter = ?",
                (team_key(name), voter),
            ).fetchone()
            db.execute(
                "INSERT INTO team_requests (team_key, team_name, voter, email, created_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT (team_key, voter) DO UPDATE SET"
                " email = COALESCE(excluded.email, team_requests.email)",
                (team_key(name), name.strip(), voter, email, now.isoformat()),
            )
        return seen is None

    def top(self, limit: int = 10, min_votes: int = PUBLIC_MIN_VOTES) -> list[RequestedTeam]:
        """Most requested teams first (ties: the earliest asked), from `min_votes` votes."""
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT team_key, COUNT(*) AS votes FROM team_requests GROUP BY team_key"
                " HAVING votes >= ? ORDER BY votes DESC, MIN(created_at) LIMIT ?",
                (min_votes, limit),
            ).fetchall()
            return [self._team(db, key, votes) for key, votes in rows]

    def position(self, key: str) -> tuple[int, RequestedTeam] | None:
        """Where the team stands among all requests (no minimum)."""
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT COUNT(*), MIN(created_at) FROM team_requests WHERE team_key = ?", (key,)
            ).fetchone()
            votes, first = row
            if not votes:
                return None
            ahead = db.execute(
                "SELECT COUNT(*) FROM (SELECT COUNT(*) AS v, MIN(created_at) AS f"
                " FROM team_requests GROUP BY team_key) WHERE v > ? OR (v = ? AND f < ?)",
                (votes, votes, first),
            ).fetchone()[0]
            return ahead + 1, self._team(db, key, votes)

    def _team(self, db: sqlite3.Connection, key: str, votes: int) -> RequestedTeam:
        name = db.execute(
            "SELECT team_name FROM team_requests WHERE team_key = ? GROUP BY team_name"
            " ORDER BY COUNT(*) DESC, MIN(created_at) LIMIT 1",
            (key,),
        ).fetchone()[0]
        emails = [
            email
            for (email,) in db.execute(
                "SELECT email FROM team_requests WHERE team_key = ? AND email IS NOT NULL"
                " ORDER BY created_at",
                (key,),
            )
        ]
        return RequestedTeam(key=key, name=name, votes=votes, emails=emails)
