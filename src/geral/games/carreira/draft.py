"""The draft: ten names on offer (eight turns plus two re-rolls), one legend and nine known real
players, one stolen attribute from each of eight of them."""

import random
from collections.abc import Iterable

from pydantic import BaseModel, Field

from geral.games.carreira.dados import Dados, Lenda
from geral.games.carreira.jogadores import jogadores_da_base
from geral.games.carreira.regras import ATRIBUTOS

OFERTA = 10  # 8 turns and 2 re-rolls
ROUBOS = len(ATRIBUTOS)


class JogadaInvalida(ValueError):
    """The fan sent something the game never offered; the message is shown to them."""


class Roubo(BaseModel):
    lenda: str = Field(max_length=60)
    atributo: str = Field(max_length=20)


def edicoes(dados: Dados, times: Iterable[str]) -> list[str]:
    """'geral' plus each of `times` with at least one legend of its own, in the given order."""
    proprias = {e for lenda in dados.lendas for e in lenda.edicoes}
    return ["geral", *(t for t in times if t != "geral" and t in proprias)]


LENDAS = 1  # curated legends in an offer, the find of the draft; the rest are known real players
JOGADORES = OFERTA - LENDAS
REGIONAIS = (1, 3)  # starting in the Northeast: at least this many legends, players of the region


def oferta(dados: Dados, edicao: str, semente_draft: str, clube: str | None = None) -> list[Lenda]:
    """The draft's ten names (8 turns and 2 re-rolls): 1 legend and 9 known real players, all
    with different names; starting in the Northeast brings people of the region (the legend is
    one of theirs). Same seed, same offer."""
    rng = random.Random(f"draft:{edicao}:{semente_draft}")
    inicio = dados.clubes.get(clube or "")
    regiao = dados.regiao(inicio) if inicio else None
    lendas = sorted((x for x in dados.lendas if "geral" in x.edicoes), key=lambda x: x.nome)
    curadas = {x.nome for x in dados.lendas}
    jogadores = [x for x in jogadores_da_base(dados) if x.nome not in curadas]
    escolhidas = _escolher(rng, lendas, LENDAS, regiao, REGIONAIS[0])
    escolhidas += _escolher(rng, jogadores, JOGADORES, regiao, REGIONAIS[1], escolhidas)
    rng.shuffle(escolhidas)
    return escolhidas


def _escolher(
    rng: random.Random,
    gente: list[Lenda],
    quantos: int,
    regiao: str | None,
    da_regiao: int,
    ja: list[Lenda] = (),
) -> list[Lenda]:
    """`quantos` of `gente` with names not taken yet, `da_regiao` of them from the region."""
    nomes = {x.nome for x in ja}
    escolhidas: list[Lenda] = []

    def pegar(candidatos: list[Lenda], n: int) -> None:
        for x in rng.sample(candidatos, min(len(candidatos), n * 3 + 10)):
            if len(escolhidas) >= quantos or n <= 0:
                return
            if x.nome not in nomes:
                escolhidas.append(x)
                nomes.add(x.nome)
                n -= 1

    if regiao:
        pegar([x for x in gente if x.regiao == regiao], da_regiao)
    pegar(gente, quantos - len(escolhidas))
    return escolhidas


def montar(ofertadas: list[Lenda], roubos: list[Roubo]) -> dict[str, int]:
    """The player's ratings: each attribute taken from a different legend of the offer."""
    por_nome = {lenda.nome: lenda for lenda in ofertadas}
    if len(roubos) != ROUBOS:
        raise JogadaInvalida(f"são {ROUBOS} roubos, um por atributo")
    if {r.atributo for r in roubos} != set(ATRIBUTOS):
        raise JogadaInvalida("cada atributo é roubado uma vez só")
    if len({r.lenda for r in roubos}) != ROUBOS:
        raise JogadaInvalida("de cada lenda se rouba um atributo só")
    if any(r.lenda not in por_nome for r in roubos):
        raise JogadaInvalida("essa lenda não estava no seu draft")
    return {r.atributo: por_nome[r.lenda].notas[r.atributo] for r in roubos}
