"""What both ge table formats load into: the competition's matches and current table."""

from dataclasses import dataclass, field
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
    phase: str | None = None
    round: int | None = None  # points phases only
    tie: str | None = None  # knockout phases only: ge's `chave.nome`
    home_crest: str | None = None
    away_crest: str | None = None

    def involves(self, team_id: int) -> bool:
        return team_id in (self.home_id, self.away_id)

    def finished(self, now: datetime) -> bool:
        return self.home_goals is not None and self.kickoff + MATCH_LENGTH <= now


@dataclass(frozen=True)
class Phase:
    name: str
    kind: Literal["points", "groups", "knockout"] | None
    bands: list[str] = field(default_factory=list)  # ge's band names, in its order
    groups: list[list[StandingRow]] | None = None  # None in a knockout phase
    tie_legs: dict[str, int] = field(default_factory=dict)  # knockout: legs ge lists per tie


@dataclass(frozen=True)
class Competition:
    name: str
    games: list[Game]
    # Groups of the current points phase (rows already parsed); None in a knockout phase.
    groups: list[list[StandingRow]] | None = None
    phase: str | None = None  # the current phase's name, e.g. "Final"
    phase_kind: Literal["points", "groups", "knockout"] | None = None
    phases: list[Phase] = field(default_factory=list)  # every published phase, in order
    current: int | None = None  # index of the current phase in `phases`
