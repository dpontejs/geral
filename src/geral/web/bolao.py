"""Bolão: score bets on each team's matches, kept next to the subscribers in the same SQLite.

Every team has its own bolão and season ranking; a match between two teams of the Geral (Vasco x
Palmeiras) is two bolãos. Scores are always from that team's side (our goals, their goals). Points
are computed when read, never stored, so a result sent twice cannot count twice. Only people who
follow the team (active subscription) bet and appear in its ranking; the nickname is one per e-mail
across the whole Geral.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from geral.models import BolaoSummary, RankRow
from geral.web.store import normalize

TZ = ZoneInfo("America/Sao_Paulo")
TOP = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS bolao_matches (
    team TEXT NOT NULL,
    match_id TEXT NOT NULL,
    opponent TEXT NOT NULL,
    home INTEGER NOT NULL,
    kickoff TEXT NOT NULL,
    our_goals INTEGER,
    their_goals INTEGER,
    PRIMARY KEY (team, match_id)
);
CREATE TABLE IF NOT EXISTS bolao_bets (
    email TEXT NOT NULL,
    team TEXT NOT NULL,
    match_id TEXT NOT NULL,
    our_goals INTEGER NOT NULL,
    their_goals INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (email, team, match_id)
);
CREATE TABLE IF NOT EXISTS bolao_players (
    email TEXT PRIMARY KEY,
    nickname TEXT NOT NULL UNIQUE COLLATE NOCASE
);
"""

Score = tuple[int, int]


@dataclass(frozen=True)
class BolaoMatch:
    team: str
    match_id: str
    opponent: str
    home: bool
    kickoff: datetime
    our_goals: int | None
    their_goals: int | None

    @property
    def result(self) -> Score | None:
        return None if self.our_goals is None else (self.our_goals, self.their_goals)


def _outcome(score: Score) -> int:
    return (score[0] > score[1]) - (score[0] < score[1])


def points(bet: Score, result: Score) -> int:
    """Exact 5; right winner and goal difference 3; right outcome 2 (a wrong draw too); else 0."""
    if bet == result:
        return 5
    if _outcome(bet) != _outcome(result):
        return 0
    if _outcome(result) != 0 and bet[0] - bet[1] == result[0] - result[1]:
        return 3
    return 2


def _unique_best(scored: list[tuple[tuple, str]]) -> str | None:
    """The name with the highest key, or None when nobody or more than one has it."""
    if not scored:
        return None
    best = max(key for key, _ in scored)
    names = [name for key, name in scored if key == best]
    return names[0] if len(names) == 1 else None


class BolaoStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(SCHEMA)

    def _run(self, sql: str, *params: object) -> list[tuple]:
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute(sql, params).fetchall()

    def upsert_match(
        self, team: str, match_id: str, opponent: str, home: bool, kickoff: datetime
    ) -> None:
        self._run(
            "INSERT INTO bolao_matches (team, match_id, opponent, home, kickoff)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT (team, match_id) DO UPDATE SET"
            " opponent = excluded.opponent, home = excluded.home, kickoff = excluded.kickoff",
            team,
            match_id,
            opponent,
            int(home),
            kickoff.isoformat(),
        )

    def match(self, team: str, match_id: str) -> BolaoMatch | None:
        rows = self._run(
            "SELECT team, match_id, opponent, home, kickoff, our_goals, their_goals"
            " FROM bolao_matches WHERE team = ? AND match_id = ?",
            team,
            match_id,
        )
        if not rows:
            return None
        team, mid, opponent, home, kickoff, ours, theirs = rows[0]
        return BolaoMatch(
            team, mid, opponent, bool(home), datetime.fromisoformat(kickoff), ours, theirs
        )

    def is_open(self, team: str, match_id: str, now: datetime) -> bool:
        match = self.match(team, match_id)
        return match is not None and now < match.kickoff

    def nickname(self, email: str) -> str | None:
        rows = self._run("SELECT nickname FROM bolao_players WHERE email = ?", normalize(email))
        return rows[0][0] if rows else None

    def set_nickname(self, email: str, nickname: str) -> bool:
        """False when another player already uses it (case-insensitive)."""
        try:
            self._run(
                "INSERT INTO bolao_players (email, nickname) VALUES (?, ?)"
                " ON CONFLICT (email) DO UPDATE SET nickname = excluded.nickname",
                normalize(email),
                nickname.strip(),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    def place_bet(self, email: str, team: str, match_id: str, bet: Score, now: datetime) -> bool:
        """False when the match is unknown or already kicked off."""
        if not self.is_open(team, match_id, now):
            return False
        self._run(
            "INSERT INTO bolao_bets (email, team, match_id, our_goals, their_goals, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (email, team, match_id) DO UPDATE SET"
            " our_goals = excluded.our_goals, their_goals = excluded.their_goals,"
            " updated_at = excluded.updated_at",
            normalize(email),
            team,
            match_id,
            bet[0],
            bet[1],
            now.isoformat(),
        )
        return True

    def bet(self, email: str, team: str, match_id: str) -> Score | None:
        rows = self._run(
            "SELECT our_goals, their_goals FROM bolao_bets"
            " WHERE email = ? AND team = ? AND match_id = ?",
            normalize(email),
            team,
            match_id,
        )
        return rows[0] if rows else None

    def _bets(self, team: str, override: tuple[str, Score] | None = None) -> list[tuple]:
        """(nickname, match_id, kickoff, bet, result) of the team's followers with a nickname."""
        rows = self._run(
            "SELECT p.nickname, b.match_id, m.kickoff, b.our_goals, b.their_goals,"
            " m.our_goals, m.their_goals"
            " FROM bolao_bets b"
            " JOIN bolao_players p ON p.email = b.email"
            " JOIN subscribers s ON s.email = b.email AND s.status = 'active'"
            " JOIN subscriptions f ON f.email = b.email AND f.team = b.team"
            "  AND f.status = 'active'"
            " JOIN bolao_matches m ON m.team = b.team AND m.match_id = b.match_id"
            " WHERE b.team = ?"
            " ORDER BY p.nickname",
            team,
        )
        bets = []
        for nickname, match_id, kickoff, bo, bt, ro, rt in rows:
            result = None if ro is None else (ro, rt)
            if override is not None and match_id == override[0]:
                result = override[1]
            bets.append((nickname, match_id, datetime.fromisoformat(kickoff), (bo, bt), result))
        return bets

    def ranking(
        self, team: str, season: int, override: tuple[str, Score] | None = None
    ) -> list[RankRow]:
        """The team's season (calendar year in Brasília) ranking: points, then exact scores."""
        table: dict[str, list[int]] = {}
        for nickname, _, kickoff, bet, result in self._bets(team, override):
            if kickoff.astimezone(TZ).year != season:
                continue
            row = table.setdefault(nickname, [0, 0])
            if result is not None:
                row[0] += points(bet, result)
                row[1] += bet == result
        rows = [RankRow(nickname=n, points=p, exact=e) for n, (p, e) in table.items()]
        return sorted(rows, key=lambda r: (-r.points, -r.exact, r.nickname.lower()))

    def summary(self, team: str, match_id: str, result: Score, persist: bool) -> BolaoSummary:
        """The match's bolão with this result; persist=False only previews it."""
        if persist:
            self._run(
                "UPDATE bolao_matches SET our_goals = ?, their_goals = ?"
                " WHERE team = ? AND match_id = ?",
                result[0],
                result[1],
                team,
                match_id,
            )
        match = self.match(team, match_id)
        season = match.kickoff.astimezone(TZ).year
        ranking = self.ranking(team, season, override=(match_id, result))
        match_bets = [(n, bet) for n, mid, _, bet, _ in self._bets(team) if mid == match_id]
        real_diff = result[0] - result[1]
        missed = [
            ((abs(bet[0] - bet[1] - real_diff),), n)
            for n, bet in match_bets
            if points(bet, result) == 0
        ]
        return BolaoSummary(
            our_goals=result[0],
            their_goals=result[1],
            exact=[n for n, bet in match_bets if bet == result],
            top=ranking[:TOP],
            king=_unique_best([((r.points, r.exact), r.nickname) for r in ranking if r.points]),
            cold_foot=_unique_best(missed),
        )
