"""Deterministic 7a0 data for the tests: the ABC by decades and its bracket, all-time."""

import random

from geral.games.setea0.dados import chaves
from geral.games.setea0.modelos import Clube, Dados, Jogador

LINHAS = ["GOL", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "ATA", "ATA"]  # cycled per decade


def dados_de_teste(semente: int = 7, escala: float = 1.0) -> Dados:
    """`escala` multiplies every club's strengths (capped at 99): strength is relative to the
    club, so a stronger club meets stronger opponents too."""
    rng = random.Random(semente)
    abc = []
    for decada in (1970, 1980, 2000, 2010):
        for i in range(15):
            inicio = decada + rng.randint(0, 7)
            abc.append(
                Jogador(
                    id=f"Qabc{decada}{i}",
                    nome=f"ABC {decada} {i}",
                    posicoes=[LINHAS[i % len(LINHAS)]],
                    # the last of each decade stays into the next one
                    passagens=[(inicio, inicio + 4 if i == 14 else min(inicio + 2, decada + 9))],
                    forca=min(99, round(rng.randint(30, 95) * escala)),
                )
            )
    for i, posicao in enumerate(["GOL", "ZAG", "ATA"]):  # a thin decade
        abc.append(
            Jogador(
                id=f"Qabc1940{i}",
                nome=f"ABC 1940 {i}",
                posicoes=[posicao],
                passagens=[(1942, 1945)],
                forca=min(99, round(60 * escala)),
            )
        )
    clubes = {"abc": Clube(nome="ABC", jogadores=abc)}
    for slug in [*chaves()["edicao"]["abc"]["adversarios"], "america-rn"]:
        clubes[slug] = Clube(
            nome=chaves()["clube"][slug]["nome"],
            jogadores=[
                Jogador(
                    id=f"Q{slug}{i}",
                    nome=f"{slug} {i}",
                    posicoes=[LINHAS[i % len(LINHAS)]],
                    forca=min(99, round((40 + i * 55 // 17) * escala)),
                )
                for i in range(18)
            ],
        )
    return Dados(versao="teste", clubes=clubes)


def _clube_por_decadas(rng: random.Random, slug: str, nome: str, escala: float) -> list[Jogador]:
    """A club of four decades of 15 (70s, 80s, 2000s, 2010s), as the fake ABC above."""
    jogadores = []
    for decada in (1970, 1980, 2000, 2010):
        for i in range(15):
            inicio = decada + rng.randint(0, 7)
            jogadores.append(
                Jogador(
                    id=f"Q{slug}{decada}{i}",
                    nome=f"{nome} {decada} {i}",
                    posicoes=[LINHAS[i % len(LINHAS)]],
                    passagens=[(inicio, inicio + 4 if i == 14 else min(inicio + 2, decada + 9))],
                    forca=min(99, round(rng.randint(30, 95) * escala)),
                )
            )
    return jogadores


# Players who wore two of the Geral's shirts in the same decade: one id, a stint at each club.
DUPLAS = [("Qdupla1", "flamengo", "vasco", 1980), ("Qdupla2", "abc", "nautico", 2000)]


def dados_geral_de_teste(semente: int = 11) -> Dados:
    """Every edition's club by decades (strengths from 0.9x to 1.15x), the 7 grandes all-time
    (each its own strength) and two players at two clubs."""
    rng = random.Random(semente)
    clubes: dict[str, Clube] = {}
    edicoes = chaves()["edicao"]
    for k, (slug, edicao) in enumerate(edicoes.items()):
        escala = 0.9 + 0.05 * k
        clubes[slug] = Clube(
            nome=edicao["nome"], jogadores=_clube_por_decadas(rng, slug, edicao["nome"], escala)
        )
    for id_, *dois, decada in DUPLAS:
        for slug in dois:
            clubes[slug].jogadores.append(
                Jogador(
                    id=id_,
                    nome=f"Dupla {id_[-1]}",
                    posicoes=["ATA"],
                    passagens=[(decada + 2, decada + 4)],
                    forca=90,
                )
            )
    # strengths in an order of their own, not the file's: the bracket must sort them
    for k, slug in zip((3, 0, 6, 1, 5, 2, 4), chaves()["geral"]["grandes"], strict=True):
        clubes[slug] = Clube(
            nome=chaves()["clube"][slug]["nome"],
            jogadores=[
                Jogador(
                    id=f"Q{slug}{i}",
                    nome=f"{slug} {i}",
                    posicoes=[LINHAS[i % len(LINHAS)]],
                    forca=min(99, 40 + i * 55 // 17 + k),
                )
                for i in range(18)
            ],
        )
    return Dados(versao="teste-geral", clubes=clubes)
