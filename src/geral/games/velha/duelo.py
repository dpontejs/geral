"""The duel: X against O on one board. The server replays every move (no state of its own).

X starts. A right player takes the cell; a wrong one, a player already on the board (by anyone),
a timeout or a pass hands the turn over. Three in a row wins at once; a full board, MAX_DRY_TURNS
turns in a row without a cell taken, or an end both players agreed to (`encerrar`) end the game,
and then the most cells win (same count: empate).
"""

from typing import Literal

from pydantic import BaseModel, Field

from geral.games.velha.base import Base, fits
from geral.games.velha.board import Board
from geral.games.velha.judge import GuessError

MAX_DRY_TURNS = 6
SECONDS = 30  # per turn; the clock runs in the browser here, on the server in the duel by link
LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))

type Side = Literal["X", "O"]


class Move(BaseModel):
    casa: int | None = None
    jogador: str | None = Field(default=None, max_length=20)
    estouro: bool = False  # the turn's time ran out, or the player passed
    encerrar: bool = False  # both players agreed to end here: the most cells win


class DuelState(BaseModel):
    casas: dict[int, Side]
    jogadores: dict[int, str]  # cell -> the player who took it
    vez: Side
    acertos: list[bool]  # one per move
    sem_casa: int  # turns in a row without a cell taken
    over: bool
    vencedor: Literal["X", "O", "empate"] | None
    linha: list[int] | None  # the winning three in a row
    acordo: bool = False  # ended because both players agreed


def _line(casas: dict[int, Side], side: Side) -> list[int] | None:
    return next((list(line) for line in LINES if all(casas.get(c) == side for c in line)), None)


def judge_duel(base: Base, board: Board, jogadas: list[Move]) -> DuelState:
    casas: dict[int, Side] = {}
    jogadores: dict[int, str] = {}
    acertos: list[bool] = []
    vez: Side = "X"
    sem_casa, vencedor, linha, acordo = 0, None, None, False
    for move in jogadas:
        if vencedor is not None:
            raise GuessError("the duel is over")
        if move.encerrar:
            acertos.append(False)
            acordo = True
            x, o = (sum(1 for s in casas.values() if s == side) for side in ("X", "O"))
            vencedor = "X" if x > o else "O" if o > x else "empate"
            continue
        hit = False
        if not move.estouro:
            if move.casa is None or move.jogador is None:
                raise GuessError("a move names a cell and a player, or is a timeout")
            if not 0 <= move.casa <= 8:
                raise GuessError(f"no cell {move.casa}")
            if move.casa in casas:
                raise GuessError(f"cell {move.casa} is taken")
            if move.jogador not in base.players:
                raise GuessError(f"unknown player {move.jogador}")
            hit = move.jogador not in jogadores.values() and fits(
                base, move.jogador, *board.cell(move.casa)
            )
        acertos.append(hit)
        if hit:
            casas[move.casa] = vez
            jogadores[move.casa] = move.jogador
            sem_casa = 0
            if line := _line(casas, vez):
                vencedor, linha = vez, line
        else:
            sem_casa += 1
        if vencedor is None and (len(casas) == 9 or sem_casa >= MAX_DRY_TURNS):
            x, o = (sum(1 for s in casas.values() if s == side) for side in ("X", "O"))
            vencedor = "X" if x > o else "O" if o > x else "empate"
        vez = "O" if vez == "X" else "X"
    return DuelState(
        casas=casas,
        jogadores=jogadores,
        vez=vez,
        acertos=acertos,
        sem_casa=sem_casa,
        over=vencedor is not None,
        vencedor=vencedor,
        linha=linha,
        acordo=acordo,
    )
