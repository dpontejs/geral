"""The 7a0 difficulty, in one pass of 1000 seeds per team (engine takes every penalty)."""

from setea0_fake import dados_de_teste
from setea0_times import aleatorias, gulosas

from geral.games.setea0 import motor

SEMENTES = [f"cal{i}" for i in range(1000)]


def _taxa(dados, edicao, escolher) -> float:
    campeoes = 0
    for semente in SEMENTES:
        es = escolher(dados, edicao, semente)
        campeoes += motor.campanha_motor(dados, edicao, semente, "classico", "4-4-2", es).campeao
    return campeoes / len(SEMENTES)


def test_calibragem():
    # a synthetic Flamengo: the same generator, another seed, strengths 20% higher
    abc, fla = dados_de_teste(), dados_de_teste(semente=8, escala=1.2)
    guloso = _taxa(abc, "abc", gulosas)
    aleatorio = _taxa(abc, "abc", aleatorias)
    flamengo = _taxa(fla, "abc", gulosas)
    assert 0.10 <= guloso <= 0.30, guloso
    assert aleatorio < 0.03, aleatorio
    assert abs(flamengo - guloso) <= 0.5 * guloso, (guloso, flamengo)
