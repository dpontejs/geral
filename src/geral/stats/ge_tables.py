"""Matches, results and tables from ge's table API, for competitions ESPN does not cover.

Série C, Série D and the state leagues (docs/features/dados-serie-c.md). Each run reads the
championship page for its `tUUID` and phases, then the API for every phase up to the current
one. Every public method degrades to None/[] like the ESPN client; only `get_fixtures` raises
`StatsUnavailable`, since an unknown calendar is not an empty one.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from geral.collectors.base import create_http_client
from geral.models import FormResult, MatchPreview, MatchStats, NextMatch, StandingRow, TeamMoment
from geral.schedule import Fixture
from geral.stats.espn import FIXTURES_LOOKBACK, FORM_SIZE, StatsUnavailable, standings_gap
from geral.teams import Team

logger = logging.getLogger(__name__)

GE_TABLES_API = "https://api.globoesporte.globo.com/tabela"
LEAGUE_PREFIX = "ge:"
MATCH_LENGTH = timedelta(hours=2, minutes=15)  # after this, a match with a score is over
MAX_ROUNDS = 40
POINTS, KNOCKOUT, GROUPS = "1", "2", "3"  # fase.tipo.tipo_id

TUUID = re.compile(r'tUUID:\s*"([0-9a-f-]{36})"')
PHASES = re.compile(r'"fases_navegacao":(\[[^\]]*\])')


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

    def involves(self, team_id: int) -> bool:
        return team_id in (self.home_id, self.away_id)

    def finished(self, now: datetime) -> bool:
        return self.home_goals is not None and self.kickoff + MATCH_LENGTH <= now


@dataclass(frozen=True)
class Competition:
    name: str
    games: list[Game]
    table: dict | None  # the current phase's classification, when it is a points phase


class GETablesClient:
    def __init__(
        self,
        team: Team,
        client: httpx.Client | None = None,
        tz_name: str = "America/Sao_Paulo",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if team.ge_id is None:
            raise ValueError(f"{team.slug} has no ge_id")
        self.team = team
        self.team_id = team.ge_id
        self.tz = ZoneInfo(tz_name)
        self._client = client or create_http_client()
        self._clock = clock or (lambda: datetime.now(self.tz))
        self._competitions: dict[str, Competition | None] = {}
        self.table_name: str | None = None

    # Public API (same shape as ESPNStatsClient)

    def get_fixtures(self, now: datetime) -> list[Fixture]:
        """Our matches in every ge competition from a week ago on; raises when one fails."""
        competitions = self._all()
        if any(c is None for c in competitions):
            raise StatsUnavailable("a ge competition could not be loaded")
        fixtures = [
            self._fixture(game, self._clock())  # the state is today's, like ESPN's
            for game in self._ours(competitions)
            if game.kickoff >= now - FIXTURES_LOOKBACK
        ]
        return sorted(fixtures, key=lambda f: f.kickoff)

    def get_last_match(self, start: datetime, end: datetime) -> MatchStats | None:
        now = self._clock()
        played = [
            g for g in self._ours(self._all()) if g.finished(now) and start <= g.kickoff <= end
        ]
        if not played:
            return None
        game = max(played, key=lambda g: g.kickoff)
        is_home = game.home_id == self.team_id
        return MatchStats(
            fixture_id=game.id,
            competition=game.competition,
            date=game.kickoff,
            home=game.home,
            away=game.away,
            home_goals=game.home_goals,
            away_goals=game.away_goals,
            venue=game.venue,
            is_home=is_home,
            # ge only publishes SVG crests, which Gmail does not show: ours comes from ESPN.
            home_logo=self.team.logo if is_home else None,
            away_logo=None if is_home else self.team.logo,
        )

    def get_next_match(self, now: datetime) -> NextMatch | None:
        upcoming = [g for g in self._ours(self._all()) if g.kickoff > now]
        if not upcoming:
            return None
        game = min(upcoming, key=lambda g: g.kickoff)
        is_home = game.home_id == self.team_id
        return NextMatch(
            opponent=game.away if is_home else game.home,
            competition=game.competition,
            date=game.kickoff,
            venue=game.venue,
            is_home=is_home,
            match_id=str(game.id),
        )

    def get_standings(self, league: str | None = None) -> list[StandingRow]:
        """Our group in the current points phase of the competition we played last."""
        if league is not None:
            if not league.startswith(LEAGUE_PREFIX):
                return []
            competition = self._competition(league.removeprefix(LEAGUE_PREFIX))
        else:
            competition = self._latest_competition()
        if competition is None or competition.table is None:
            return []
        table = competition.table
        groups = table.get("grupos") or [{"classificacao": table.get("classificacao", [])}]
        try:
            for group in groups:
                rows = [self._standing(entry) for entry in group["classificacao"]]
                if any(r.is_ours for r in rows):
                    self.table_name = competition.name
                    return sorted(rows, key=lambda r: r.position)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to parse ge table for %s: %s", competition.name, e)
        return []

    def get_moment(self, end: datetime, standings: list[StandingRow]) -> TeamMoment | None:
        form = self._form(self.team_id, end)
        standing = next((r for r in standings if r.is_ours), None)
        if not form and standing is None:
            return None
        return TeamMoment(
            form=form, standing=standing, gap=standings_gap(standings), league=self.table_name
        )

    def get_preview(self, match_id: str, league: str) -> MatchPreview | None:
        competition = self._competition(league.removeprefix(LEAGUE_PREFIX))
        if competition is None:
            return None
        game = next((g for g in competition.games if str(g.id) == match_id), None)
        if game is None or not game.involves(self.team_id):
            return None
        opponent_id = game.away_id if game.home_id == self.team_id else game.home_id
        before = game.kickoff - timedelta(minutes=1)
        now = self._clock()
        meetings = [
            g
            for g in self._games()
            if g.involves(self.team_id) and g.involves(opponent_id) and g.finished(now)
        ]
        return MatchPreview(
            opponent=game.away if game.home_id == self.team_id else game.home,
            team_form=self._form(self.team_id, before),
            opponent_form=self._form(opponent_id, before),
            head_to_head=[
                self._result(g, self.team_id)
                for g in sorted(meetings, key=lambda g: g.kickoff, reverse=True)
                if g.kickoff < game.kickoff
            ],
        )

    # Loading

    def _all(self) -> list[Competition | None]:
        return [self._competition(name) for name in self.team.ge_tables]

    def _games(self) -> list[Game]:
        unique = {g.id: g for c in self._all() if c for g in c.games}
        return list(unique.values())

    def _ours(self, competitions: list[Competition | None]) -> list[Game]:
        return [g for c in competitions if c for g in c.games if g.involves(self.team_id)]

    def _latest_competition(self) -> Competition | None:
        now = self._clock()
        played = [g for g in self._ours(self._all()) if g.finished(now)]
        if not played:
            return None
        return self._competition(max(played, key=lambda g: g.kickoff).competition)

    def _competition(self, name: str) -> Competition | None:
        if name not in self.team.ge_tables:
            return None
        if name not in self._competitions:
            try:
                self._competitions[name] = self._load(name, self.team.ge_tables[name])
            except Exception as e:
                logger.warning("Failed to load ge competition %s: %s", name, e)
                self._competitions[name] = None
        return self._competitions[name]

    def _load(self, name: str, page_url: str) -> Competition:
        page = self._client.get(page_url)
        page.raise_for_status()
        tuuid = TUUID.search(page.text)
        phases = PHASES.search(page.text)
        if tuuid is None or phases is None:
            raise ValueError(f"no tUUID or phases on {page_url}")
        navigation = json.loads(phases.group(1))
        current = next((i for i, p in enumerate(navigation) if p.get("atual")), len(navigation) - 1)

        games: dict[int, Game] = {}
        table = None
        for index, phase in enumerate(navigation[: current + 1]):
            base = f"{GE_TABLES_API}/{tuuid.group(1)}/fase/{phase['slug']}"
            data = self._json(f"{base}/classificacao/")
            kind = data["fase"]["tipo"]["tipo_id"]
            if kind == KNOCKOUT:
                raw = [g for s in data.get("secao", []) for c in s["chave"] for g in c["jogos"]]
            else:
                last = (data.get("rodada") or {}).get("ultima") if kind == POINTS else None
                raw = self._rounds(base, last)
                if index == current:
                    table = data
            for item in raw:
                try:
                    game = self._game(item, name)
                except (KeyError, TypeError, ValueError) as e:  # e.g. a knockout tie still TBD
                    logger.info("Skipping ge game %s: %s", item.get("id"), e)
                    continue
                if game is not None:
                    games[game.id] = game
        return Competition(name=name, games=list(games.values()), table=table)

    def _rounds(self, base: str, last: int | None) -> list[dict]:
        """Every round's games: 1..`last`, or up to the first empty round when unknown."""
        games: list[dict] = []
        for n in range(1, (last or MAX_ROUNDS) + 1):
            round_games = self._json(f"{base}/rodada/{n}/jogos/")
            if not round_games and last is None:
                break
            games += round_games
        return games

    def _json(self, url: str):
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    # Parsing

    def _game(self, item: dict, competition: str) -> Game | None:
        day = item.get("data_realizacao")
        if not day:
            return None  # not scheduled yet
        hour = item.get("hora_realizacao")
        at = time.fromisoformat(hour) if hour else time(0, 0)
        kickoff = datetime.combine(date.fromisoformat(day[:10]), at, tzinfo=self.tz)
        home, away = item["equipes"]["mandante"], item["equipes"]["visitante"]
        return Game(
            id=int(item["id"]),
            competition=competition,
            kickoff=kickoff,
            time_valid=bool(hour),
            home=home["nome_popular"],
            away=away["nome_popular"],
            home_id=int(home["id"]),
            away_id=int(away["id"]),
            home_goals=item.get("placar_oficial_mandante"),
            away_goals=item.get("placar_oficial_visitante"),
            venue=(item.get("sede") or {}).get("nome_popular"),
        )

    def _fixture(self, game: Game, now: datetime) -> Fixture:
        if game.kickoff > now:
            state = "pre"
        elif game.finished(now):
            state = "post"
        else:
            state = "in"
        return Fixture(
            match_id=str(game.id),
            league=f"{LEAGUE_PREFIX}{game.competition}",
            kickoff=game.kickoff,
            time_valid=game.time_valid,
            state=state,
            home=game.home,
            away=game.away,
        )

    def _form(self, team_id: int, until: datetime) -> list[FormResult]:
        now = self._clock()
        played = [
            g
            for g in self._games()
            if g.involves(team_id) and g.finished(now) and g.kickoff <= until
        ]
        played.sort(key=lambda g: g.kickoff, reverse=True)
        return [self._result(g, team_id) for g in played[:FORM_SIZE]]

    def _result(self, game: Game, team_id: int) -> FormResult:
        at_home = game.home_id == team_id
        goals_for, goals_against = (
            (game.home_goals, game.away_goals) if at_home else (game.away_goals, game.home_goals)
        )
        result = "V" if goals_for > goals_against else "D" if goals_for < goals_against else "E"
        return FormResult(
            result=result,
            opponent=game.away if at_home else game.home,
            score=f"{goals_for}-{goals_against}",
            competition=game.competition,
            date=game.kickoff,
        )

    def _standing(self, entry: dict) -> StandingRow:
        return StandingRow(
            position=int(entry["ordem"]),
            team=entry["nome_popular"],
            points=int(entry["pontos"]),
            played=int(entry["jogos"]),
            won=int(entry["vitorias"]),
            drawn=int(entry["empates"]),
            lost=int(entry["derrotas"]),
            goals_diff=int(entry["saldo_gols"]),
            goals_for=int(entry.get("gols_pro") or 0),
            goals_against=int(entry.get("gols_contra") or 0),
            is_ours=int(entry["equipe_id"]) == self.team_id,
        )
