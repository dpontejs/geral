"""The solo game: the browser sends every guess so far; the server replays them (no state)."""

from pydantic import BaseModel

from geral.games.velha.base import Base, answers, fits
from geral.games.velha.board import Board

MAX_GUESSES = 12  # hits and misses alike
REVEALED = 3  # most famous answers shown per cell at the end


class GuessError(ValueError):
    """A guess the game cannot take (the page answers 422)."""


class Guess(BaseModel):
    casa: int
    jogador: str  # Wikidata id


class Answer(BaseModel):
    id: str
    nome: str


class CellReveal(BaseModel):
    top: list[Answer]
    total: int


class SoloVerdict(BaseModel):
    casas: dict[int, str]  # cell -> player who took it
    acertos: list[bool]  # one per guess
    over: bool
    revelacao: list[CellReveal] | None  # the nine cells, only once the game is over


def judge_solo(base: Base, board: Board, chutes: list[Guess]) -> SoloVerdict:
    casas: dict[int, str] = {}
    acertos: list[bool] = []
    for n, chute in enumerate(chutes):
        if n >= MAX_GUESSES or len(casas) == 9:
            raise GuessError("the game is over")
        if not 0 <= chute.casa <= 8:
            raise GuessError(f"no cell {chute.casa}")
        if chute.casa in casas:
            raise GuessError(f"cell {chute.casa} is taken")
        if chute.jogador not in base.players:
            raise GuessError(f"unknown player {chute.jogador}")
        hit = chute.jogador not in casas.values() and fits(
            base, chute.jogador, *board.cell(chute.casa)
        )
        if hit:
            casas[chute.casa] = chute.jogador
        acertos.append(hit)
    over = len(casas) == 9 or len(chutes) >= MAX_GUESSES
    return SoloVerdict(
        casas=casas, acertos=acertos, over=over, revelacao=_reveal(base, board) if over else None
    )


def _reveal(base: Base, board: Board) -> list[CellReveal]:
    cells = [answers(base, *board.cell(casa)) for casa in range(9)]
    return [
        CellReveal(top=[Answer(id=p.id, nome=p.nome) for p in found[:REVEALED]], total=len(found))
        for found in cells
    ]
