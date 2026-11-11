"""Goal scorers of national competitions (Série C, Série D) from the CBF site.

The championship page carries the competition id and its phases; the site's own API lists every
round's games with their goals (`penalidades`). Only the post-game needs it, once per match.
Any failure is an empty list: the edition keeps the score without the scorers.
"""

import logging
import re
from datetime import date, datetime, timedelta

import httpx

from geral.collectors.base import create_http_client
from geral.models import MatchEvent

logger = logging.getLogger(__name__)

CBF_PAGE_URL = "https://www.cbf.com.br/futebol-brasileiro/tabelas/{path}/{year}"
CBF_GAMES_URL = (
    "https://www.cbf.com.br/api/cbf/jogos/campeonato/{competition}/rodada/{round}/fase/{phase}"
)
GOAL_DETAILS = {"PN": "Pênalti", "FT": "Falta", "CT": "Contra"}
HALF_START = {"1": 0, "2": 45, "3": 90, "4": 105}  # extra time halves are 15 minutes
HALF_LENGTH = {"1": 45, "2": 45, "3": 15, "4": 15}
# A round all older than the match by this much ends the phase's search; closer than that,
# a postponed match may still sit in an earlier round.
POSTPONED_SLACK = timedelta(days=45)

COMPETITION = re.compile(r'competitionId\\?"\s*:\s*\\?"(\d+)')
PHASE = re.compile(r'fase_id\\?"\s*:\s*\\?"(\d+)\\?",\s*\\?"fase_nome\\?"\s*:\s*\\?"[^"\\]*\\?",'
                   r'\s*\\?"rodadas_qtd\\?"\s*:\s*\\?"(\d+)')  # fmt: skip


class CBFGoals:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or create_http_client()

    def goals(self, path: str, day: date, team_id: int, ours: str, theirs: str) -> list[MatchEvent]:
        """Goals of our match on `day` in the competition at `path` (e.g. "…/serie-c")."""
        try:
            page = self._client.get(CBF_PAGE_URL.format(path=path, year=day.year))
            page.raise_for_status()
            competition = COMPETITION.search(page.text)
            phases = sorted({int(p): int(n) for p, n in PHASE.findall(page.text)}.items())
            if competition is None or not phases:
                raise ValueError("no competition id or phases on the CBF page")
            game = self._find(competition.group(1), phases, day, team_id)
            if game is None:
                return []
            events = [
                _goal(p, team_id=team_id, ours=ours, theirs=theirs)
                for p in game.get("penalidades") or []
                if p.get("tipo") == "GOL"
            ]
            return sorted((e for e in events if e), key=lambda e: (e.minute, e.extra_minute or 0))
        except Exception as e:
            logger.warning("Failed to load CBF goals for %s on %s: %s", path, day, e)
            return []

    def _find(
        self, competition: str, phases: list[tuple[int, int]], day: date, team_id: int
    ) -> dict | None:
        """Our game on `day`, searching from the last round backwards."""
        for phase, rounds in reversed(phases):
            for n in range(rounds, 0, -1):
                games = self._round(competition, phase, n)
                days = [d for d in map(_day, games) if d]
                for game in games:
                    sides = (game["mandante"]["id"], game["visitante"]["id"])
                    if str(team_id) in sides and _day(game) == day:
                        return game
                if days and max(days) < day - POSTPONED_SLACK:
                    break  # earlier rounds are older still; phases may overlap, so go on
        return None

    def _round(self, competition: str, phase: int, n: int) -> list[dict]:
        """The round's games; a failing or empty round (the API answers `[]`) has none."""
        url = CBF_GAMES_URL.format(competition=competition, round=n, phase=phase)
        try:
            response = self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.info("Skipping CBF round %s of phase %s: %s", n, phase, e)
            return []
        if not isinstance(data, dict):
            return []
        return [g for group in data.get("jogos") or [] for g in group.get("jogo") or []]


def _day(game: dict) -> date | None:
    try:
        return datetime.strptime(game.get("data", "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _goal(entry: dict, team_id: int, ours: str, theirs: str) -> MatchEvent | None:
    half = str(entry.get("tempo_jogo", "")).strip()
    match = re.match(r"(\d+):", str(entry.get("minutos", "")))
    if half not in HALF_START or match is None:
        return None
    played = int(match.group(1))
    extra = played - HALF_LENGTH[half] if played > HALF_LENGTH[half] else None
    minute = HALF_START[half] + min(played, HALF_LENGTH[half])
    scorer_is_ours = str(entry.get("clube_id")) == str(team_id)
    own_goal = entry.get("resultado") == "CT"
    return MatchEvent(
        minute=minute,
        extra_minute=extra,
        team=ours if scorer_is_ours != own_goal else theirs,
        player=entry.get("atleta_apelido") or entry.get("atleta_nome") or "?",
        type="goal",
        detail=GOAL_DETAILS.get(entry.get("resultado", "")),
    )
