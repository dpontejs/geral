"""Import a single-team app (the Urubu News schema) into the Geral, as one team.

Idempotent: running it again changes nothing. It only adds: active subscribers (with the team
active, keeping their other teams), the last edition when the Geral has none newer, the bolão
matches and bets, and nicknames; pending and unsubscribed addresses stay out (they sign up again).
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from geral.web.bolao import BolaoStore
from geral.web.store import SubscriberStore


@dataclass
class ImportReport:
    subscribers: int = 0
    matches: int = 0
    bets: int = 0
    edition: bool = False
    nickname_conflicts: list[str] = field(default_factory=list)


def _rows(path: Path, sql: str) -> list[tuple]:
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        return db.execute(sql).fetchall()


def import_single_team(source: Path, team: str, target: Path) -> ImportReport:
    SubscriberStore(target)  # creates the Geral schema if needed
    BolaoStore(target)
    report = ImportReport()
    active = _rows(
        source,
        "SELECT email, created_at, confirmed_at FROM subscribers WHERE status = 'active'"
        " ORDER BY confirmed_at, email",
    )
    edition = _rows(source, "SELECT subject, html, text, published_at FROM editions WHERE id = 1")
    matches = _rows(
        source,
        "SELECT match_id, opponent, flamengo_home, kickoff, fla_goals, opp_goals"
        " FROM bolao_matches",
    )
    bets = _rows(source, "SELECT email, match_id, fla_goals, opp_goals, updated_at FROM bolao_bets")
    players = _rows(source, "SELECT email, nickname FROM bolao_players")

    with closing(sqlite3.connect(target)) as db, db:
        for email, created_at, confirmed_at in active:
            db.execute(
                "INSERT INTO subscribers (email, status, created_at, confirmed_at)"
                " VALUES (?, 'active', ?, ?) ON CONFLICT (email) DO UPDATE SET"
                " status = 'active', confirmed_at = COALESCE(confirmed_at, excluded.confirmed_at),"
                " unsubscribed_at = NULL",
                (email, created_at, confirmed_at),
            )
            db.execute(
                "INSERT INTO subscriptions (email, team, status, created_at, activated_at)"
                " VALUES (?, ?, 'active', ?, ?) ON CONFLICT (email, team) DO UPDATE SET"
                " status = 'active', activated_at = COALESCE(activated_at, excluded.activated_at)",
                (email, team, created_at, confirmed_at),
            )
        report.subscribers = len(active)

        if edition:
            subject, html, text, published_at = edition[0]
            ours = db.execute(
                "SELECT published_at FROM editions WHERE team = ?", (team,)
            ).fetchone()
            if ours is None or datetime.fromisoformat(ours[0]) < datetime.fromisoformat(
                published_at
            ):
                db.execute(
                    "INSERT INTO editions (team, subject, html, text, published_at)"
                    " VALUES (?, ?, ?, ?, ?) ON CONFLICT (team) DO UPDATE SET"
                    " subject = excluded.subject, html = excluded.html, text = excluded.text,"
                    " published_at = excluded.published_at",
                    (team, subject, html, text, published_at),
                )
                report.edition = True

        for match_id, opponent, home, kickoff, ours_goals, theirs_goals in matches:
            db.execute(
                "INSERT INTO bolao_matches (team, match_id, opponent, home, kickoff, our_goals,"
                " their_goals) VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (team, match_id) DO NOTHING",
                (team, match_id, opponent, home, kickoff, ours_goals, theirs_goals),
            )
        report.matches = len(matches)

        for email, match_id, ours_goals, theirs_goals, updated_at in bets:
            db.execute(
                "INSERT INTO bolao_bets (email, team, match_id, our_goals, their_goals,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (email, team, match_id) DO NOTHING",
                (email, team, match_id, ours_goals, theirs_goals, updated_at),
            )
        report.bets = len(bets)

        for email, nickname in players:
            try:
                db.execute(
                    "INSERT INTO bolao_players (email, nickname) VALUES (?, ?)"
                    " ON CONFLICT (email) DO NOTHING",
                    (email, nickname),
                )
            except sqlite3.IntegrityError:  # someone in the Geral already took the nickname
                report.nickname_conflicts.append(nickname)
    return report
