from random import Random

import pytest
from pydantic import ValidationError

from geral.games.mano.regras import (
    ALCANCE_SAIDA,
    ALTURA_PULO,
    P_ANGULO,
    RUIDO,
    faixa_boa,
    resolver,
)
from geral.games.mano.tipos import Chute, Defesa

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
