"""Fake word bank and helpers for the Prancheta room tests."""

import random
from datetime import UTC, datetime, timedelta

from geral.games.prancheta.sala import Sala
from geral.games.prancheta.tipos import Palavra, Veredito, normalizar

T0 = datetime(2026, 11, 23, 20, 0, tzinfo=UTC)


def em(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


def _p(texto: str, dificuldade: str, *aceita: str) -> Palavra:
    return Palavra(texto, tuple(aceita), dificuldade, "lance")  # type: ignore[arg-type]


PALAVRAS = [
    _p("Bicicleta", "facil", "bicicleta de costas"),
    _p("Escanteio", "facil"),
    _p("Trave", "facil"),
    _p("Apito", "facil"),
    _p("Gol olímpico", "media", "gol de escanteio"),
    _p("Carrinho", "media"),
    _p("Impedimento", "media"),
    _p("Chapéu", "media"),
    _p("Frasqueira", "dificil", "torcida do abc"),
    _p("Folha seca", "dificil"),
    _p("Pé de Anjo", "dificil"),
    _p("Arquibancada", "dificil"),
]


class BancoFalso:
    """Offers the first unused word of each difficulty; exact match by `normalizar`."""

    def __init__(self) -> None:
        self.julgados: list[str] = []

    def opcoes(self, rng: random.Random, usadas: set[str]) -> list[Palavra]:
        return [
            next(p for p in PALAVRAS if p.dificuldade == d and p.texto not in usadas)
            for d in ("facil", "media", "dificil")
        ]

    def julgar(self, chute: str, palavra: Palavra) -> Veredito:
        self.julgados.append(chute)
        alvo = normalizar(chute)
        if alvo in {normalizar(t) for t in (palavra.texto, *palavra.aceita)}:
            return "certo"
        if len(alvo) >= 4 and normalizar(palavra.texto).startswith(alvo[:4]):
            return "trave"
        return "errado"


APELIDOS = ["Ana", "Bia", "Caio", "Davi", "Edu", "Fabi", "Gil", "Hugo", "Iara", "Juca", "Kiko"]


def sala_com(
    n: int, agora: datetime = T0, rodadas: int = 1, banco: BancoFalso | None = None
) -> tuple[Sala, dict[int, str]]:
    """A room where `n` players joined and connected; returns it and the tokens by player id."""
    sala = Sala("abc234", rodadas, banco or BancoFalso(), random.Random(7), agora)
    tokens = {}
    for apelido in APELIDOS[:n]:
        jogador, token, _ = sala.entrar(apelido, agora)
        sala.conectou(jogador, agora)
        tokens[jogador] = token
    return sala, tokens


def traco(id_: int, pts: list[list[int]], fim: bool = True, cor: int = 1, esp: int = 2) -> dict:
    return {"tipo": "traco", "id": id_, "cor": cor, "esp": esp, "pts": pts, "fim": fim}
