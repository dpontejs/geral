"""Real players for the draft, from the jogo da velha base: the curated legends are few and all
great, so most of the offer is made of real players, only the ones fans know (Brazilians who
played for the Seleção or are famous; in the Northeast, the region's own names too).

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
# Who counts as known (fame = number of Wikipedias): a Seleção player from CORTE_SELECAO, anyone
# from CORTE_FAMA, a player of a Northeastern club from CORTE_NORDESTE.
CORTE_SELECAO = 20
CORTE_FAMA = 40
CORTE_NORDESTE = 25


@cache
def _ajustes() -> tuple[dict[str, str], frozenset[str]]:
    """Fan names for players the base lists by their registered name, and who stays out."""
    raw = tomllib.loads((Path(__file__).parent / "conhecidos.toml").read_text(encoding="utf-8"))
    fora = raw["fora"]
    return raw["apelidos"], frozenset(fora["tecnicos"]) | frozenset(fora["sem_apelido"])


def conhecido(p: Player, nordeste: bool) -> bool:
    """A Brazilian (no other country, or he played for the Seleção) fans would know."""
    return (not p.paises or p.selecao) and (
        p.fama >= CORTE_FAMA
        or (p.selecao and p.fama >= CORTE_SELECAO)
        or (nordeste and p.fama >= CORTE_NORDESTE)
    )


def nivel(fama: int) -> float:
    """Fame 20 ≈ 62, 40 ≈ 67, 80+ ≈ 72 (calibrated: a careful draft lands around 71)."""
    return 40 + 32 * min(1.0, math.log(1 + fama) / math.log(1 + FAMA_TOPO))


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
    apelidos, fora = _ajustes()
    jogadores = []
    for p in sorted(load().players.values(), key=lambda p: p.id):
        if not p.posicoes or "goleiro" in p.posicoes or p.id in curadas:
            continue
        if p.id in fora or p.nome in fora:
            continue
        da_regiao = bool(p.clubes & nordeste)
        if not conhecido(p, da_regiao):
            continue
        jogadores.append(
            Lenda(
                nome=apelidos.get(p.id, p.nome),
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
