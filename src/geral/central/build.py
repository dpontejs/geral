"""Builds the Central snapshot from ge's tables (docs/features/central.md)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from geral.central.models import (
    CentralSnapshot,
    MatchView,
    SerieSummary,
    SerieView,
    TeamNextMatch,
    TieView,
)
from geral.collectors.base import create_http_client
from geral.general import SERIES
from geral.stats.combined import stats_client_for
from geral.stats.ge_models import Competition, Phase
from geral.stats.ge_tables import load_competition
from geral.teams import load_teams

logger = logging.getLogger(__name__)

NEXT_MATCHES_EVERY = timedelta(hours=1)  # ~100 ge/ESPN calls for six teams: not every 10 min
STRAGGLERS = 2  # unfinished games a round may leave behind (postponed) and still be past
SLUGS = {"Série A": "a", "Série B": "b", "Série C": "c", "Série D": "d"}
# Knockout phases whose winners go up (2026 rules: the B's playoffs; the D's quarter-final and
# playoff winners). Bands cover the rest. Check each season: the CBF changes formats.
PROMOTION_PHASES = {
    "Série B": ("Playoffs de acesso",),
    "Série D": ("Quartas de final", "Playoffs de acesso"),
}


def decide(tie: TieView) -> str | None:
    """Aggregate, then penalties; level without them goes to the 2nd-leg host (better campaign)."""
    if not tie.legs or any(m.status != "post" for m in tie.legs) or tie.home_agg is None:
        return None
    if len(tie.legs) < tie.expected_legs:  # a leg ge has not dated yet
        return None
    if tie.home_agg != tie.away_agg:
        return tie.home if tie.home_agg > tie.away_agg else tie.away
    last = tie.legs[-1]
    if last.home_penalties is not None and last.away_penalties is not None:
        if last.home_penalties != last.away_penalties:
            return last.home if last.home_penalties > last.away_penalties else last.away
    return last.home if len(tie.legs) == 2 else None


def serie_view(competition: Competition, slug: str, now: datetime) -> SerieView:
    phases = competition.phases
    current = competition.current if competition.current is not None else len(phases) - 1
    view = SerieView(name=competition.name, slug=slug, status="points")
    if not phases:
        return view
    phase = phases[current]
    view.phase = phase.name
    table_phase = next(
        (p for p in reversed(phases[: current + 1]) if p.kind == "points" and _single(p)), None
    )
    if table_phase:
        view.table, view.bands = table_phase.groups[0], table_phase.bands
        rounds: dict[int, list[MatchView]] = {}
        for game in sorted(competition.games, key=lambda g: g.kickoff):
            if game.phase == table_phase.name and game.round is not None:
                rounds.setdefault(game.round, []).append(MatchView.of(game, now))
        view.rounds = dict(sorted(rounds.items()))
        view.current_round = _current_round(view.rounds)
    if phase.kind == "groups":
        view.status, view.groups, view.group_bands = "groups", phase.groups or [], phase.bands
    elif phase.kind == "knockout":
        view.status = "knockout"
    view.ties = _ties(competition, phase.name, now) if phase.kind == "knockout" else []
    games = [g for g in competition.games if g.phase == phase.name]
    decided = all(t.winner for t in view.ties)
    if current == len(phases) - 1 and games and decided and all(g.finished(now) for g in games):
        view.status = "over"
        view.summary = _summary(competition, view, now)
    return view


def _current_round(rounds: dict[int, list[MatchView]]) -> int | None:
    """The first round still being played: one or two postponed games don't hold a round open."""
    open_rounds = [
        n
        for n, ms in rounds.items()
        if sum(m.status != "post" for m in ms) >= min(STRAGGLERS + 1, len(ms))
    ]
    if open_rounds:
        return min(open_rounds)
    left = [n for n, ms in rounds.items() if any(m.status != "post" for m in ms)]
    return max(left or rounds, default=None)


def _single(phase: Phase) -> bool:
    return bool(phase.groups) and len(phase.groups) == 1


def _ties(competition: Competition, phase: str, now: datetime) -> list[TieView]:
    legs: dict[str, list[MatchView]] = {}
    for game in competition.games:
        if game.phase == phase and game.tie:
            legs.setdefault(game.tie, []).append(MatchView.of(game, now))
    sizes = next((p.tie_legs for p in competition.phases if p.name == phase), {})
    ties = [TieView.of(name, ms) for name, ms in legs.items()]
    for tie in ties:
        tie.expected_legs = sizes.get(tie.name, 0)
        tie.winner = decide(tie)
    return ties


def _summary(competition: Competition, view: SerieView, now: datetime) -> SerieSummary:
    summary = SerieSummary()
    final = next((p for p in competition.phases if p.name.startswith("Final")), None)
    if final and final.kind == "knockout":
        ties = _ties(competition, final.name, now)
        if ties and ties[0].winner:
            summary.champion = ties[0].winner
            summary.runner_up = ties[0].away if ties[0].winner == ties[0].home else ties[0].home
    elif len(view.table) >= 2:
        summary.champion, summary.runner_up = view.table[0].team, view.table[1].team
    promoted: list[str] = []
    for phase in competition.phases:
        for group in phase.groups or []:
            promoted += [r.team for r in group if r.band and _goes_up(r.band)]
            summary.relegated += [
                r.team for r in group if r.band and r.band.startswith("Rebaixados")
            ]
    for phase in PROMOTION_PHASES.get(competition.name, ()):
        promoted += [t.winner for t in _ties(competition, phase, now) if t.winner]
    summary.promoted = list(dict.fromkeys(promoted))
    return summary


def _goes_up(band: str) -> bool:
    if band.startswith("Rebaixados") or "playoff" in band.lower():
        return False
    return "Acesso" in band or "Série " in band


def team_next_matches(now: datetime, tz: str = "America/Sao_Paulo") -> list[TeamNextMatch]:
    """The next match of every listed team; a team whose sources fail is left out."""
    found = []
    for team in load_teams().values():
        if not team.listed:
            continue
        try:
            match = stats_client_for(team, tz).get_next_match(now)
        except Exception as e:
            logger.warning("Central: next match of %s left out: %s", team.slug, e)
            continue
        if match:
            found.append(
                TeamNextMatch(
                    team_slug=team.slug,
                    team_name=team.name,
                    opponent=match.opponent,
                    kickoff=match.date,
                    competition=match.competition,
                    is_home=match.is_home,
                )
            )
    # Two of our teams playing each other: once, from the home side.
    shown: dict[tuple, TeamNextMatch] = {}
    for match in sorted(found, key=lambda m: (m.kickoff, not m.is_home)):
        key = (match.kickoff, frozenset((match.team_name, match.opponent)))
        if key in shown:
            shown[key].other_slug = match.team_slug
        else:
            shown[key] = match
    return list(shown.values())


def build_snapshot(
    now: datetime,
    previous: CentralSnapshot | None,
    client: httpx.Client | None = None,
    next_matches: Callable[[datetime], list[TeamNextMatch]] = team_next_matches,
    tz: ZoneInfo | None = None,
    series: dict[str, str] | None = None,
) -> CentralSnapshot:
    """Every série from ge; one that fails keeps its previous version. None at all is an error."""
    client = client or create_http_client()
    tz = tz or ZoneInfo("America/Sao_Paulo")
    old = {s.name: s for s in previous.series} if previous else {}
    views = []
    for name, page in (series if series is not None else SERIES).items():
        try:
            competition = load_competition(client, name, page, tz)
            if not competition.phases:  # e.g. ge switched the page to the tabela-context format
                raise ValueError("no phases on the page")
            views.append(serie_view(competition, SLUGS[name], now))
        except Exception as e:
            logger.warning("Central: %s not refreshed: %s", name, e)
            if name in old:
                views.append(old[name])
    if not views:
        raise RuntimeError("no série could be loaded")
    matches, fetched = (previous.next_matches, previous.next_matches_at) if previous else ([], None)
    if fetched is None or now - fetched >= NEXT_MATCHES_EVERY:
        try:
            matches, fetched = next_matches(now), now
        except Exception as e:
            logger.warning("Central: next matches not refreshed: %s", e)
    return CentralSnapshot(
        updated_at=now, series=views, next_matches=matches, next_matches_at=fetched
    )
