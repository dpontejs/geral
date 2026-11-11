"""Subscribers and their teams in SQLite.

An e-mail is confirmed once (pending -> active); each team it follows is a subscription, pending
until a confirmation link is clicked. Leaving the last team unsubscribes the e-mail.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

CONFIRMATION_COOLDOWN = timedelta(minutes=10)
# Data minimization: unconfirmed sign-ups and unsubscribed addresses are deleted after this.
RETENTION = timedelta(days=30)

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    email TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'unsubscribed')),
    created_at TEXT NOT NULL,
    confirmation_sent_at TEXT,
    confirmed_at TEXT,
    unsubscribed_at TEXT
);
CREATE TABLE IF NOT EXISTS subscriptions (
    email TEXT NOT NULL REFERENCES subscribers (email) ON DELETE CASCADE,
    team TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'active')),
    created_at TEXT NOT NULL,
    activated_at TEXT,
    PRIMARY KEY (email, team)
);
-- Every confirmation e-mail sent: the daily cap counts e-mails, not people.
CREATE TABLE IF NOT EXISTS confirmations_sent (
    email TEXT NOT NULL,
    sent_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS editions (
    team TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    html TEXT NOT NULL,
    text TEXT NOT NULL,
    published_at TEXT NOT NULL
);
"""


class RequestResult(Enum):
    SEND_CONFIRMATION = "send_confirmation"
    COOLDOWN = "cooldown"
    ALREADY_ACTIVE = "already_active"  # every requested team is already active


@dataclass(frozen=True)
class Edition:
    """A team's last edition sent, with the unsubscribe placeholder still in it."""

    subject: str
    html: str
    text: str
    published_at: datetime


@dataclass(frozen=True)
class Subscriber:
    email: str
    status: str


def normalize(email: str) -> str:
    return email.strip().lower()


class SubscriberStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _run(self, sql: str, *params: object) -> list[tuple]:
        # `with connection` commits; `closing` releases the file handle.
        with closing(self._connect()) as db, db:
            return db.execute(sql, params).fetchall()

    def get(self, email: str) -> Subscriber | None:
        rows = self._run("SELECT email, status FROM subscribers WHERE email = ?", normalize(email))
        return Subscriber(*rows[0]) if rows else None

    def _teams(self, email: str, status: str) -> list[str]:
        rows = self._run(
            "SELECT team FROM subscriptions WHERE email = ? AND status = ? ORDER BY team",
            normalize(email),
            status,
        )
        return [team for (team,) in rows]

    def teams_of(self, email: str) -> list[str]:
        """Active teams of an active e-mail."""
        subscriber = self.get(email)
        if subscriber is None or subscriber.status != "active":
            return []
        return self._teams(email, "active")

    def pending_teams(self, email: str) -> list[str]:
        return self._teams(email, "pending")

    def request(self, email: str, teams: list[str], now: datetime) -> RequestResult:
        """Register a sign-up for `teams`; tells whether a confirmation e-mail should go out."""
        email = normalize(email)
        rows = self._run(
            "SELECT status, confirmation_sent_at FROM subscribers WHERE email = ?", email
        )
        if not rows:
            self._run(
                "INSERT INTO subscribers (email, status, created_at) VALUES (?, 'pending', ?)",
                email,
                now.isoformat(),
            )
            status, sent_at = "pending", None
        else:
            status, sent_at = rows[0]
        if status == "unsubscribed":
            self._run("DELETE FROM subscriptions WHERE email = ?", email)
        active = set(self._teams(email, "active")) if status == "active" else set()
        new = sorted(set(teams) - active)
        if not new:
            return RequestResult.ALREADY_ACTIVE
        for team in new:
            self._run(
                "INSERT INTO subscriptions (email, team, status, created_at)"
                " VALUES (?, ?, 'pending', ?) ON CONFLICT (email, team) DO UPDATE"
                " SET created_at = excluded.created_at WHERE subscriptions.status = 'pending'",
                email,
                team,
                now.isoformat(),
            )
        recently_sent = sent_at and now - datetime.fromisoformat(sent_at) < CONFIRMATION_COOLDOWN
        if recently_sent:  # any status: an active address must not be flooded either
            return RequestResult.COOLDOWN
        self._run(
            "UPDATE subscribers SET status = CASE WHEN status = 'active' THEN 'active'"
            " ELSE 'pending' END, confirmation_sent_at = ? WHERE email = ?",
            now.isoformat(),
            email,
        )
        self._run(
            "INSERT INTO confirmations_sent (email, sent_at) VALUES (?, ?)", email, now.isoformat()
        )
        return RequestResult.SEND_CONFIRMATION

    def forget_confirmation(self, email: str) -> None:
        """Lift the cooldown after a confirmation e-mail failed to go out."""
        email = normalize(email)
        self._run("UPDATE subscribers SET confirmation_sent_at = NULL WHERE email = ?", email)
        self._run(
            "DELETE FROM confirmations_sent WHERE rowid ="
            " (SELECT MAX(rowid) FROM confirmations_sent WHERE email = ?)",
            email,
        )

    def confirm(self, email: str, now: datetime) -> list[str] | None:
        """Activate the e-mail and its pending teams; returns the teams activated now.

        None when the link is no good: unknown e-mail, or one that unsubscribed since (an old
        confirmation link must not undo that). An empty list means nothing was pending.
        """
        email = normalize(email)
        subscriber = self.get(email)
        if subscriber is None or subscriber.status == "unsubscribed":
            return None
        if subscriber.status == "pending" and not self.pending_teams(email):
            return None  # nothing left to confirm (purged): not a subscription
        # Confirming lifts the cooldown: adding a team right after is a new, legit request.
        self._run(
            "UPDATE subscribers SET status = 'active', confirmation_sent_at = NULL,"
            " confirmed_at = CASE WHEN status = 'pending' THEN ? ELSE confirmed_at END"
            " WHERE email = ?",
            now.isoformat(),
            email,
        )
        rows = self._run(
            "UPDATE subscriptions SET status = 'active', activated_at = ?"
            " WHERE email = ? AND status = 'pending' RETURNING team",
            now.isoformat(),
            email,
        )
        return sorted(team for (team,) in rows)

    def leave(self, email: str, team: str, now: datetime) -> None:
        email = normalize(email)
        self._run("DELETE FROM subscriptions WHERE email = ? AND team = ?", email, team)
        if not self._teams(email, "active"):
            self.leave_all(email, now)

    def leave_all(self, email: str, now: datetime) -> None:
        email = normalize(email)
        self._run("DELETE FROM subscriptions WHERE email = ?", email)
        self._run(
            "UPDATE subscribers SET status = 'unsubscribed', unsubscribed_at = ?,"
            " confirmation_sent_at = NULL WHERE email = ? AND status != 'unsubscribed'",
            now.isoformat(),
            email,
        )

    def active(self, team: str) -> list[str]:
        rows = self._run(
            "SELECT s.email FROM subscriptions s JOIN subscribers u USING (email)"
            " WHERE s.team = ? AND s.status = 'active' AND u.status = 'active'"
            " ORDER BY s.activated_at, s.email",
            team,
        )
        return [email for (email,) in rows]

    def counts(self) -> dict[str, int]:
        """Active subscribers per team (the Geral scoreboard)."""
        rows = self._run(
            "SELECT s.team, COUNT(*) FROM subscriptions s JOIN subscribers u USING (email)"
            " WHERE s.status = 'active' AND u.status = 'active' GROUP BY s.team"
        )
        return dict(rows)

    def set_latest_edition(
        self, team: str, subject: str, html: str, text: str, now: datetime
    ) -> None:
        self._run(
            "INSERT INTO editions (team, subject, html, text, published_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (team) DO UPDATE SET subject = excluded.subject, html = excluded.html,"
            " text = excluded.text, published_at = excluded.published_at",
            team,
            subject,
            html,
            text,
            now.isoformat(),
        )

    def latest_edition(self, team: str) -> Edition | None:
        return self.latest_editions().get(team)

    def latest_editions(self) -> dict[str, Edition]:
        rows = self._run("SELECT team, subject, html, text, published_at FROM editions")
        return {
            team: Edition(subject, html, text, datetime.fromisoformat(published_at))
            for team, subject, html, text, published_at in rows
        }

    def confirmations_sent_since(self, since: datetime) -> int:
        rows = self._run(
            "SELECT COUNT(*) FROM confirmations_sent WHERE sent_at >= ?", since.isoformat()
        )
        return rows[0][0]

    def purge(self, now: datetime) -> int:
        """Delete stale pending sign-ups and old unsubscribes; returns how many e-mails went.

        Teams added by an active subscriber but never confirmed are dropped too.
        """
        cutoff = (now - RETENTION).isoformat()
        self._run(
            "DELETE FROM confirmations_sent WHERE sent_at < ?",
            (now - timedelta(days=2)).isoformat(),
        )
        self._run("DELETE FROM subscriptions WHERE status = 'pending' AND created_at < ?", cutoff)
        rows = self._run(
            "DELETE FROM subscribers WHERE"
            " (status = 'pending' AND COALESCE(confirmation_sent_at, created_at) < ?)"
            " OR (status = 'unsubscribed' AND unsubscribed_at < ?)"
            " RETURNING email",
            cutoff,
            cutoff,
        )
        return len(rows)
