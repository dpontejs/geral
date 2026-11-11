"""'Craque do dia': a Wordle of each fanbase's idols, one nickname per day and edition.

The answers are curated by hand in `craques/<team slug>.toml` (no club names in the code). The
"geral" edition mixes every list.
"""

import re
import tomllib
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from geral.games.daily import number_on, pick, shuffled

CRAQUES = Path(__file__).with_name("craques")
LAUNCH = date(2026, 11, 11)  # puzzle #1: no later than the deploy, or two days share #1
MAX_GUESSES = 6
POSITION_HINT_AFTER, ERA_HINT_AFTER = 3, 4  # misses
MIN_LETTERS, MAX_LETTERS = 3, 10
MIN_LIST = (
    30  # a team gets its own edition with a month of puzzles; smaller lists only feed "geral"
)
FIELDS = ("nome", "completo", "posicao", "epoca", "fato")
LETTERS = re.compile(r"[A-Z]+")


def normalize(text: str) -> str:
    """'Nenê' -> 'NENE': upper case, accents dropped (other symbols kept, so they fail later)."""
    plain = unicodedata.normalize("NFKD", text.strip())
    return "".join(ch for ch in plain if not unicodedata.combining(ch)).upper()


@dataclass(frozen=True)
class Craque:
    team: str
    nome: str
    completo: str
    posicao: str
    epoca: str
    fato: str

    @property
    def answer(self) -> str:
        return normalize(self.nome)


def _read(path: Path) -> list[Craque]:
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("craque", [])
    craques = []
    for entry in entries:
        missing = [f for f in FIELDS if not str(entry.get(f, "")).strip()]
        word = normalize(str(entry.get("nome", "")))
        if missing or not LETTERS.fullmatch(word) or not MIN_LETTERS <= len(word) <= MAX_LETTERS:
            raise ValueError(
                f"{path.name}: {entry.get('nome')!r} needs one word of {MIN_LETTERS}-{MAX_LETTERS}"
                f" letters and every field ({', '.join(FIELDS)}); missing: {missing}"
            )
        craques.append(Craque(team=path.stem, **{f: entry[f].strip() for f in FIELDS}))
    return craques


def load_lists(directory: Path = CRAQUES) -> dict[str, list[Craque]]:
    """Team slug -> its curated list, from every `<slug>.toml` in `directory`."""
    return {path.stem: _read(path) for path in sorted(directory.glob("*.toml"))}


def pool(lists: dict[str, list[Craque]], edition: str, min_list: int = MIN_LIST) -> list[Craque]:
    """The edition's craques in its fixed daily order; 'geral' mixes all, one per name.

    A team list shorter than `min_list` is still a draft: no edition of its own yet.
    """
    if edition == "geral":
        unique = {}
        for slug in sorted(lists):
            for craque in lists[slug]:
                unique.setdefault(craque.answer, craque)
        chosen = [unique[name] for name in sorted(unique)]
    else:
        team = lists.get(edition, [])
        chosen = sorted(team, key=lambda c: c.answer) if len(team) >= min_list else []
    return shuffled(chosen, f"craque:{edition}") if chosen else []


def puzzle_number(day: date) -> int:
    return number_on(day, LAUNCH)


def by_number(craques: list[Craque], number: int) -> Craque:
    return pick(craques, number)


def valid_guess(craque: Craque, guess: str) -> bool:
    word = normalize(guess)
    return bool(LETTERS.fullmatch(word)) and len(word) == len(craque.answer)


Mark = Literal["certo", "existe", "nao"]


class Reveal(BaseModel):
    nome: str
    completo: str
    posicao: str
    epoca: str
    fato: str


class Verdict(BaseModel):
    rows: list[list[Mark]]
    solved: bool
    over: bool
    hints: list[str]
    reveal: Reveal | None


def _marks(answer: str, guess: str) -> list[Mark]:
    """Wordle rules: exact letters first, then each remaining letter of the answer marks once."""
    marks: list[Mark] = ["nao"] * len(answer)
    left = Counter(a for a, g in zip(answer, guess, strict=True) if a != g)
    for i, (a, g) in enumerate(zip(answer, guess, strict=True)):
        if a == g:
            marks[i] = "certo"
        elif left[g] > 0:
            marks[i] = "existe"
            left[g] -= 1
    return marks


def judge(craque: Craque, guesses: list[str]) -> Verdict:
    words = [normalize(g) for g in guesses]
    solved = craque.answer in words
    over = solved or len(words) >= MAX_GUESSES
    misses = len(words) - (1 if solved else 0)
    hints = []
    if misses >= POSITION_HINT_AFTER:
        hints.append(f"Posição: {craque.posicao}")
    if misses >= ERA_HINT_AFTER:
        hints.append(f"Época: {craque.epoca}")
    reveal = None
    if over:
        reveal = Reveal(
            nome=craque.nome,
            completo=craque.completo,
            posicao=craque.posicao,
            epoca=craque.epoca,
            fato=craque.fato,
        )
    return Verdict(
        rows=[_marks(craque.answer, w) for w in words],
        solved=solved,
        over=over,
        hints=hints,
        reveal=reveal,
    )
