"""Lineups for the 7a0 tests: a greedy fan and a random one."""

import random

from geral.games.setea0 import motor
from geral.games.setea0.modelos import ESQUEMAS, Dados, Escolha


def gulosas(
    dados: Dados,
    edicao: str,
    semente: str,
    esquema: str = "4-4-2",
    modo: str = "classico",
    trocas: list[int] | None = None,
) -> list[Escolha]:
    """Each round, the strongest offered player that fits a free slot (best fit first)."""
    trocas = trocas or [0] * 11
    vagas = ESQUEMAS[esquema]
    livres = list(range(11))
    usados: set[str] = set()
    escolhas = []
    for rodada in range(11):
        r = motor.oferta(dados, edicao, semente, rodada, trocas[rodada], modo)
        jogador, vaga = max(
            ((j, v) for j in r.jogadores if j.id not in usados for v in livres),
            key=lambda jv: (motor.encaixe(jv[0], vagas[jv[1]]), jv[0].forca),
        )
        livres.remove(vaga)
        usados.add(jogador.id)
        escolhas.append(Escolha(rodada=rodada, troca=trocas[rodada], jogador=jogador.id, vaga=vaga))
    return escolhas


def aleatorias(dados: Dados, edicao: str, semente: str) -> list[Escolha]:
    """A fan who clicks anywhere: a random offered player into a random free slot."""
    rng = random.Random(f"aleatorio:{semente}")
    livres = list(range(11))
    usados: set[str] = set()
    escolhas = []
    for rodada in range(11):
        r = motor.oferta(dados, edicao, semente, rodada, 0)
        jogador = rng.choice([j for j in r.jogadores if j.id not in usados])
        vaga = livres.pop(rng.randrange(len(livres)))
        usados.add(jogador.id)
        escolhas.append(Escolha(rodada=rodada, troca=0, jogador=jogador.id, vaga=vaga))
    return escolhas


def zagueiro_no_gol(dados: Dados, edicao: str, semente: str) -> list[Escolha]:
    """The dev's case: the greedy XI with the keeper's slot swapped with a centre-back's."""
    vagas = ESQUEMAS["4-4-2"]
    escolhas = gulosas(dados, edicao, semente)
    g = next(i for i, e in enumerate(escolhas) if vagas[e.vaga] == "GOL")
    z = next(i for i, e in enumerate(escolhas) if vagas[e.vaga] == "ZAG")
    vaga_g, vaga_z = escolhas[g].vaga, escolhas[z].vaga
    escolhas[g] = escolhas[g].model_copy(update={"vaga": vaga_z})
    escolhas[z] = escolhas[z].model_copy(update={"vaga": vaga_g})
    return escolhas
