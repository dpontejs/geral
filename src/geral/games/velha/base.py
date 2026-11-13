"""The jogo da velha player base and its categories (club, Seleção, Copa, country, position).

`scripts/import_base.py` writes `base.json` from Wikidata and the English Wikipedia; the board
clubs are fixed by hand in `clubes.toml`. A cell holds any player who fits its row and column.
"""

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

HERE = Path(__file__).parent
BASE = HERE / "base.json"
CLUBS = HERE / "clubes.toml"

type Kind = Literal["clube", "selecao", "copa", "pais", "posicao"]
SELECAO, COPA = "selecao:BRA", "copa:FIFA"  # the kinds with a single value
POSITIONS = {
    "goleiro": "Goleiro",
    "zagueiro": "Zagueiro",
    "lateral": "Lateral",
    "meio-campo": "Meio-campo",
    "atacante": "Atacante",
}


@dataclass(frozen=True)
class Player:
    id: str  # Wikidata id
    nome: str
    anos: str  # "1985–2002", "2019–" or "" when unknown
    posicoes: tuple[str, ...]  # keys of POSITIONS
    paises: tuple[str, ...]  # country ids, Brazil left out
    fama: int  # number of Wikipedias
    clubes: frozenset[str]  # board club ids
    selecao: bool
    copa: bool


@dataclass(frozen=True)
class Category:
    kind: Kind
    value: str
    label: str

    @property
    def code(self) -> str:
        return f"{self.kind}:{self.value}"


@dataclass
class Base:
    players: dict[str, Player]
    clubs: dict[str, str]  # board club id -> name
    countries: dict[str, str]  # country id -> pt-BR name
    _members: dict[str, frozenset[str]] = field(default_factory=dict, repr=False)

    def players_in(self, cat: Category) -> frozenset[str]:
        if cat.code not in self._members:
            self._members[cat.code] = frozenset(
                p.id for p in self.players.values() if _belongs(p, cat)
            )
        return self._members[cat.code]


def _belongs(player: Player, cat: Category) -> bool:
    match cat.kind:
        case "clube":
            return cat.value in player.clubes
        case "selecao":
            return player.selecao
        case "copa":
            return player.copa
        case "pais":
            return cat.value in player.paises
        case "posicao":
            return cat.value in player.posicoes


def category(base: Base, code: str) -> Category:
    """'clube:Q5014111' -> the category; ValueError when the code names nothing on the board."""
    kind, _, value = code.partition(":")
    if code == SELECAO:
        return Category("selecao", "BRA", "Seleção Brasileira")
    if code == COPA:
        return Category("copa", "FIFA", "Jogou uma Copa")
    if kind == "clube" and value in base.clubs:
        return Category("clube", value, base.clubs[value])
    if kind == "pais" and value in base.countries:
        return Category("pais", value, base.countries[value])
    if kind == "posicao" and value in POSITIONS:
        return Category("posicao", value, POSITIONS[value])
    raise ValueError(f"unknown category: {code!r}")


def fits(base: Base, player_id: str, a: Category, b: Category) -> bool:
    return player_id in base.players_in(a) and player_id in base.players_in(b)


def answers(base: Base, a: Category, b: Category) -> list[Player]:
    """Every player of the cell, the most famous first."""
    found = (base.players[i] for i in base.players_in(a) & base.players_in(b))
    return sorted(found, key=lambda p: (-p.fama, p.nome, p.id))


def load_clubs(path: Path = CLUBS) -> dict[str, str]:
    return {qid: club["nome"] for qid, club in tomllib.loads(path.read_text("utf-8")).items()}


def load(path: Path = BASE, clubs: Path = CLUBS) -> Base:
    raw = json.loads(path.read_text(encoding="utf-8"))
    players = {
        p["id"]: Player(
            id=p["id"],
            nome=p["nome"],
            anos=p["anos"],
            posicoes=tuple(p["posicoes"]),
            paises=tuple(p["paises"]),
            fama=p["fama"],
            clubes=frozenset(p["clubes"]),
            selecao=p["selecao"],
            copa=p["copa"],
        )
        for p in raw["jogadores"]
    }
    return Base(players=players, clubs=load_clubs(clubs), countries=raw["paises"])
