"""ESPN plus ge's tables: one stats client for teams in competitions ESPN does not cover."""

import logging
from datetime import datetime

from geral.models import MatchPreview, MatchStats, NextMatch, StandingRow, TeamMoment
from geral.schedule import Fixture
from geral.stats.espn import FORM_SIZE, ESPNStatsClient, StatsUnavailable
from geral.stats.ge_tables import LEAGUE_PREFIX, GETablesClient
from geral.teams import Team

logger = logging.getLogger(__name__)


def stats_client_for(team: Team, tz_name: str = "America/Sao_Paulo"):
    """ESPN alone, or ESPN and ge together when the team follows competitions on ge."""
    espn = ESPNStatsClient(team, tz_name=tz_name)
    if not team.ge_tables:
        return espn
    return CombinedStatsClient(espn, GETablesClient(team, tz_name=tz_name), team)


class CombinedStatsClient:
    """Same API as ESPNStatsClient; ge matches carry a `ge:` league."""

    def __init__(self, espn, ge, team: Team | None = None) -> None:
        self.espn = espn
        self.ge = ge
        self.team = team

    @property
    def _espn_table(self) -> bool:
        return bool(self.team and self.team.league)

    @property
    def table_name(self) -> str | None:
        return self.team.league_name if self._espn_table else self.ge.table_name

    def get_fixtures(self, now: datetime) -> list[Fixture]:
        """Both calendars. ESPN unknown makes it unknown; ge unknown too, unless the team's main
        league is on ESPN (a state league on ge must not stop the Série B editions)."""
        fixtures = self.espn.get_fixtures(now)
        try:
            fixtures += self.ge.get_fixtures(now)
        except StatsUnavailable as e:
            if not self._espn_table:
                raise
            logger.warning("ge calendar unavailable, going on with ESPN's: %s", e)
        return sorted(fixtures, key=lambda f: f.kickoff)

    def get_last_match(self, start: datetime, end: datetime) -> MatchStats | None:
        played = [
            m
            for m in (self.espn.get_last_match(start, end), self.ge.get_last_match(start, end))
            if m
        ]
        return max(played, key=lambda m: m.date, default=None)

    def get_next_match(self, now: datetime) -> NextMatch | None:
        upcoming = [m for m in (self.espn.get_next_match(now), self.ge.get_next_match(now)) if m]
        return min(upcoming, key=lambda m: m.date, default=None)

    def get_standings(self, league: str | None = None) -> list[StandingRow]:
        if league is not None:
            source = self.ge if league.startswith(LEAGUE_PREFIX) else self.espn
            return source.get_standings(league)
        return self.espn.get_standings() if self._espn_table else self.ge.get_standings()

    def get_moment(self, end: datetime, standings: list[StandingRow]) -> TeamMoment | None:
        moments = [
            m
            for m in (self.espn.get_moment(end, standings), self.ge.get_moment(end, standings))
            if m
        ]
        if not moments:
            return None
        form = sorted((f for m in moments for f in m.form), key=lambda f: f.date, reverse=True)
        standing = next((r for r in standings if r.is_ours), None)
        return TeamMoment(
            form=form[:FORM_SIZE],
            standing=standing,
            gap=next((m.gap for m in moments if m.gap), None),
            rankings=[r for m in moments for r in m.rankings],
            league=self.table_name or next((m.league for m in moments if m.league), None),
        )

    def get_preview(self, match_id: str, league: str) -> MatchPreview | None:
        source = self.ge if league.startswith(LEAGUE_PREFIX) else self.espn
        return source.get_preview(match_id, league)
