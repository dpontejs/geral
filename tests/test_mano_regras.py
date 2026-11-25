from random import Random

import pytest
from pydantic import ValidationError

from geral.games.mano.regras import (
    ALCANCE_SAIDA,
    ALTURA_BARREIRA,
    ALTURA_PULO,
    MEIA_LARGURA_POR_HOMEM,
    P_ANGULO,
    P_DEFESA_FALTA,
    RUIDO,
    cobertura,
    faixa_boa,
    resolver,
)
from geral.games.mano.tipos import Barreira, Chute, Defesa, Posicao

LONGE = Defesa(lado="direita", saida=False)


def test_faixa_estreita_perto_da_trave():
    assert faixa_boa((500, 300), falta=False) > faixa_boa((60, 300), falta=False)
    assert faixa_boa((500, 300), falta=False) > faixa_boa((500, 950), falta=False)
    assert faixa_boa((500, 300), falta=True) < faixa_boa((500, 300), falta=False)


def test_barra_na_faixa_vai_onde_mirou():
    lance = resolver(Chute(alvo=(150, 300), barra=500), LONGE, Random(1))
    assert abs(lance.onde[0] - 150) <= RUIDO
    assert abs(lance.onde[1] - 300) <= RUIDO
    assert lance.resultado == "gol"


def test_barra_fora_da_faixa_desvia():
    alvo = (150, 300)
    perto = resolver(
        Chute(alvo=alvo, barra=500 + faixa_boa(alvo, False) // 2 + 50), LONGE, Random(1)
    )
    longe = resolver(Chute(alvo=alvo, barra=1000), LONGE, Random(1))
    assert longe.onde[0] < perto.onde[0] < 150 + RUIDO
    assert longe.resultado in {"fora", "trave"}


def test_barra_nos_extremos_nao_quebra():
    for barra in (0, 1000):
        lance = resolver(Chute(alvo=(500, 0), barra=barra), LONGE, Random(4))
        assert lance.resultado in {"gol", "defesa", "trave", "fora"}


def test_goleiro_no_lado_certo_defende_ate_meia_altura():
    for y in (0, 300, ALTURA_PULO):
        chute = Chute(alvo=(150, y), barra=500)
        lance = resolver(chute, Defesa(lado="esquerda", saida=False), Random(2))
        assert lance.resultado == "defesa"


def test_angulo_so_em_parte():
    defesas = sum(
        resolver(
            Chute(alvo=(120, 900), barra=500), Defesa(lado="esquerda", saida=False), Random(s)
        ).resultado
        == "defesa"
        for s in range(2000)
    )
    assert abs(defesas / 2000 - P_ANGULO) <= 0.05


def test_fica_cobre_o_centro_inteiro():
    lance = resolver(Chute(alvo=(500, 950), barra=500), Defesa(lado="fica", saida=False), Random(5))
    assert lance.resultado == "defesa"


def test_saida_no_tempo_alcanca_o_vizinho():
    chute = Chute(alvo=(333 + ALCANCE_SAIDA - 20, 300), barra=500)
    assert resolver(chute, Defesa(lado="esquerda", saida=True), Random(3)).resultado == "defesa"
    assert resolver(chute, Defesa(lado="esquerda", saida=False), Random(3)).resultado == "gol"


def test_alvo_no_poste_e_trave_ou_fora():
    for alvo in ((0, 300), (1000, 500), (500, 1000)):
        for s in range(200):
            lance = resolver(Chute(alvo=alvo, barra=500), LONGE, Random(s))
            assert lance.resultado in {"trave", "fora"}


def test_chute_valida_os_limites():
    with pytest.raises(ValidationError):
        Chute(alvo=(-1, 300), barra=500)
    with pytest.raises(ValidationError):
        Chute(alvo=(500, 300), barra=1001)
    with pytest.raises(ValidationError):
        Chute(alvo=(500, 300), barra=500, curva=1.5)


BARREIRA = Barreira(n=4, x=500)
MEIA_LUA = Posicao(nome="meia_lua", desvio=0)


def _falta(chute: Chute, semente: int = 0, barreira: Barreira = BARREIRA, posicao=MEIA_LUA):
    return resolver(chute, LONGE, Random(semente), barreira=barreira, posicao=posicao)


def test_cobertura_cortada_no_gol():
    assert cobertura(Barreira(n=5, x=20)) == (0, 20 + 5 * MEIA_LARGURA_POR_HOMEM)
    assert cobertura(Barreira(n=5, x=990)) == (990 - 5 * MEIA_LARGURA_POR_HOMEM, 1000)
    assert cobertura(Barreira(n=2, x=500)) == (390, 610)


def test_barreira_bloqueia_rasteira():
    for s in range(50):
        chute = Chute(alvo=(450, 100), barra=500, trajetoria="rasteira")
        assert _falta(chute, s).resultado == "barreira"


def test_rasteira_fora_da_barreira_segue():
    lance = _falta(Chute(alvo=(150, 400), barra=500, trajetoria="rasteira"), 1)
    assert lance.onde[1] <= 150
    assert lance.resultado == "gol"


def test_pelo_lado_com_pouca_curva_bate_na_barreira():
    reta = Chute(alvo=(450, 300), barra=500, trajetoria="pelo_lado", curva=0.2)
    curvada = Chute(alvo=(450, 300), barra=500, trajetoria="pelo_lado", curva=0.8)
    assert _falta(reta, 2).resultado == "barreira"
    assert _falta(curvada, 2).resultado != "barreira"


def test_por_cima_fraco_bate_na_barreira():
    alvo = (450, ALTURA_BARREIRA + 100)
    na_faixa = Chute(alvo=alvo, barra=500, trajetoria="por_cima")
    fraco = Chute(alvo=alvo, barra=500 - faixa_boa(alvo, True) // 2 - 200, trajetoria="por_cima")
    assert _falta(na_faixa, 3).resultado == "gol"
    assert _falta(fraco, 3).resultado == "barreira"


def test_por_cima_forte_demais_sai():
    lance = _falta(Chute(alvo=(450, 850), barra=1000, trajetoria="por_cima"), 4)
    assert lance.onde[1] > 1000
    assert lance.resultado in {"fora", "trave"}


def test_posicao_desvia_a_bola():
    chute = Chute(alvo=(500, 700), barra=500, trajetoria="por_cima")
    sem = _falta(chute, 5)
    com = _falta(chute, 5, posicao=Posicao(nome="entrada_esquerda", desvio=60))
    assert com.onde[0] - sem.onde[0] == 60
    assert com.posicao is not None and com.barreira == BARREIRA


def test_falta_sem_trajetoria_da_erro():
    with pytest.raises(ValueError):
        _falta(Chute(alvo=(500, 700), barra=500))


def test_goleiro_tapado_na_falta_defende_so_em_parte():
    chute = Chute(alvo=(150, 300), barra=500, trajetoria="por_cima")
    defesa = Defesa(lado="esquerda", saida=False)
    longe = Barreira(n=2, x=900)
    defesas = sum(
        resolver(chute, defesa, Random(s), barreira=longe, posicao=MEIA_LUA).resultado == "defesa"
        for s in range(2000)
    )
    assert abs(defesas / 2000 - P_DEFESA_FALTA) <= 0.05
