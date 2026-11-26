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
# The penalty's band (dev, 2026-11-26): 120 at a post or the crossbar, +1 per unit away, up to 450
FAIXA_PENALTI_MIN = 120
FAIXA_PENALTI_MAX = 450
FAIXA_PENALTI_POR_DIST = 1
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
# Penalty bar error by direction (dev, 2026-11-26): over the band the ball climbs from the
# aim; under it the shot is weak: it drops from the aim and the keeper reaches further, at any
# height, up to about the exit's bonus.
SUBIDA_POR_ERRO = 2
QUEDA_POR_ERRO = 2
ALCANCE_POR_ERRO = 1
ALCANCE_FRACO = ALCANCE_SAIDA
# Cavadinha: a fixed, narrower band; over it the chip clears the bar, under it the keeper
# recovers. Inside it beats any dive and dies in the hands of a keeper who stays.
FAIXA_CAVADINHA = 160
ALTURA_CAVADINHA = 550
CAVADINHA_FRACA = 150

TERCO = 333
CENTRO = (500, 0)


def faixa_boa(alvo: tuple[int, int], falta: bool) -> int:
    """Width of the good band of the bar: narrower near the posts and the crossbar.

    The penalty has its own, narrower band (dev, 2026-11-26); the free kick keeps the first one.
    """
    x, y = alvo
    dist = min(x, 1000 - x, 1000 - y)
    if not falta:
        return round(min(FAIXA_PENALTI_MAX, FAIXA_PENALTI_MIN + FAIXA_PENALTI_POR_DIST * dist))
    faixa = min(FAIXA_MAX, max(FAIXA_MIN, FAIXA_MIN + FAIXA_POR_DIST * dist))
    return round(faixa * FATOR_FALTA)


def _erro(chute: Chute, falta: bool) -> float:
    """How far the bar stopped outside the good band (0 inside it)."""
    largura = FAIXA_CAVADINHA if chute.cavadinha else faixa_boa(chute.alvo, falta)
    return max(0.0, abs(chute.barra - 500) - largura / 2)


def _onde_no_penalti(chute: Chute) -> tuple[float, float, float]:
    """Where a penalty goes before noise, and the keeper's extra reach of a weak shot."""
    x, y = chute.alvo
    erro = _erro(chute, falta=False)
    if not erro:
        return x, y, 0.0
    if chute.barra > 500:
        return x, y + erro * SUBIDA_POR_ERRO, 0.0
    return x, max(0, y - erro * QUEDA_POR_ERRO), min(ALCANCE_FRACO, erro * ALCANCE_POR_ERRO)


def _cavadinha(
    chute: Chute, defesa: Defesa, rng: random.Random
) -> tuple[tuple[int, int], Resultado]:
    """The chip: decided by the bar and by whether the keeper stayed, never by the aim."""
    erro = _erro(chute, falta=False)
    x = 500 + round(rng.uniform(-RUIDO, RUIDO))
    if erro and chute.barra > 500:
        return (x, 1000 + TRAVE + 1 + round(erro * SUBIDA_POR_ERRO)), "fora"
    if erro:
        return (x, CAVADINHA_FRACA), "defesa"
    return (x, ALTURA_CAVADINHA), "defesa" if defesa.lado == "fica" else "gol"


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


def _alcanca(defesa: Defesa, x: int, y: int, rng: random.Random, extra: float = 0) -> bool:
    """Whether the keeper's choice covers the ball at (x, y): same keeper in both modes.

    ``extra`` widens his reach past his third at any height, and takes the angle too: a weak
    penalty."""
    if _terco(x) == defesa.lado:
        if defesa.lado == "fica" or y <= ALTURA_PULO or extra:
            return True
        return rng.random() < P_ANGULO
    alcance = (ALCANCE_SAIDA if defesa.saida and y <= ALTURA_PULO else 0) + extra
    if not alcance:
        return False
    if defesa.lado == "esquerda":
        return x < TERCO + alcance
    if defesa.lado == "direita":
        return x >= 1000 - TERCO - alcance
    return TERCO - alcance <= x < 1000 - TERCO + alcance


def resolver(
    chute: Chute,
    defesa: Defesa,
    rng: random.Random,
    *,
    barreira: Barreira | None = None,
    posicao: Posicao | None = None,
) -> Lance:
    """Resolve a free kick when a ``barreira`` is given, else a penalty.

    A penalty ignores ``trajetoria``, ``curva`` and ``posicao``; a free kick refuses a
    ``cavadinha``.
    """
    extra = 0.0
    if barreira is None:
        if chute.cavadinha:
            onde, resultado = _cavadinha(chute, defesa, rng)
            return Lance(
                chute=chute,
                defesa=defesa,
                barreira=None,
                posicao=None,
                onde=onde,
                resultado=resultado,
            )
        x, y, extra = _onde_no_penalti(chute)
        posicao = None
    else:
        if chute.trajetoria is None:
            raise ValueError("a free kick needs a trajetoria")
        if chute.cavadinha:
            raise ValueError("a cavadinha is a penalty kick")
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
        resultado = "defesa" if _alcanca(defesa, *onde, rng, extra) else "gol"
    return Lance(
        chute=chute,
        defesa=defesa,
        barreira=barreira,
        posicao=posicao,
        onde=onde,
        resultado=resultado,
    )
