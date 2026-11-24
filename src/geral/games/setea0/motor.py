"""The 7a0 engine: pure and deterministic, replayed from the seed on every call.

Every function takes `dados` and recomputes from `semente`, like `carreira/motor.py`.
"""

import weakref
from random import Random

from geral.games.setea0.modelos import (
    ESQUEMAS,
    MODOS,
    Dados,
    Escalado,
    Escolha,
    JogadaInvalida,
    Jogador,
    Posicao,
    Rodada,
)

MIN_DECADA = 8  # a decade needs this many players at the club to be drawn
TAMANHO_OFERTA = 10
RODADAS = 11

LINHA: dict[Posicao, str] = {"GOL": "GOL", "ZAG": "DEF", "LAT": "DEF", "MEI": "MEI", "ATA": "ATA"}
VIZINHAS = {frozenset(("LAT", "ZAG")), frozenset(("LAT", "MEI")), frozenset(("MEI", "ATA"))}


# Per-`Dados` index of each club's players by decade; mass simulations draw thousands of offers.
_INDICES: dict[int, tuple[weakref.ref, dict[str, dict[int, list[Jogador]]]]] = {}


def _por_decada(dados: Dados, edicao: str) -> dict[int, list[Jogador]]:
    if edicao not in dados.clubes:
        raise JogadaInvalida(f"edição sem 7a0: {edicao}")
    chave = id(dados)
    guardado = _INDICES.get(chave)
    if guardado is None or guardado[0]() is not dados:  # a dead `Dados` may leave its id behind
        guardado = (weakref.ref(dados, lambda _: _INDICES.pop(chave, None)), {})
        _INDICES[chave] = guardado
    indice = guardado[1]
    if edicao not in indice:
        grupos: dict[int, list[Jogador]] = {}
        for jogador in dados.clubes[edicao].jogadores:
            for decada in sorted(jogador.decadas()):
                grupos.setdefault(decada, []).append(jogador)
        indice[edicao] = grupos
    return indice[edicao]


def decadas(dados: Dados, edicao: str) -> list[int]:
    """The club's decades with at least `MIN_DECADA` players, in order."""
    return sorted(d for d, js in _por_decada(dados, edicao).items() if len(js) >= MIN_DECADA)


def oferta(
    dados: Dados, edicao: str, semente: str, rodada: int, troca: int, modo: str = "classico"
) -> Rodada:
    """The decade drawn for this round and reroll, with up to 10 of its players."""
    if modo not in MODOS:
        raise JogadaInvalida(f"modo desconhecido: {modo}")
    if not 0 <= rodada < RODADAS or not 0 <= troca <= MODOS[modo]:
        raise JogadaInvalida(f"rodada {rodada} ou troca {troca} fora do jogo")
    rng = Random(f"{semente}:{rodada}:{troca}")
    decada = rng.choice(decadas(dados, edicao))
    da_decada = list(_por_decada(dados, edicao)[decada])
    rng.shuffle(da_decada)
    escolhidos: list[Jogador] = []
    for linha in ("GOL", "DEF", "MEI", "ATA"):  # one of each line when the decade has one
        achado = next(
            (
                j
                for j in da_decada
                if j not in escolhidos and any(LINHA[p] == linha for p in j.posicoes)
            ),
            None,
        )
        if achado is not None:
            escolhidos.append(achado)
    for jogador in da_decada:
        if len(escolhidos) >= TAMANHO_OFERTA:
            break
        if jogador not in escolhidos:
            escolhidos.append(jogador)
    escolhidos.sort(key=lambda j: -j.forca)
    return Rodada(
        rodada=rodada,
        troca=troca,
        decada=decada,
        jogadores=escolhidos,
        trocas_restantes=MODOS[modo] - troca,
    )


def encaixe(jogador: Jogador, vaga: Posicao) -> float:
    """How well the player fits the slot: the best of his positions."""

    def um(posicao: Posicao) -> float:
        if posicao == vaga:
            return 1.0
        if frozenset((posicao, vaga)) in VIZINHAS:
            return 0.85
        if "GOL" in (posicao, vaga):
            return 0.3
        return 0.6

    return max(um(p) for p in jogador.posicoes)


def escalar(
    dados: Dados, edicao: str, semente: str, modo: str, esquema: str, escolhas: list[Escolha]
) -> list[Escalado]:
    """Checks the lineup against the draw; the 11 sorted by slot."""
    if esquema not in ESQUEMAS:
        raise JogadaInvalida(f"esquema desconhecido: {esquema}")
    if modo not in MODOS:
        raise JogadaInvalida(f"modo desconhecido: {modo}")
    if len(escolhas) != RODADAS:
        raise JogadaInvalida("a escalação tem 11 escolhas")
    ordem = sorted(escolhas, key=lambda e: e.rodada)
    if [e.rodada for e in ordem] != list(range(RODADAS)):
        raise JogadaInvalida("as rodadas vão de 0 a 10")
    if sorted(e.vaga for e in ordem) != list(range(len(ESQUEMAS[esquema]))):
        raise JogadaInvalida("vaga repetida ou fora do esquema")
    escalados = []
    usados: set[str] = set()
    troca = 0
    for escolha in ordem:
        if escolha.troca < troca or escolha.troca > MODOS[modo]:
            raise JogadaInvalida(f"troca inválida na rodada {escolha.rodada}")
        troca = escolha.troca
        rodada = oferta(dados, edicao, semente, escolha.rodada, escolha.troca, modo)
        jogador = next((j for j in rodada.jogadores if j.id == escolha.jogador), None)
        if jogador is None:
            raise JogadaInvalida(f"{escolha.jogador} não estava na rodada {escolha.rodada}")
        if jogador.id in usados:
            raise JogadaInvalida(f"{jogador.nome} já está no time")
        usados.add(jogador.id)
        escalados.append(Escalado(jogador=jogador, decada=rodada.decada, vaga=escolha.vaga))
    return sorted(escalados, key=lambda e: e.vaga)
