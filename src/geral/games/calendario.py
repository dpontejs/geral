"""The daily answers already played, frozen so a data update never rewrites them.

Each daily order is a shuffle of the edition's players: adding or fixing one player reshuffles the
whole order, which would change today's puzzle mid-day and every past number (the archive). Before
the careers change, `scripts/congelar_calendario.py` writes the answers up to the next day here;
those numbers keep their answer, and only later numbers follow the new order.
"""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from geral.games.daily import pick as order_pick

if TYPE_CHECKING:
    from geral.games.onde_jogou import Data

CALENDAR = Path(__file__).with_name("calendario.json")

type Calendar = dict[str, dict[str, list[str]]]


def load(path: Path = CALENDAR) -> Calendar:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def answers(calendar: Calendar, game: str, edition: str) -> list[str]:
    return calendar.get(game, {}).get(edition, [])


def pick[T](order: Sequence[T], number: int, frozen: Sequence[str], key: Callable[[T], str]) -> T:
    """The frozen answer of `number` while it is still in the pool, else the daily order's."""
    if 1 <= number <= len(frozen):
        found = next((item for item in order if key(item) == frozen[number - 1]), None)
        if found is not None:
            return found
    return order_pick(list(order), number)


def freeze(path: Path, game: str, edition: str, ids: list[str]) -> None:
    """Record answers #1..#len(ids); numbers already frozen keep theirs."""
    calendar = load(path)
    known = calendar.setdefault(game, {}).setdefault(edition, [])
    known.extend(ids[len(known) :])
    path.write_text(json.dumps(calendar, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def freeze_games(path: Path, data: "Data", teams: dict[str, str], until: int) -> None:
    """Freeze #1..#until of every careers game and edition, with the careers in `data`.

    `teams` maps each listed team slug to its `teams.toml` name, as the site uses them.
    """
    from geral.games import onde_jogou, quem_e  # careers games; imported here to avoid a cycle

    for game, pool in (("onde-jogou", onde_jogou.pool), ("quem-e", quem_e.pool)):
        for edition in ("geral", *teams):
            players = pool(data, edition, teams)
            if not players:
                continue
            known = answers(load(path), game, edition)
            ids = [
                pick(players, n, known, key=lambda j: j.wikidata).wikidata
                for n in range(1, until + 1)
            ]
            freeze(path, game, edition, ids)
