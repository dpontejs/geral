from collections import Counter
from random import Random

import pytest

from geral.games.mano.bot import ACERTO_SAIDA, armar, chutar, defender
from geral.games.mano.regras import cobertura, resolver
from geral.games.mano.tipos import Barreira, Chute, Defesa, Posicao

REPETIDO = Chute(alvo=(150, 300), barra=500)


def _gols_contra(nivel: str) -> float:
    gols = 0
    for partida in range(500):
        rng = Random(partida)
        historico = []
        for _ in range(5):
            lance = resolver(REPETIDO, defender(nivel, historico, rng), rng)
            gols += lance.resultado == "gol"
            historico.append(lance)
    return gols / 2500


def test_bot_dificil_pune_quem_repete():
    assert _gols_contra("dificil") < 0.40


def test_bot_facil_nao_le_padrao():
    assert _gols_contra("facil") > 0.50


@pytest.mark.parametrize("nivel", ["facil", "medio", "dificil"])
def test_saida_do_bot_por_nivel(nivel):
    rng = Random(9)
    saidas = sum(defender(nivel, [], rng).saida for _ in range(5000))
    assert abs(saidas / 5000 - ACERTO_SAIDA[nivel]) <= 0.03


def test_dificil_sem_historico_nao_quebra():
    assert isinstance(defender("dificil", [], Random(0)), Defesa)
    assert isinstance(chutar("dificil", [], Random(0), barreira=None), Chute)


def test_armar_dentro_dos_limites():
    rng = Random(1)
    for nivel in ("facil", "medio", "dificil"):
        for _ in range(500):
            barreira = armar(nivel, rng)
            assert 2 <= barreira.n <= 5
            assert 0 <= barreira.x <= 1000


def test_bot_dificil_mira_onde_o_humano_nao_pula():
    historico = [
        resolver(REPETIDO, Defesa(lado="esquerda", saida=False), Random(s)) for s in range(3)
    ]
    rng = Random(2)
    for _ in range(300):
        chute = chutar("dificil", historico, rng, barreira=None)
        assert chute.alvo[0] >= 333
        assert 150 <= chute.alvo[0] <= 850 and chute.alvo[1] <= 850


def test_bot_medio_tem_mania_na_partida():
    rng = Random(4)
    lados = Counter(defender("medio", [], rng).lado for _ in range(2000))
    assert lados.most_common(1)[0][1] / 2000 > 0.65


def test_bot_na_falta_escolhe_trajetoria():
    barreira = Barreira(n=4, x=500)
    for nivel in ("facil", "medio", "dificil"):
        rng = Random(6)
        for _ in range(100):
            chute = chutar(nivel, [], rng, barreira=barreira)
            assert chute.trajetoria is not None
            resolver(chute, Defesa(lado="fica", saida=False), rng, barreira=barreira)
        assert chutar(nivel, [], rng, barreira=None).trajetoria is None


def test_bot_dificil_contorna_a_barreira():
    barreira = Barreira(n=5, x=500)
    inicio, fim = cobertura(barreira)
    historico = [
        resolver(REPETIDO, Defesa(lado="direita", saida=False), Random(s)) for s in range(3)
    ]
    rng = Random(8)
    for _ in range(200):
        chute = chutar("dificil", historico, rng, barreira=barreira)
        if inicio <= chute.alvo[0] <= fim:
            assert chute.trajetoria == "pelo_lado" and abs(chute.curva) >= 0.5


@pytest.mark.parametrize("desvio", [-80, 0, 80])
def test_bot_dificil_compensa_a_posicao_e_nao_bate_na_barreira(desvio):
    posicao = Posicao(nome="entrada_esquerda", desvio=desvio)
    historico = [
        resolver(REPETIDO, Defesa(lado="esquerda", saida=False), Random(s)) for s in range(3)
    ]
    rng = Random(10)
    for x in (150, 400, 500, 600, 850):
        barreira = Barreira(n=5, x=x)
        for _ in range(100):
            chute = chutar("dificil", historico, rng, barreira=barreira, posicao=posicao)
            chega = chute.alvo[0] + desvio
            assert 333 <= chega <= 850  # the third the human never dived to (fica/direita)
            defesa = Defesa(lado="esquerda", saida=False)
            lance = resolver(chute, defesa, rng, barreira=barreira, posicao=posicao)
            assert lance.resultado != "barreira"


CAVADINHA = Chute(alvo=(500, 500), barra=500, cavadinha=True)


def test_bot_dificil_fica_contra_quem_repete_a_cavadinha():
    gols = 0
    for partida in range(500):
        rng = Random(partida)
        historico = []
        for _ in range(5):
            lance = resolver(CAVADINHA, defender("dificil", historico, rng), rng)
            gols += lance.resultado == "gol"
            historico.append(lance)
    assert gols / 2500 < 0.24


@pytest.mark.parametrize("nivel", ["medio", "dificil"])
def test_bot_bate_cavadinha_de_vez_em_quando(nivel):
    rng = Random(11)
    historico = [resolver(REPETIDO, Defesa(lado="esquerda", saida=False), Random(1))]
    chutes = [chutar(nivel, historico if i % 2 else [], rng, barreira=None) for i in range(4000)]
    cavadinhas = [c for c in chutes if c.cavadinha]
    assert 0.02 <= len(cavadinhas) / 4000 <= 0.10
    assert all(c.alvo == (500, 500) for c in cavadinhas)


def test_bot_facil_e_falta_sem_cavadinha():
    rng = Random(12)
    assert not any(chutar("facil", [], rng, barreira=None).cavadinha for _ in range(2000))
    for nivel in ("medio", "dificil"):
        assert not any(
            chutar(nivel, [], rng, barreira=Barreira(n=3, x=500)).cavadinha for _ in range(2000)
        )


def test_bot_facil_nao_gasta_sorteio_com_cavadinha():
    # facil never chips: its draws stay the ones it had before the cavadinha existed
    rng, espelho = Random(5), Random(5)
    chute = chutar("facil", [], rng, barreira=None)
    x, y_barra = espelho.randint(0, 1000), espelho.randint(0, 1000)
    assert chute.alvo[0] == x and chute.barra == y_barra
