"""ge championship pages in the `tabela-context` format (e.g. the Pernambucano).

The page embeds a JSON (`<script id="tabela-context">`) with the edition, its phases and the
standings; knockout ties carry their matches. Points phases list their matches round by round in
ge's GraphQL API, with the same query the page uses (copied from it: introspection is off).
"""

import json
import logging
import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx

from geral.models import StandingRow
from geral.stats.ge_models import Competition, Game

logger = logging.getLogger(__name__)

GEQL_URL = "https://geql.globo.com/graphql"
CONTEXT = re.compile(r'<script id="tabela-context" type="application/json">(.*?)</script>', re.S)
KNOCKOUT = "2"
MAX_ROUNDS = 40

MATCH_FIELDS = """
  id
  startDate
  startHour
  moment
  canceled
  firstContestant { ... on Team { id popularName } }
  secondContestant { ... on Team { id popularName } }
  scoreboard { home away penalty { home away } }
  location { popularName }
"""
MATCHES_BY_PHASE = f"""
query GetMultisportMatchesByPhase(
  $multisportMatchesByPhaseFilter: MultisportMatchesByPhaseFilter!
) {{
  multisportMatchesByPhase(filter: $multisportMatchesByPhaseFilter) {{
    __typename
    ... on GroupedMultisportMatch {{ events {{ match {{ {MATCH_FIELDS} }} }} }}
    ... on MatchEventKind {{ match {{ {MATCH_FIELDS} }} }}
  }}
}}
"""


def read_context(html: str) -> dict | None:
    found = CONTEXT.search(html)
    if found is None:
        return None
    try:
        return json.loads(found.group(1))
    except ValueError:
        return None


def load(context: dict, name: str, client: httpx.Client, team_id: int, tz: ZoneInfo) -> Competition:
    standings = context["getStandingData"]["body"]["standings"]
    edition = standings["championshipEdition"]
    base_filter = {
        "championshipSlug": edition["championship"]["slug"],
        "championshipEditionSlug": edition["slug"],
        "sportSlug": standings["sport"]["slug"],
        "modalitySlug": standings["modality"]["slug"],
        "categorySlug": standings["category"]["slug"],
    }
    phases = standings["multisportStandings"]
    current = next((i for i, p in enumerate(phases) if p["phase"].get("actual")), None)
    if current is None:  # between stages: the last phase that already has teams or matches
        current = max((i for i, p in enumerate(phases) if _has_data(p)), default=0)
    games: dict[int, Game] = {}
    groups = None
    for index, phase in enumerate(phases):
        knockout = phase["phase"].get("typeID") == KNOCKOUT
        try:
            if knockout:
                matches = [
                    event["match"]
                    for standing in phase.get("standing") or []
                    for bracket in standing.get("brackets") or []
                    for event in bracket.get("events") or []
                    if event.get("match")
                ]
            else:
                total = max(
                    (s.get("totalRounds") or 0 for s in phase.get("standing") or []), default=0
                )
                filter_ = {**base_filter, "phaseSlug": phase["phase"]["slug"]}
                matches = _rounds(client, filter_, total)
        except Exception as e:
            if index <= current:
                raise
            logger.info("Skipping ge phase %s, not published yet: %s", phase["phase"]["slug"], e)
            continue
        if index == current and not knockout:
            groups = _groups(phase, team_id)
        for match in matches:
            try:
                game = _game(match, name, tz)
            except (KeyError, TypeError, ValueError) as e:  # e.g. a tie still without teams
                logger.info("Skipping ge match %s: %s", match.get("id"), e)
                continue
            if game is not None:
                games[game.id] = game
    return Competition(name=name, games=list(games.values()), groups=groups)


def _has_data(phase: dict) -> bool:
    for standing in phase.get("standing") or []:
        for rating in standing.get("ratings") or []:
            if ((rating.get("contestant") or {}).get("contestantData") or {}).get("id"):
                return True
        for bracket in standing.get("brackets") or []:
            if any((e.get("match") or {}).get("id") for e in bracket.get("events") or []):
                return True
    return False


def _rounds(client: httpx.Client, filter_: dict, total: int) -> list[dict]:
    """Rounds 1..`total` (the phase's round count) and on, until an empty one after it."""
    matches: list[dict] = []
    for n in range(1, MAX_ROUNDS + 1):
        response = client.post(
            GEQL_URL,
            json={
                "operationName": "GetMultisportMatchesByPhase",
                "query": MATCHES_BY_PHASE,
                "variables": {"multisportMatchesByPhaseFilter": {**filter_, "round": n}},
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise ValueError(f"ge GraphQL error: {body['errors'][0].get('message')}")
        found = []
        for item in body["data"]["multisportMatchesByPhase"] or []:
            if item.get("__typename") == "GroupedMultisportMatch":
                found += [e["match"] for e in item.get("events") or [] if e.get("match")]
            elif item.get("match"):
                found.append(item["match"])
        if not found and n > total:
            break
        matches += found
    return matches


def _game(match: dict, competition: str, tz: ZoneInfo) -> Game | None:
    day = match.get("startDate")
    if not day:
        return None
    hour = match.get("startHour")
    at = time.fromisoformat(hour) if hour else time(0, 0)
    home, away = match["firstContestant"], match["secondContestant"]
    if not int(match["id"]) or not all(side["id"] and side["popularName"] for side in (home, away)):
        raise ValueError("a tie still without both teams")
    score = match.get("scoreboard") or {}
    penalty = score.get("penalty") or {}
    pens = (penalty.get("home"), penalty.get("away"))
    return Game(
        id=int(match["id"]),
        competition=competition,
        kickoff=datetime.combine(date.fromisoformat(day[:10]), at, tzinfo=tz),
        time_valid=bool(hour),
        home=home["popularName"],
        away=away["popularName"],
        home_id=int(home["id"]),
        away_id=int(away["id"]),
        home_goals=score.get("home"),
        away_goals=score.get("away"),
        venue=(match.get("location") or {}).get("popularName"),
        # PAST without a score never started (put off); a score or a live moment did.
        started=score.get("home") is not None
        or match.get("moment") not in (None, "FUTURE", "PAST"),
        canceled=bool(match.get("canceled")),
        home_penalties=pens[0] if None not in pens else None,
        away_penalties=pens[1] if None not in pens else None,
    )


def _groups(phase: dict, team_id: int) -> list[list[StandingRow]] | None:
    try:
        return [
            [_standing(rating, team_id) for rating in standing["ratings"]]
            for standing in phase.get("standing") or []
            if standing.get("ratings")
        ]
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("Failed to parse ge table %s: %s", phase["phase"].get("slug"), e)
        return None


def _standing(rating: dict, team_id: int) -> StandingRow:
    columns = {c["slug"]: c["value"] for c in rating["standingColumns"]}
    team = rating["contestant"]["contestantData"]
    return StandingRow(
        position=int(rating["order"]),
        team=team["popularName"],
        points=int(columns["pontos"]),
        played=int(columns["jogos"]),
        won=int(columns["vitorias"]),
        drawn=int(columns["empates"]),
        lost=int(columns["derrotas"]),
        goals_diff=int(columns["saldo-de-gols"]),
        goals_for=int(columns.get("gols-pro") or 0),
        goals_against=int(columns.get("gols-contra") or 0),
        is_ours=int(team["id"]) == team_id,
    )
