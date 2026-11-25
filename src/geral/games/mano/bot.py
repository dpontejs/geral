"""The Mano a Mano bot: random (facil), with a habit (medio) or reading the human (dificil).

``historico`` holds the human's previous kicks of the match in the opposite role: his kicks
when the bot defends, his dives when the bot kicks. Every draw comes from ``rng``; the
``medio`` habit is drawn once per ``rng`` (one per match) and remembered for it.
"""

import random
from collections import Counter
from weakref import WeakKeyDictionary

from geral.games.mano.regras import cobertura
from geral.games.mano.tipos import Barreira, Chute, Defesa, Lado, Lance, Nivel, Trajetoria

ACERTO_SAIDA: dict[Nivel, float] = {"facil": 0.3, "medio": 0.5, "dificil": 0.7}
P_MANIA = 0.6
P_LEITURA = 0.75
JANELA_LEITURA = 3
MARGEM = 150
BARRA_DIFICIL = 40
BARRA_MEDIO = 250
CURVA_DIFICIL = 0.5

LADOS: tuple[Lado, ...] = ("esquerda", "fica", "direita")
TRAJETORIAS: tuple[Trajetoria, ...] = ("rasteira", "por_cima", "pelo_lado")
TERCOS: dict[Lado, tuple[int, int]] = {
    "esquerda": (0, 332),
    "fica": (333, 666),
    "direita": (667, 1000),
}

_manias: WeakKeyDictionary[random.Random, Lado] = WeakKeyDictionary()


def _mania(rng: random.Random) -> Lado:
    if rng not in _manias:
        _manias[rng] = rng.choice(LADOS)
    return _manias[rng]


def _terco(x: int) -> Lado:
    return "esquerda" if x < 333 else "fica" if x < 667 else "direita"


def defender(nivel: Nivel, historico: list[Lance], rng: random.Random) -> Defesa:
    lado: Lado = rng.choice(LADOS)
    if nivel == "medio" and rng.random() < P_MANIA:
        lado = _mania(rng)
    elif nivel == "dificil" and historico and rng.random() < P_LEITURA:
        recentes = Counter(_terco(lance.chute.alvo[0]) for lance in historico[-JANELA_LEITURA:])
        lado = recentes.most_common(1)[0][0]
    return Defesa(lado=lado, saida=rng.random() < ACERTO_SAIDA[nivel])


def _menos_pulado(historico: list[Lance], rng: random.Random) -> Lado:
    pulos = Counter(lance.defesa.lado for lance in historico[-JANELA_LEITURA:])
    menor = min(pulos.get(lado, 0) for lado in LADOS)
    return rng.choice([lado for lado in LADOS if pulos.get(lado, 0) == menor])


def chutar(
    nivel: Nivel, historico: list[Lance], rng: random.Random, *, barreira: Barreira | None
) -> Chute:
    if nivel == "dificil" and historico:
        inicio, fim = TERCOS[_menos_pulado(historico, rng)]
        x = rng.randint(max(inicio, MARGEM), min(fim, 1000 - MARGEM))
        y = rng.randint(0, 1000 - MARGEM)
        barra = rng.randint(500 - BARRA_DIFICIL, 500 + BARRA_DIFICIL)
        if barreira is None:
            return Chute(alvo=(x, y), barra=barra)
        de, ate = cobertura(barreira)
        if de <= x <= ate:
            curva = rng.uniform(CURVA_DIFICIL, 1) * rng.choice((-1, 1))
            return Chute(alvo=(x, y), barra=barra, trajetoria="pelo_lado", curva=curva)
        return Chute(alvo=(x, y), barra=barra, trajetoria="rasteira")
    if nivel == "medio":
        lado = _mania(rng) if rng.random() < P_MANIA else rng.choice(LADOS)
        x = rng.randint(*TERCOS[lado])
        barra = rng.randint(500 - BARRA_MEDIO, 500 + BARRA_MEDIO)
    else:
        x = rng.randint(0, 1000)
        barra = rng.randint(0, 1000)
    alvo = (x, rng.randint(0, 1000))
    if barreira is None:
        return Chute(alvo=alvo, barra=barra)
    return Chute(
        alvo=alvo, barra=barra, trajetoria=rng.choice(TRAJETORIAS), curva=rng.uniform(-1, 1)
    )


def armar(nivel: Nivel, rng: random.Random) -> Barreira:
    if nivel == "facil":
        return Barreira(n=rng.randint(2, 5), x=rng.randint(0, 1000))
    return Barreira(n=rng.randint(3, 5), x=rng.randint(250, 750))
