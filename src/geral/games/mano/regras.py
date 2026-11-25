"""Resolve one Mano a Mano kick: where the ball goes and what happens to it.

Goal coordinates: ``x`` 0-1000 left to right as the kicker sees it, ``y`` 0-1000 from the
ground to the crossbar. Every draw comes from the ``rng`` passed in.
"""

import math
import random

from geral.games.mano.tipos import Barreira, Chute, Defesa, Lado, Lance, Posicao, Resultado

# Tuning constants: only these change to pass the calibration.
FAIXA_MIN = 250
FAIXA_MAX = 500
FAIXA_POR_DIST = 3
FATOR_FALTA = 0.95
DESVIO_POR_ERRO = 0.8
RUIDO = 10
TRAVE = 15
ALTURA_PULO = 500
P_ANGULO = 0.25
ALCANCE_SAIDA = 90
ALTURA_BARREIRA = 450
MEIA_LARGURA_POR_HOMEM = 55
CURVA_CONTORNA = 0.3
ALTURA_RASTEIRA = 150

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


def cobertura(barreira: Barreira) -> tuple[int, int]:
    """Stretch of ``x`` the wall covers, cut to the goal mouth."""
    meia = barreira.n * MEIA_LARGURA_POR_HOMEM
    return max(0, barreira.x - meia), min(1000, barreira.x + meia)


def _onde_na_falta(chute: Chute) -> tuple[float, float]:
    """Where a free kick goes before noise: the bar is also the strength of ``por_cima``."""
    erro = _erro(chute, falta=True)
    if chute.trajetoria == "por_cima" and erro:
        fraco = chute.barra < 500
        return chute.alvo[0], chute.alvo[1] + (-erro if fraco else erro) * DESVIO_POR_ERRO
    return _desviar(chute.alvo, erro)


def curva_certa(barreira: Barreira, chega: int) -> int:
    """Sign a ``pelo_lado`` curve needs to end at ``chega`` behind the wall: it bends away
    from the wall's centre (positive bends right as the kicker sees it); 0 = either works."""
    return (chega > barreira.x) - (chega < barreira.x)


def _contorna(chute: Chute, barreira: Barreira, desvio: int) -> bool:
    if chute.trajetoria != "pelo_lado" or abs(chute.curva) < CURVA_CONTORNA:
        return False
    sinal = curva_certa(barreira, chute.alvo[0] + desvio)
    return sinal == 0 or (chute.curva > 0) == (sinal > 0)


def _na_barreira(chute: Chute, barreira: Barreira, desvio: int, x: int, y: int) -> bool:
    inicio, fim = cobertura(barreira)
    if not (inicio <= x <= fim and y <= ALTURA_BARREIRA):
        return False
    return not _contorna(chute, barreira, desvio)


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
    """Whether the keeper's choice covers the ball at (x, y): same keeper in both modes."""
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


def resolver(
    chute: Chute,
    defesa: Defesa,
    rng: random.Random,
    *,
    barreira: Barreira | None = None,
    posicao: Posicao | None = None,
) -> Lance:
    """Resolve a free kick when a ``barreira`` is given, else a penalty.

    A penalty ignores ``trajetoria``, ``curva`` and ``posicao``.
    """
    if barreira is None:
        x, y = _desviar(chute.alvo, _erro(chute, falta=False))
        posicao = None
    else:
        if chute.trajetoria is None:
            raise ValueError("a free kick needs a trajetoria")
        x, y = _onde_na_falta(chute)
    x += rng.uniform(-RUIDO, RUIDO)
    y += rng.uniform(-RUIDO, RUIDO)
    desvio = posicao.desvio if posicao else 0
    if barreira is not None and chute.trajetoria == "rasteira":
        y = min(y, ALTURA_RASTEIRA)
    onde = (round(x) + desvio, max(0, round(y)))
    resultado: Resultado | None = None
    if barreira is not None and _na_barreira(chute, barreira, desvio, *onde):
        resultado = "barreira"
    if resultado is None:
        resultado = _na_trave_ou_fora(*onde)
    if resultado is None:
        resultado = "defesa" if _alcanca(defesa, *onde, rng) else "gol"
    return Lance(
        chute=chute,
        defesa=defesa,
        barreira=barreira,
        posicao=posicao,
        onde=onde,
        resultado=resultado,
    )
