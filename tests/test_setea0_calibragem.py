"""The 7a0 difficulty, in one pass of 1000 seeds per team (engine takes every penalty)."""

from setea0_fake import dados_de_teste, dados_geral_de_teste
from setea0_times import aleatorias, gulosas, zagueiro_no_gol

from geral.games.setea0 import motor

SEMENTES = [f"cal{i}" for i in range(1000)]


def _taxas(dados, edicao, escolher) -> tuple[float, float]:
    """(title rate, rate of campaigns that reach game 5 or beyond)."""
    campeoes = chegaram = 0
    for semente in SEMENTES:
        es = escolher(dados, edicao, semente)
        feita = motor.campanha_motor(dados, edicao, semente, "classico", "4-4-2", es)
        campeoes += feita.campeao
        chegaram += sum(p.venceu for p in feita.partidas) >= 4
    return campeoes / len(SEMENTES), chegaram / len(SEMENTES)


def test_calibragem():
    # a synthetic Flamengo: the same generator, another seed, strengths 20% higher
    abc, fla = dados_de_teste(), dados_de_teste(semente=8, escala=1.2)
    guloso, _ = _taxas(abc, "abc", gulosas)
    aleatorio, _ = _taxas(abc, "abc", aleatorias)
    flamengo, _ = _taxas(fla, "abc", gulosas)
    # the dev's case (2026-11-24): a centre-back in goal still reached game 5
    sem_goleiro, jogo_5_sem_goleiro = _taxas(abc, "abc", zagueiro_no_gol)
    assert 0.10 <= guloso <= 0.30, guloso
    assert aleatorio < 0.03, aleatorio
    assert abs(flamengo - guloso) <= 0.5 * guloso, (guloso, flamengo)
    assert sem_goleiro < 0.01, sem_goleiro
    assert jogo_5_sem_goleiro < 0.03, jogo_5_sem_goleiro


def test_zagueiro_no_gol_poe_um_zagueiro_no_gol():
    abc = dados_de_teste()
    escalados = motor.escalar(
        abc, "abc", "cal0", "classico", "4-4-2", zagueiro_no_gol(abc, "abc", "cal0")
    )
    assert escalados[0].jogador.posicoes == ["ZAG"]  # slot 0 is the goal
    assert any(e.jogador.posicoes == ["GOL"] for e in escalados[3:5])


def test_calibragem_da_geral():
    """The Geral (dev, 2026-11-24): clubs and eras mixed, against the grandes; same targets."""
    geral = dados_geral_de_teste()
    guloso, _ = _taxas(geral, motor.GERAL, gulosas)
    aleatorio, _ = _taxas(geral, motor.GERAL, aleatorias)
    assert 0.10 <= guloso <= 0.30, guloso
    assert aleatorio < 0.03, aleatorio
