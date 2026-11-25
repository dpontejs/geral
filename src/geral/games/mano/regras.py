"""Resolve one Mano a Mano kick: where the ball goes and what happens to it.

Goal coordinates: ``x`` 0-1000 left to right as the kicker sees it, ``y`` 0-1000 from the
ground to the crossbar. Every draw comes from the ``rng`` passed in.
"""

import math
import random

from geral.games.mano.tipos import Chute, Defesa, Lado, Lance, Resultado

# Tuning constants: only these change to pass the calibration.
FAIXA_MIN = 60
FAIXA_MAX = 320
FAIXA_POR_DIST = 1.1
FATOR_FALTA = 0.8
DESVIO_POR_ERRO = 0.7
RUIDO = 20
TRAVE = 25
ALTURA_PULO = 600
P_ANGULO = 0.35
ALCANCE_SAIDA = 120

TERCO = 333
CENTRO = (500, 0)


def faixa_boa(alvo: tuple[int, int], falta: bool) -> int:
    """Width of the good band of the bar: narrower near the posts and the crossbar."""
    x, y = alvo
    dist = min(x, 1000 - x, 1000 - y)
    faixa = min(FAIXA_MAX, max(FAIXA_MIN, FAIXA_MIN + FAIXA_POR_DIST * dist))
    if falta:
        faixa *= FATOR_FALTA
    return round(faixa)


def _erro(chute: Chute, falta: bool) -> float:
    """How far the bar stopped outside the good band (0 inside it)."""
    return max(0.0, abs(chute.barra - 500) - faixa_boa(chute.alvo, falta) / 2)


def _desviar(alvo: tuple[int, int], erro: float) -> tuple[float, float]:
    """Push the ball away from the goal's centre, proportionally to the error."""
    dx, dy = alvo[0] - CENTRO[0], alvo[1] - CENTRO[1]
    norma = math.hypot(dx, dy)
    if norma == 0:
        dx, dy, norma = 0, 1, 1
    empurrao = erro * DESVIO_POR_ERRO
    return alvo[0] + dx / norma * empurrao, alvo[1] + dy / norma * empurrao


def _na_trave_ou_fora(x: int, y: int) -> Resultado | None:
    dentro_x = -TRAVE <= x <= 1000 + TRAVE
    if dentro_x and 1000 - TRAVE <= y <= 1000 + TRAVE:
        return "trave"
    if y <= 1000 + TRAVE and (abs(x) <= TRAVE or abs(x - 1000) <= TRAVE):
        return "trave"
    if x < 0 or x > 1000 or y > 1000:
        return "fora"
    return None


def _terco(x: int) -> Lado:
    if x < TERCO:
        return "esquerda"
    if x < 1000 - TERCO:
        return "fica"
    return "direita"


def _alcanca(defesa: Defesa, x: int, y: int, rng: random.Random) -> bool:
    """Whether the keeper's choice covers the ball at (x, y)."""
    if _terco(x) == defesa.lado:
        if defesa.lado == "fica" or y <= ALTURA_PULO:
            return True
        return rng.random() < P_ANGULO
    if not defesa.saida or y > ALTURA_PULO:
        return False
    if defesa.lado == "esquerda":
        return x < TERCO + ALCANCE_SAIDA
    if defesa.lado == "direita":
        return x >= 1000 - TERCO - ALCANCE_SAIDA
    return TERCO - ALCANCE_SAIDA <= x < 1000 - TERCO + ALCANCE_SAIDA


def resolver(chute: Chute, defesa: Defesa, rng: random.Random) -> Lance:
    """Resolve a penalty kick."""
    x, y = _desviar(chute.alvo, _erro(chute, falta=False))
    x += rng.uniform(-RUIDO, RUIDO)
    y += rng.uniform(-RUIDO, RUIDO)
    onde = (round(x), max(0, round(y)))
    resultado = _na_trave_ou_fora(*onde)
    if resultado is None:
        resultado = "defesa" if _alcanca(defesa, *onde, rng) else "gol"
    return Lance(
        chute=chute, defesa=defesa, barreira=None, posicao=None, onde=onde, resultado=resultado
    )
