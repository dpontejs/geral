"""'Onde jogou?': name the clubs in the career of the player of the day.

Careers come from Wikidata (`scripts/import_carreiras.py` writes `carreiras.json` from the curated
`jogadores.toml`); `clubes.toml` fixes club names. No club is written in the code: a team's edition
is the players who played for the club whose name is the team's `name` in `teams.toml`.
"""

import json
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path

from pydantic import BaseModel

from geral.games.daily import number_on, pick, shuffled

HERE = Path(__file__).parent
CAREERS = HERE / "carreiras.json"
CLUB_FIXES = HERE / "clubes.toml"
PLAYERS = HERE / "jogadores.toml"
LAUNCH = date(2026, 11, 11)  # puzzle #1: no later than the deploy, or two days share #1
MAX_WRONG = 3
MIN_CLUBS = {"geral": 3, "team": 2}  # distinct clubs a career needs to be a puzzle
# National and youth teams are not clubs of a career.
# Whole words only: "Internazionale" is a club, not a "nazionale".
NOT_A_CLUB = re.compile(
    r"^sele[çc][ãa]o|\bselecci[óo]n\b|\bnational\b|\bnazionale\b|\b(sub|u)-?\d{2}\b|\bB$|"
    r"\bII$|\bjuvenil\b|\breserv|\bol[ií]mpic",
    re.IGNORECASE,
)
FIRST_YEAR = 1850  # Wikidata writes an unknown date as year 0001
# Positions as a Brazilian fan says them (Wikidata mixes English and Portugal's Portuguese).
POSITIONS = {
    "wing half": "Volante",
    "winger": "Ponta",
    "ponteiro": "Ponta",
    "defesa central": "Zagueiro",
    "defender": "Zagueiro",
    "attacking midfielder": "Meia",
    "midfielder": "Meio-campista",
    "forward": "Atacante",
    "goalkeeper": "Goleiro",
    "guarda-redes": "Goleiro",
}
# Country names as the fans look for them.
COUNTRY_NAMES = {"Reino Unido": "Inglaterra", "República Popular da China": "China"}


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def _year(value: str) -> int | None:
    year = int(value[:4]) if value and value[:4].isdigit() else None
    return year if year and year >= FIRST_YEAR else None


def convert(players: list[dict], rows: list[dict], fixes: dict[str, dict]) -> dict:
    """Wikidata rows (one per career statement) -> the compact careers file."""
    names = {p["wikidata"]: p["nome"] for p in players}
    # player -> (club, start) -> end; duplicate statements keep the known (latest) end.
    stints: dict[str, dict[tuple[str, int], int | None]] = {qid: {} for qid in names}
    positions: dict[str, str] = {}
    labels: dict[str, set[str]] = {}
    shown: dict[str, str] = {}
    countries: dict[str, str] = {}
    for r in rows:
        qid, club, label = r["player"], r["club"], r["clubLabel"].strip()
        if qid not in names:
            continue
        if r.get("position") and qid not in positions:
            position = re.sub(r"\s*\(.*\)$", "", r["position"]).strip()  # "Lateral (futebol)"
            position = POSITIONS.get(position.lower(), position)
            positions[qid] = position[:1].upper() + position[1:]
        start = _year(r["start"]) or _year(r["end"])  # unknown start: the end year at least
        ignored = fixes.get(club, {}).get("ignorar", False)  # e.g. a country listed as a club
        if r["national"] or ignored or NOT_A_CLUB.search(label) or start is None:
            continue
        end = _year(r["end"])
        if end is not None and end < start:  # swapped dates in the source
            start, end = end, start
        known = stints[qid].get((club, start))
        stints[qid][(club, start)] = (
            max(e for e in (known, end) if e is not None)
            if (known is not None or end is not None)
            else None
        )
        labels.setdefault(club, set()).update(x for x in (label, r.get("clubShort", "")) if x)
        shown.setdefault(club, r.get("clubShort") or label)
        if r.get("country"):
            countries.setdefault(club, COUNTRY_NAMES.get(r["country"], r["country"]))

    jogadores = []
    for qid, nome in names.items():
        merged: list[list] = []
        career = [(club, start, end) for (club, start), end in stints[qid].items()]
        for club, start, end in sorted(career, key=lambda s: (s[1], s[2] or 9999)):
            if merged and merged[-1][0] == club:  # back-to-back stints at the same club
                last = merged[-1][2]
                merged[-1][2] = None if last is None or end is None else max(last, end)
                continue
            merged.append([club, start, end])
        jogadores.append(
            {
                "wikidata": qid,
                "nome": nome,
                "posicao": positions.get(qid, ""),
                "clubes": [{"clube": c, "inicio": s, "fim": e} for c, s, e in merged],
            }
        )

    clubes = {}
    for club in sorted(labels):
        fix = fixes.get(club, {})
        nome = fix.get("nome") or shown[club]
        aliases = (labels[club] | set(fix.get("apelidos", []))) - {nome}
        pais = fix.get("pais") or countries.get(club) or "Outros"
        clubes[club] = {"nome": nome, "apelidos": sorted(aliases), "pais": pais}
    return {"clubes": clubes, "jogadores": jogadores}


@dataclass(frozen=True)
class Clube:
    nome: str
    apelidos: tuple[str, ...]
    pais: str = "Outros"


@dataclass(frozen=True)
class Passagem:
    clube: str
    inicio: int
    fim: int | None


@dataclass(frozen=True)
class Jogador:
    wikidata: str
    nome: str
    posicao: str
    clubes: tuple[Passagem, ...]

    @property
    def distintos(self) -> set[str]:
        return {s.clube for s in self.clubes}


@dataclass(frozen=True)
class Data:
    clubes: dict[str, Clube]
    jogadores: tuple[Jogador, ...]

    @classmethod
    def from_dict(cls, raw: dict) -> "Data":
        return cls(
            clubes={
                qid: Clube(c["nome"], tuple(c["apelidos"]), c.get("pais", "Outros"))
                for qid, c in raw["clubes"].items()
            },
            jogadores=tuple(
                Jogador(
                    j["wikidata"],
                    j["nome"],
                    j["posicao"],
                    tuple(Passagem(s["clube"], s["inicio"], s["fim"]) for s in j["clubes"]),
                )
                for j in raw["jogadores"]
            ),
        )

    @cached_property
    def index(self) -> dict[str, str]:
        """Every club name and alias, normalized -> club id (for what people type)."""
        found: dict[str, str] = {}
        for qid, club in sorted(self.clubes.items()):
            for name in (club.nome, *club.apelidos):
                found.setdefault(normalize(name), qid)
        return found


def load(path: Path = CAREERS) -> Data:
    return Data.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_fixes(path: Path = CLUB_FIXES) -> dict[str, dict]:
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def resolve(data: Data, text: str) -> str | None:
    return data.index.get(normalize(text))


def team_clubs(data: Data, name: str | None) -> set[str]:
    """The club ids of a team, by its `teams.toml` name (none for an unknown name)."""
    return {qid for qid, c in data.clubes.items() if name and c.nome == name}


def pool(
    data: Data, edition: str, teams: dict[str, str], game: str = "onde-jogou"
) -> list[Jogador]:
    """The edition's players in its fixed daily order; `teams` maps slug -> team name.

    `game` seeds the order, so two games on the same players don't fall on the same day.
    """
    if edition == "geral":
        chosen = [j for j in data.jogadores if len(j.distintos) >= MIN_CLUBS["geral"]]
    else:
        clubs = team_clubs(data, teams.get(edition))
        chosen = [
            j
            for j in data.jogadores
            if j.distintos & clubs and len(j.distintos) >= MIN_CLUBS["team"]
        ]
    chosen.sort(key=lambda j: j.wikidata)
    return shuffled(chosen, f"{game}:{edition}") if chosen else []


def puzzle_number(day: date) -> int:
    return number_on(day, LAUNCH)


def by_number(players: list[Jogador], number: int) -> Jogador:
    return pick(players, number)


class Slot(BaseModel):
    inicio: int
    fim: int | None
    clube: str | None  # shown once found, given, or when the game is over
    achado: bool
    dado: bool = False  # the edition's own team: shown from the start, not scored


class Verdict(BaseModel):
    slots: list[Slot]
    achados: int
    total: int
    erros: list[str]
    solved: bool
    over: bool


def judge(
    data: Data,
    jogador: Jogador,
    palpites: list[str],
    desistiu: bool,
    dados: set[str] | frozenset[str] = frozenset(),
) -> Verdict:
    """`dados`: clubs given away (the team of the edition), shown and left out of the score."""
    career = jogador.distintos - set(dados)
    guesses = [q for q in dict.fromkeys(palpites) if q not in dados]  # a repeat counts once
    found = {q for q in guesses if q in career}
    wrong = [q for q in guesses if q not in career]
    solved = found == career
    over = solved or len(wrong) >= MAX_WRONG or desistiu
    return Verdict(
        slots=[
            Slot(
                inicio=s.inicio,
                fim=s.fim,
                clube=(
                    data.clubes[s.clube].nome
                    if s.clube in found or s.clube in dados or over
                    else None
                ),
                achado=s.clube in found,
                dado=s.clube in dados,
            )
            for s in jogador.clubes
        ],
        achados=len(found),
        total=len(career),
        erros=[data.clubes[q].nome for q in wrong],
        solved=solved,
        over=over,
    )
