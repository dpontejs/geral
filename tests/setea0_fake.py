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
