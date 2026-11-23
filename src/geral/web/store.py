"""Subscribers and their teams in SQLite.

An e-mail is confirmed once (pending -> active); each team it follows is a subscription, pending
until a confirmation link is clicked. Leaving the last team unsubscribes the e-mail.
"""

import json
import random
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from pathlib import Path

CONFIRMATION_COOLDOWN = timedelta(minutes=10)
# Data minimization: unconfirmed sign-ups and unsubscribed addresses are deleted after this.
RETENTION = timedelta(days=30)
# A draft let go after its send time is listed for sending this long (a failed run is not retried
# forever; the owner can let it go again).
RELEASE_GRACE = timedelta(hours=3)

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
-- One-off announcements (`geral announce`): who already got each one, so a rerun skips them.
CREATE TABLE IF NOT EXISTS announcements_sent (
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (name, email)
);
-- Each team edition is built first (the owner reviews it) and sent later: one per team, kind, day.
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    team TEXT NOT NULL,
    kind TEXT NOT NULL,
    day TEXT NOT NULL,
    label TEXT NOT NULL,
    newsletter_json TEXT NOT NULL,
    build_at TEXT NOT NULL,
    send_at TEXT NOT NULL,
    held INTEGER NOT NULL DEFAULT 0,
    removed_topics TEXT NOT NULL DEFAULT '[]',
    sent_at TEXT,
    released_at TEXT,
    send_now INTEGER NOT NULL DEFAULT 0,
    UNIQUE (team, kind, day)
);
-- Stories for the special sections, written each night from the sources; refused ones are kept
-- (with the reason) so their source is not tried again.
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    team TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    summary TEXT NOT NULL,
    fact_date TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rejected_reason TEXT,
    used_label TEXT,
    discarded INTEGER NOT NULL DEFAULT 0,
    UNIQUE (team, source_key)
);
-- Birth dates of the idols found by the stories job ("Neste dia").
CREATE TABLE IF NOT EXISTS idol_birthdays (
    team TEXT NOT NULL,
    name TEXT NOT NULL,
    birth_date TEXT NOT NULL,
    source_url TEXT NOT NULL,
    UNIQUE (team, name)
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
class Draft:
    """A built edition waiting for its send time (the owner may hold it or drop topics)."""

    id: int
    team: str
    kind: str
    day: str
    label: str
    newsletter_json: str
    build_at: datetime
    send_at: datetime
    held: bool
    removed_topics: list[int]
    sent_at: datetime | None
    released_at: datetime | None = None  # let go by the owner after holding it
    send_now: bool = False  # the owner published it after reviewing: it does not wait send_at


@dataclass(frozen=True)
class Subscriber:
    email: str
    status: str


def _when(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def normalize(email: str) -> str:
    return email.strip().lower()


class SubscriberStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript(SCHEMA)
            # Columns added after a table already existed in production.
            columns = {row[1] for row in db.execute("PRAGMA table_info(drafts)")}
            if "released_at" not in columns:
                db.execute("ALTER TABLE drafts ADD COLUMN released_at TEXT")
            if "send_now" not in columns:
                db.execute("ALTER TABLE drafts ADD COLUMN send_now INTEGER NOT NULL DEFAULT 0")

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

    def everyone_active(self) -> list[str]:
        """Active e-mails following at least one team, each once."""
        rows = self._run(
            "SELECT DISTINCT u.email FROM subscribers u JOIN subscriptions s USING (email)"
            " WHERE u.status = 'active' AND s.status = 'active' ORDER BY u.email"
        )
        return [email for (email,) in rows]

    def active_since_before(self, team: str, before: datetime) -> set[str]:
        """Active followers of `team` since before `before` (for a moved-in team: the import)."""
        rows = self._run(
            "SELECT s.email FROM subscriptions s JOIN subscribers u USING (email)"
            " WHERE s.team = ? AND s.status = 'active' AND u.status = 'active'"
            " AND s.activated_at < ?",
            team,
            before.astimezone(UTC).isoformat(),  # stored times are UTC ISO strings
        )
        return {email for (email,) in rows}

    def announced(self, name: str) -> set[str]:
        rows = self._run("SELECT email FROM announcements_sent WHERE name = ?", name)
        return {email for (email,) in rows}

    def mark_announced(self, name: str, emails: list[str], now: datetime) -> None:
        with closing(self._connect()) as db, db:
            db.executemany(
                "INSERT OR IGNORE INTO announcements_sent (name, email, sent_at) VALUES (?, ?, ?)",
                [(name, normalize(email), now.isoformat()) for email in emails],
            )

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

    def save_draft(
        self,
        team: str,
        kind: str,
        day: str,
        label: str,
        newsletter_json: str,
        build_at: datetime,
        send_at: datetime,
    ) -> bool:
        """Keep a new draft; False (and the first one kept) when that edition already has one."""
        rows = self._run(
            "INSERT INTO drafts (team, kind, day, label, newsletter_json, build_at, send_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (team, kind, day) DO NOTHING RETURNING id",
            team,
            kind,
            day,
            label,
            newsletter_json,
            build_at.isoformat(),
            send_at.isoformat(),
        )
        return bool(rows)

    _DRAFT_COLUMNS = (
        "id, team, kind, day, label, newsletter_json, build_at, send_at, held, removed_topics,"
        " sent_at, released_at, send_now"
    )

    def _drafts(self, where: str, *params: object) -> list[Draft]:
        rows = self._run(f"SELECT {self._DRAFT_COLUMNS} FROM drafts WHERE {where}", *params)
        return [
            Draft(
                id_,
                team,
                kind,
                day,
                label,
                body,
                datetime.fromisoformat(build_at),
                datetime.fromisoformat(send_at),
                bool(held),
                json.loads(removed),
                _when(sent_at),
                _when(released_at),
                bool(send_now),
            )
            for (
                id_,
                team,
                kind,
                day,
                label,
                body,
                build_at,
                send_at,
                held,
                removed,
                sent_at,
                released_at,
                send_now,
            ) in rows
        ]

    def draft(self, team: str, kind: str, day: str) -> Draft | None:
        found = self._drafts("team = ? AND kind = ? AND day = ?", team, kind, day)
        return found[0] if found else None

    def draft_by_id(self, draft_id: int) -> Draft | None:
        found = self._drafts("id = ?", draft_id)
        return found[0] if found else None

    def pending_drafts(self) -> list[Draft]:
        """Drafts not sent yet, the next to go out first."""
        return sorted(self._drafts("sent_at IS NULL"), key=lambda d: d.send_at)

    def set_held(self, draft_id: int, held: bool, now: datetime) -> Draft | None:
        """Hold or let go of a draft; letting go records when (a late one is sent right away).
        Either way, a "publish now" is undone: let go early, it waits its send time again."""
        self._run(
            "UPDATE drafts SET held = ?, released_at = CASE WHEN ? THEN released_at ELSE ? END,"
            " send_now = 0 WHERE id = ?",
            int(held),
            int(held),
            now.isoformat(),
            draft_id,
        )
        return self.draft_by_id(draft_id)

    def publish_now(self, draft_id: int, now: datetime) -> Draft | None:
        """Reviewed: it goes out at the next tick, not at its send time."""
        self._run(
            "UPDATE drafts SET held = 0, released_at = ?, send_now = 1 WHERE id = ?",
            now.isoformat(),
            draft_id,
        )
        return self.draft_by_id(draft_id)

    def set_topic_removed(self, draft_id: int, topic: int, removed: bool) -> Draft | None:
        draft = self.draft_by_id(draft_id)
        if draft is None:
            return None
        topics = set(draft.removed_topics)
        topics = topics | {topic} if removed else topics - {topic}
        self._run(
            "UPDATE drafts SET removed_topics = ? WHERE id = ?",
            json.dumps(sorted(topics)),
            draft_id,
        )
        return self.draft_by_id(draft_id)

    def set_draft_newsletter(self, draft_id: int, newsletter_json: str) -> None:
        """The draft's edition after the owner took a special section out of it."""
        self._run("UPDATE drafts SET newsletter_json = ? WHERE id = ?", newsletter_json, draft_id)

    def released_due(self, now: datetime) -> list[Draft]:
        """Drafts let go after their send time, or published now by the owner, and not sent yet:
        they go out at the next tick."""
        return [
            d
            for d in self._drafts("sent_at IS NULL AND held = 0 AND released_at IS NOT NULL")
            if (d.send_now or d.send_at <= d.released_at)
            and d.released_at <= now < d.released_at + RELEASE_GRACE
        ]

    def team_drafts(self, team: str) -> list[Draft]:
        return self._drafts("team = ?", team)

    def mark_draft_sent(self, team: str, kind: str, day: str, now: datetime) -> bool:
        """False when there is no such draft."""
        rows = self._run(
            "UPDATE drafts SET sent_at = ? WHERE team = ? AND kind = ? AND day = ? RETURNING id",
            now.isoformat(),
            team,
            kind,
            day,
        )
        return bool(rows)

    def add_story(self, team: str, story: dict, now: datetime) -> bool:
        """Keep a story (or a refusal); False when its source was already seen for the team."""
        fields = (
            "kind",
            "title",
            "body",
            "summary",
            "fact_date",
            "source_url",
            "source_title",
            "source_key",
            "rejected_reason",
        )
        rows = self._run(
            f"INSERT INTO stories (team, {', '.join(fields)}, created_at)"
            f" VALUES (?, {', '.join('?' for _ in fields)}, ?)"
            " ON CONFLICT (team, source_key) DO NOTHING RETURNING id",
            team,
            *(story[f] for f in fields),
            now.isoformat(),
        )
        return bool(rows)

    def unused_stories(self, team: str) -> int:
        rows = self._run(
            "SELECT COUNT(*) FROM stories WHERE team = ? AND rejected_reason IS NULL"
            " AND used_label IS NULL AND discarded = 0",
            team,
        )
        return rows[0][0]

    _STORY_COLUMNS = (
        "id",
        "kind",
        "title",
        "body",
        "summary",
        "fact_date",
        "source_title",
        "source_url",
    )

    def _stories(self, where: str, *params: object) -> list[dict]:
        rows = self._run(
            f"SELECT {', '.join(self._STORY_COLUMNS)} FROM stories WHERE {where} ORDER BY id",
            *params,
        )
        return [dict(zip(self._STORY_COLUMNS, row, strict=True)) for row in rows]

    def draw_story(self, team: str, label: str, reserve: bool = True) -> dict | None:
        """A ready story for the edition `label`, reserved for it; the same one on a rebuild.

        The pick is seeded by the label (a rebuild without reserving picks the same story).
        """
        mine = self._run(
            "SELECT id, discarded FROM stories WHERE team = ? AND used_label = ?", team, label
        )
        if mine:
            story_id, discarded = mine[0]
            return None if discarded else self._stories("id = ?", story_id)[0]
        ready = self._stories(
            "team = ? AND rejected_reason IS NULL AND used_label IS NULL AND discarded = 0", team
        )
        if not ready:
            return None
        rng = random.Random(f"{team}|{label}")
        rng.shuffle(ready)
        if not reserve:
            return ready[0]
        for story in ready:
            # Only if still free: two builds at once must not get the same story.
            if self._run(
                "UPDATE stories SET used_label = ? WHERE id = ? AND used_label IS NULL"
                " RETURNING id",
                label,
                story["id"],
            ):
                return story
        return None

    def discard_story(self, story_id: int) -> None:
        """Removed by the owner in the review: never drawn again."""
        self._run("UPDATE stories SET discarded = 1 WHERE id = ?", story_id)

    def save_birthdays(self, team: str, birthdays: list[dict]) -> None:
        """The team's idols' birth dates, replacing the previous list (one transaction)."""
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM idol_birthdays WHERE team = ?", (team,))
            db.executemany(
                "INSERT OR REPLACE INTO idol_birthdays (team, name, birth_date, source_url)"
                " VALUES (?, ?, ?, ?)",
                [(team, b["name"], b["birth_date"], b["source_url"]) for b in birthdays],
            )

    def on_this_day(self, team: str, day: date, days: int = 3) -> list[dict]:
        """Dated facts (stories, idols' births) whose day and month fall within `days` of `day`."""
        found = []
        births = [
            {"fact_date": when, "title": name, "summary": f"nascia {name}."}
            for name, when in self._run(
                "SELECT name, birth_date FROM idol_birthdays WHERE team = ?", team
            )
        ]
        for story in births + self._stories(
            "team = ? AND rejected_reason IS NULL AND discarded = 0 AND length(fact_date) = 10",
            team,
        ):
            try:
                fact = date.fromisoformat(story["fact_date"])
            except ValueError:
                continue  # a date the calendar does not have
            near = []
            for year in (day.year - 1, day.year, day.year + 1):
                try:
                    near.append(abs((fact.replace(year=year) - day).days))
                except ValueError:  # 29/02 outside a leap year
                    continue
            if near and min(near) <= days:
                found.append(
                    {
                        "date": story["fact_date"],
                        "title": story["title"],
                        "summary": story["summary"],
                    }
                )
        return found

    def story_sources(self, team: str) -> list[str]:
        return [key for (key,) in self._run("SELECT source_key FROM stories WHERE team = ?", team)]

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
