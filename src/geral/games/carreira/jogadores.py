"""Real players for the draft, from the jogo da velha base: the curated legends are few and all
great, so most of the offer is made of real players, only the ones fans know: a curated list in
conhecidos.toml (fame alone let in too many names nobody remembers).

Their ratings come from a formula, the same for a player every time (seeded by his id): the level
from his fame (number of Wikipedias), the profile from his position, a little noise.
"""

import math
import random
import tomllib
from functools import cache
from pathlib import Path

from geral.games.carreira.dados import Dados, Lenda
from geral.games.carreira.regras import ATRIBUTOS
from geral.games.velha.base import POSITIONS, Player, load

# Points above or below the player's level, by position (order of ATRIBUTOS).
PERFIS = {
    "atacante": (4, 11, -3, 5, -22, 0, 2, -5),
    "meio-campo": (0, 0, 10, 6, -3, -2, -10, 2),
    "lateral": (8, -11, 2, 2, 3, 2, -8, -5),
    "zagueiro": (-6, -19, -5, -14, 11, 6, 10, 3),
}
FAMA_TOPO = 80  # from here a player is as good as the formula allows
AJUSTES = Path(__file__).parent / "conhecidos.toml"


@cache
def _ajustes() -> dict:
    return tomllib.loads(AJUSTES.read_text(encoding="utf-8"))


def apelidos() -> dict[str, str]:
    """Fan names for players the base lists by their registered name."""
    return _ajustes()["apelidos"]


def lista_do_draft() -> frozenset[str]:
    """The curated list of players fans know: only they come up in the draft."""
    return frozenset(_ajustes()["draft"]["jogadores"])


def nivel(fama: int) -> float:
    """Fame 20 ≈ 61, 40 ≈ 66, 80+ ≈ 71 (calibrated on the curated list: a careful draft ~72)."""
    return 39 + 32 * min(1.0, math.log(1 + fama) / math.log(1 + FAMA_TOPO))


def notas_do_jogador(p: Player) -> dict[str, int]:
    rng = random.Random(f"jogador:{p.id}")
    perfil = PERFIS.get(p.posicoes[0], PERFIS["meio-campo"])
    base = nivel(p.fama)
    return {
        a: max(15, min(95, round(base + d + max(-8.0, min(8.0, rng.gauss(0, 4))))))
        for a, d in zip(ATRIBUTOS, perfil, strict=True)
    }


@cache
def _todos(versao: str, nordeste: frozenset[str], curadas: frozenset[str]) -> tuple[Lenda, ...]:
    nomes, lista = apelidos(), lista_do_draft()
    jogadores = []
    for p in sorted(load().players.values(), key=lambda p: p.id):
        if not p.posicoes or "goleiro" in p.posicoes or p.id in curadas:
            continue
        if p.id not in lista:
            continue
        da_regiao = bool(p.clubes & nordeste)
        jogadores.append(
            Lenda(
                nome=nomes.get(p.id, p.nome),
                wikidata=p.id,
                edicoes=("base",),
                notas=notas_do_jogador(p),
                regiao="nordeste" if da_regiao else "",
                tipo="jogador",
                resumo=f"{POSITIONS[p.posicoes[0]]} · {p.anos}"
                if p.anos
                else POSITIONS[p.posicoes[0]],
            )
        )
    return tuple(jogadores)


def jogadores_da_base(dados: Dados) -> tuple[Lenda, ...]:
    """The known outfield players of the base but the curated legends, as draft entries."""
    nordeste = frozenset(
        c.wikidata for c in dados.clubes.values() if c.wikidata and dados.regiao(c) == "nordeste"
    )
    curadas = frozenset(x.wikidata for x in dados.lendas)
    return _todos(dados.versao, nordeste, curadas)
