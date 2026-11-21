"""What the Central page reads: one snapshot of the four séries, saved as JSON."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from geral.models import StandingRow
from geral.stats.ge_models import Game


class MatchView(BaseModel):
    home: str
    away: str
    home_crest: str | None = None
    away_crest: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None
    kickoff: datetime
    time_valid: bool = True  # False: the day is set, the time is not
    status: Literal["pre", "live", "post"] = "pre"
    venue: str | None = None

    @classmethod
    def of(cls, game: Game, now: datetime) -> "MatchView":
        if game.finished(now):
            status = "post"
        elif game.started or game.home_goals is not None:
            status = "live"
        else:
            status = "pre"
        return cls(
            home=game.home,
            away=game.away,
            home_crest=game.home_crest,
            away_crest=game.away_crest,
            home_goals=game.home_goals,
            away_goals=game.away_goals,
            home_penalties=game.home_penalties,
            away_penalties=game.away_penalties,
            kickoff=game.kickoff,
            time_valid=game.time_valid,
            status=status,
            venue=game.venue,
        )


class TieView(BaseModel):
    name: str
    home: str  # the first leg's host
    away: str
    legs: list[MatchView]
    home_agg: int | None = None  # None until a leg has a score
    away_agg: int | None = None
    winner: str | None = None
    expected_legs: int = 0  # legs ge lists for the tie, dated or not (0: unknown)

    @classmethod
    def of(cls, name: str, legs: list[MatchView]) -> "TieView":
        legs = sorted(legs, key=lambda m: m.kickoff)
        home, away = legs[0].home, legs[0].away
        scored = [m for m in legs if m.home_goals is not None and m.away_goals is not None]
        tie = cls(name=name, home=home, away=away, legs=legs)
        if scored:
            tie.home_agg = sum(m.home_goals if m.home == home else m.away_goals for m in scored)
            tie.away_agg = sum(m.away_goals if m.home == home else m.home_goals for m in scored)
        return tie


class SerieSummary(BaseModel):
    champion: str | None = None
    runner_up: str | None = None
    promoted: list[str] = []
    relegated: list[str] = []


class SerieView(BaseModel):
    name: str  # "Série A"
    slug: Literal["a", "b", "c", "d"]
    status: Literal["points", "groups", "knockout", "over"]
    phase: str | None = None  # the current phase's name
    table: list[StandingRow] = []  # the last single-table points phase
    bands: list[str] = []  # the table's bands, in ge's order
    groups: list[list[StandingRow]] = []  # a current group phase
    group_bands: list[str] = []
    rounds: dict[int, list[MatchView]] = {}  # the table's phase, by round
    current_round: int | None = None
    ties: list[TieView] = []  # the current knockout phase
    summary: SerieSummary | None = None  # only when the série is over


class TeamNextMatch(BaseModel):
    team_slug: str
    team_name: str
    opponent: str
    other_slug: str | None = None  # the opponent is one of ours too (a derby, shown once)
    kickoff: datetime
    competition: str
    is_home: bool = True


class CentralSnapshot(BaseModel):
    updated_at: datetime
    series: list[SerieView]
    next_matches: list[TeamNextMatch] = []
    next_matches_at: datetime | None = None  # fetched hourly, not on every refresh
