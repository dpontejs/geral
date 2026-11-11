"""'Quem é?': the whole career of the player of the day is shown; guess who it is.

The inverse of 'Onde jogou?', on the same careers file and editions, in another daily order.
"""

from datetime import date

from pydantic import BaseModel

from geral.games import onde_jogou
from geral.games.daily import number_on, pick
from geral.games.onde_jogou import Data, Jogador

LAUNCH = date(2026, 11, 12)  # puzzle #1: no later than the deploy, or two days share #1
MAX_GUESSES = 6
POSITION_HINT_AFTER, INITIAL_HINT_AFTER = 3, 4  # misses


def pool(data: Data, edition: str, teams: dict[str, str]) -> list[Jogador]:
    return onde_jogou.pool(data, edition, teams, game="quem-e")


def puzzle_number(day: date) -> int:
    return number_on(day, LAUNCH)


def by_number(players: list[Jogador], number: int) -> Jogador:
    return pick(players, number)


class Row(BaseModel):
    nome: str
    certo: bool


class Reveal(BaseModel):
    nome: str
    posicao: str


class Verdict(BaseModel):
    rows: list[Row]
    solved: bool
    over: bool
    hints: list[str]
    reveal: Reveal | None


def judge(data: Data, jogador: Jogador, palpites: list[str]) -> Verdict:
    """`palpites`: Wikidata ids of the players picked (the API rejects unknown ones)."""
    names = {j.wikidata: j.nome for j in data.jogadores}
    guesses = list(dict.fromkeys(palpites))  # a repeated guess counts once
    solved = jogador.wikidata in guesses
    over = solved or len(guesses) >= MAX_GUESSES
    misses = len(guesses) - (1 if solved else 0)
    hints = []
    if misses >= POSITION_HINT_AFTER and jogador.posicao:
        hints.append(f"Posição: {jogador.posicao}")
    if misses >= INITIAL_HINT_AFTER:
        hints.append(f"Começa com {jogador.nome[:1].upper()}")
    return Verdict(
        rows=[Row(nome=names.get(q, q), certo=q == jogador.wikidata) for q in guesses],
        solved=solved,
        over=over,
        hints=hints,
        reveal=Reveal(nome=jogador.nome, posicao=jogador.posicao) if over else None,
    )
