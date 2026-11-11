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
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from geral.collectors.base import create_http_client
from geral.models import FormResult, MatchPreview, MatchStats, NextMatch, StandingRow, TeamMoment
from geral.schedule import Fixture
from geral.stats import ge_context
from geral.stats.cbf import CBFGoals
from geral.stats.espn import FIXTURES_LOOKBACK, FORM_SIZE, StatsUnavailable, standings_gap
from geral.stats.ge_models import Competition, Game
from geral.teams import Team

logger = logging.getLogger(__name__)

GE_TABLES_API = "https://api.globoesporte.globo.com/tabela"
LEAGUE_PREFIX = "ge:"
NO_SHOW = timedelta(hours=3)  # not started this long after kickoff, no score: postponed
MAX_ROUNDS = 40
POINTS, KNOCKOUT, GROUPS = "1", "2", "3"  # fase.tipo.tipo_id
PHASE_KINDS = {POINTS: "points", KNOCKOUT: "knockout", GROUPS: "groups"}

TUUID = re.compile(r'tUUID:\s*"([0-9a-f-]{36})"')
PHASES = re.compile(r'"fases_navegacao":(\[[^\]]*\])')


class GETablesClient:
    def __init__(
        self,
        team: Team,
        client: httpx.Client | None = None,
        tz_name: str = "America/Sao_Paulo",
        clock: Callable[[], datetime] | None = None,
        goals: CBFGoals | None = None,
    ) -> None:
        if team.ge_id is None:
            raise ValueError(f"{team.slug} has no ge_id")
        self.team = team
        self.team_id = team.ge_id
        self.tz = ZoneInfo(tz_name)
        self._client = client or create_http_client()
        self._clock = clock or (lambda: datetime.now(self.tz))
        self._goals = goals or CBFGoals(self._client)
        self._competitions: dict[str, Competition | None] = {}
        self._loader = CompetitionLoader(self._client, self.tz, self.team_id)
        self.table_name: str | None = None

    # Public API (same shape as ESPNStatsClient)

    def get_fixtures(self, now: datetime) -> list[Fixture]:
        """Our matches in every ge competition from a week ago on; raises when one fails.

        Any error is StatsUnavailable: `due --all` must go on with the other teams.
        """
        competitions = self._all()
        if any(c is None for c in competitions):
            raise StatsUnavailable("a ge competition could not be loaded")
        try:
            fixtures = [
                self._fixture(game, self._clock())  # the state is today's, like ESPN's
                for game in self._ours(competitions)
                if game.kickoff >= now - FIXTURES_LOOKBACK
            ]
        except Exception as e:
            raise StatsUnavailable(f"ge fixtures could not be built: {e}") from e
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
        ours, theirs = (game.home, game.away) if is_home else (game.away, game.home)
        cbf_path = self.team.cbf_tables.get(game.competition)
        events = (
            self._goals.goals(cbf_path, game.kickoff.date(), self.team.cbf_id, ours, theirs)
            if cbf_path and self.team.cbf_id
            else []
        )
        return MatchStats(
            fixture_id=game.id,
            competition=game.competition,
            date=game.kickoff,
            home=game.home,
            away=game.away,
            home_goals=game.home_goals,
            away_goals=game.away_goals,
            home_penalties=game.home_penalties,
            away_penalties=game.away_penalties,
            venue=game.venue,
            is_home=is_home,
            events=events,
            # ge only publishes SVG crests, which Gmail does not show: ours comes from ESPN.
            home_logo=self.team.logo if is_home else None,
            away_logo=None if is_home else self.team.logo,
        )

    def get_next_match(self, now: datetime) -> NextMatch | None:
        # A match without kickoff time (00:00) is still the next one all through its day.
        upcoming = [
            g
            for g in self._ours(self._all())
            if g.kickoff > now
            or (not g.time_valid and g.kickoff.date() == now.date() and not g.finished(now))
        ]
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
            # No kickoff time, no deadline for the bets: the bolão stays closed.
            match_id=str(game.id) if game.time_valid else None,
        )

    def get_standings(self, league: str | None = None) -> list[StandingRow]:
        """Our group in the current points phase of the competition we played last."""
        if league is not None:
            if not league.startswith(LEAGUE_PREFIX):
                return []
            competition = self._competition(league.removeprefix(LEAGUE_PREFIX))
        else:
            competition = self._latest_competition()
        if competition is None or not competition.groups:
            return []
        for rows in competition.groups:
            if any(r.is_ours for r in rows):
                self.table_name = competition.name
                return sorted(rows, key=lambda r: r.position)
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
                self._competitions[name] = self._loader.load(name, self.team.ge_tables[name])
            except Exception as e:
                logger.warning("Failed to load ge competition %s: %s", name, e)
                self._competitions[name] = None
        return self._competitions[name]

    # Parsing

    def _fixture(self, game: Game, now: datetime) -> Fixture:
        # ge has no "postponed": a match that never started hours after its time was put off.
        no_show = game.kickoff + NO_SHOW + (timedelta() if game.time_valid else timedelta(days=1))
        if game.canceled:
            state = "postponed"
        elif game.kickoff > now:
            state = "pre"
        elif game.finished(now):
            state = "post"
        elif game.started:
            state = "in"
        elif game.home_goals is None and now >= no_show:
            state = "postponed"
        else:
            state = "pre"
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
        score = f"{goals_for}-{goals_against}"
        if game.home_penalties is not None and game.away_penalties is not None:
            pens = (game.home_penalties, game.away_penalties)
            pens_for, pens_against = pens if at_home else pens[::-1]
            score += f" ({pens_for}-{pens_against} pên.)"
        return FormResult(
            result=result,
            opponent=game.away if at_home else game.home,
            score=score,
            competition=game.competition,
            date=game.kickoff,
        )


def load_competition(
    client: httpx.Client, name: str, page_url: str, tz: ZoneInfo, team_id: int | None = None
) -> Competition:
    """A ge championship (either page format): its matches and current table, for any reader."""
    return CompetitionLoader(client, tz, team_id).load(name, page_url)


class CompetitionLoader:
    """Reads a championship page and ge's APIs into a Competition; `team_id` marks our rows."""

    def __init__(self, client: httpx.Client, tz: ZoneInfo, team_id: int | None = None) -> None:
        self._client = client
        self.tz = tz
        self.team_id = team_id

    def load(self, name: str, page_url: str) -> Competition:
        page = self._client.get(page_url)
        page.raise_for_status()
        tuuid = TUUID.search(page.text)
        phases = PHASES.search(page.text)
        if tuuid is None or phases is None:
            context = ge_context.read_context(page.text)
            if context is None:
                raise ValueError(f"no tUUID, phases or tabela-context on {page_url}")
            return ge_context.load(context, name, self._client, self.team_id, self.tz)
        navigation = json.loads(phases.group(1))
        current = next((i for i, p in enumerate(navigation) if p.get("atual")), len(navigation) - 1)

        games: dict[int, Game] = {}
        groups = None
        phase_kind = None
        # Later phases too: their first matches must be planned before ge makes them current.
        for index, phase in enumerate(navigation):
            base = f"{GE_TABLES_API}/{tuuid.group(1)}/fase/{phase['slug']}"
            try:
                data, raw = self._phase(base)
            except Exception as e:
                if index <= current:
                    raise
                logger.info("Skipping ge phase %s, not published yet: %s", phase["slug"], e)
                continue
            if index == current:
                phase_kind = PHASE_KINDS.get(data["fase"]["tipo"]["tipo_id"])
                if phase_kind != "knockout":
                    groups = self._groups(data, name)
            for item in raw:
                try:
                    game = self._game(item, name)
                except (KeyError, TypeError, ValueError) as e:  # e.g. a knockout tie still TBD
                    logger.info("Skipping ge game %s: %s", item.get("id"), e)
                    continue
                if game is not None:
                    games[game.id] = game
        return Competition(
            name=name,
            games=list(games.values()),
            groups=groups,
            phase=navigation[current].get("nome") if navigation else None,
            phase_kind=phase_kind,
        )

    def _groups(self, data: dict, name: str) -> list[list[StandingRow]] | None:
        groups = data.get("grupos") or [{"classificacao": data.get("classificacao", [])}]
        try:
            return [[self._standing(entry) for entry in g["classificacao"]] for g in groups]
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Failed to parse ge table for %s: %s", name, e)
            return None

    def _phase(self, base: str) -> tuple[dict, list[dict]]:
        """The phase's classification and its games, from the knockout ties or the rounds."""
        data = self._json(f"{base}/classificacao/")
        kind = data["fase"]["tipo"]["tipo_id"]
        if kind == KNOCKOUT:
            return data, [g for s in data.get("secao", []) for c in s["chave"] for g in c["jogos"]]
        last = (data.get("rodada") or {}).get("ultima") if kind == POINTS else None
        return data, self._rounds(base, last or 0)

    def _rounds(self, base: str, last: int) -> list[dict]:
        """Rounds 1..`last` and on, until the first empty one after it.

        `rodada.ultima` may be the last round published, not the last of the phase.
        """
        games: list[dict] = []
        for n in range(1, MAX_ROUNDS + 1):
            round_games = self._json(f"{base}/rodada/{n}/jogos/")
            if not round_games and n > last:
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
        pens = (item.get("placar_penaltis_mandante"), item.get("placar_penaltis_visitante"))
        if not (isinstance(home["nome_popular"], str) and isinstance(away["nome_popular"], str)):
            raise ValueError("a side without name")
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
            started=bool(item.get("jogo_ja_comecou")),
            # Both sides or none: a half shoot-out would print "3 x None".
            home_penalties=pens[0] if None not in pens else None,
            away_penalties=pens[1] if None not in pens else None,
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
