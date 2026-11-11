"""The week of each série: results, table and news, all from ge."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from geral.collectors.base import create_http_client
from geral.collectors.ge import GECollector
from geral.general import SERIES
from geral.models import Article, StandingRow
from geral.stats.ge_models import MATCH_LENGTH, Game
from geral.stats.ge_tables import load_competition

logger = logging.getLogger(__name__)

MAX_NEWS = 8
FEED_PAGES = 12  # a série's feed is busy: three pages are about two days of the Série A
EDGE = 4  # rows on each end of a long table (G4, Z4)
WHOLE_TABLE = 10  # up to this, the whole table


@dataclass
class SerieWeek:
    name: str
    results: list[Game] = field(default_factory=list)  # matches over by the edition, oldest first
    table_top: list[StandingRow] = field(default_factory=list)
    table_bottom: list[StandingRow] = field(default_factory=list)
    phase: str | None = None  # current phase name when it is not a single points table
    news: list[Article] = field(default_factory=list)  # newest first


def cut_table(rows: list[StandingRow]) -> tuple[list[StandingRow], list[StandingRow]]:
    ordered = sorted(rows, key=lambda r: r.position)
    if len(ordered) <= WHOLE_TABLE:
        return ordered, []
    return ordered[:EDGE], ordered[-EDGE:]


def collect_week(
    start: datetime,
    end: datetime,
    series: dict[str, str] | None = None,
    client: httpx.Client | None = None,
    tz: ZoneInfo | None = None,
) -> list[SerieWeek]:
    """Séries with a result or a story in [start, end); a série that fails is left out.

    Raises RuntimeError when every série failed: the edition would be empty for a bad reason.
    """
    series = series if series is not None else SERIES
    client = client or create_http_client()
    tz = tz or ZoneInfo("America/Sao_Paulo")
    weeks, failed = [], 0
    for name, page in series.items():
        try:
            week = _serie_week(name, page, start, end, client, tz)
        except Exception as e:
            logger.warning("Edição geral: %s left out: %s", name, e)
            failed += 1
            continue
        if week.results or week.news:
            weeks.append(week)
    if series and failed == len(series):
        raise RuntimeError("no série could be loaded")
    return weeks


def _serie_week(
    name: str, page: str, start: datetime, end: datetime, client: httpx.Client, tz: ZoneInfo
) -> SerieWeek:
    competition = load_competition(client, name, page, tz)
    results = sorted(
        (g for g in competition.games if _over_in(g, start, end)), key=lambda g: g.kickoff
    )
    week = SerieWeek(name=name, results=results)
    if competition.phase_kind == "points" and competition.groups and len(competition.groups) == 1:
        week.table_top, week.table_bottom = cut_table(competition.groups[0])
    else:
        week.phase = competition.phase
    news = GECollector(url=page, client=client, tz_name=str(tz), max_pages=FEED_PAGES).collect(
        start, end
    )
    news = [a for a in news if start <= a.published_at < end]
    week.news = sorted(news, key=lambda a: a.published_at, reverse=True)[:MAX_NEWS]
    return week


def _over_in(game: Game, start: datetime, end: datetime) -> bool:
    return (
        game.home_goals is not None
        and game.away_goals is not None
        and start <= game.kickoff < end
        and game.kickoff + MATCH_LENGTH <= end
    )
