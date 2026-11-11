"""What both ge table formats load into: the competition's matches and current table."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from geral.models import StandingRow

MATCH_LENGTH = timedelta(hours=2, minutes=15)  # after this, a match with a score is over


@dataclass(frozen=True)
class Game:
    id: int
    competition: str
    kickoff: datetime
    time_valid: bool
    home: str
    away: str
    home_id: int
    away_id: int
    home_goals: int | None
    away_goals: int | None
    venue: str | None
    started: bool = False  # ge's `jogo_ja_comecou`
    home_penalties: int | None = None
    away_penalties: int | None = None
    canceled: bool = False

    def involves(self, team_id: int) -> bool:
        return team_id in (self.home_id, self.away_id)

    def finished(self, now: datetime) -> bool:
        return self.home_goals is not None and self.kickoff + MATCH_LENGTH <= now


@dataclass(frozen=True)
class Competition:
    name: str
    games: list[Game]
    # Groups of the current points phase (rows already parsed); None in a knockout phase.
    groups: list[list[StandingRow]] | None = None
    phase: str | None = None  # the current phase's name, e.g. "Final"
    phase_kind: Literal["points", "groups", "knockout"] | None = None
