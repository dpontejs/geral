from random import Random

import pytest
from pydantic import ValidationError

from geral.games.mano.regras import (
    ALCANCE_FRACO,
    ALCANCE_SAIDA,
    ALTURA_BARREIRA,
    ALTURA_PULO,
    FAIXA_CAVADINHA,
    FAIXA_MAX,
    FAIXA_PENALTI_MAX,
    FAIXA_PENALTI_MIN,
    FATOR_FALTA,
    MEIA_LARGURA_POR_HOMEM,
    P_ANGULO,
    QUEDA_POR_ERRO,
    RUIDO,
    SUBIDA_POR_ERRO,
    cobertura,
    faixa_boa,
    resolver,
)
from geral.games.mano.tipos import Barreira, Chute, Defesa, Posicao

LONGE = Defesa(lado="direita", saida=False)


def test_faixa_estreita_perto_da_trave():
    assert faixa_boa((500, 300), falta=False) > faixa_boa((60, 300), falta=False)
    assert faixa_boa((500, 300), falta=False) > faixa_boa((500, 950), falta=False)
    assert faixa_boa((500, 300), falta=True) == round(FAIXA_MAX * FATOR_FALTA)


def test_faixa_do_penalti_e_mais_estreita_que_a_da_falta():
    # the penalty got its own band (dev, 2026-11-26): narrower overall, much narrower in the corners
    for alvo in ((500, 300), (90, 300), (910, 850), (500, 950)):
        assert faixa_boa(alvo, falta=False) < faixa_boa(alvo, falta=True)
    assert faixa_boa((90, 300), falta=False) <= FAIXA_PENALTI_MIN + 100
    assert faixa_boa((500, 300), falta=False) == FAIXA_PENALTI_MAX


def test_barra_na_faixa_vai_onde_mirou():
    lance = resolver(Chute(alvo=(150, 300), barra=500), LONGE, Random(1))
    assert abs(lance.onde[0] - 150) <= RUIDO
    assert abs(lance.onde[1] - 300) <= RUIDO
    assert lance.resultado == "gol"


def test_barra_fora_da_faixa_desvia():
    # above the band the ball climbs from the aim: a little, then the crossbar, then over
    alvo = (150, 600)
    topo = 500 + faixa_boa(alvo, False) // 2
    perto = resolver(Chute(alvo=alvo, barra=topo + 30), LONGE, Random(1))
    longe = resolver(Chute(alvo=alvo, barra=1000), LONGE, Random(1))
    assert 600 + RUIDO < perto.onde[1] < longe.onde[1]
    assert abs(perto.onde[0] - 150) <= RUIDO and abs(longe.onde[0] - 150) <= RUIDO
    assert longe.resultado == "fora"


def test_um_pouco_acima_da_faixa_no_alto_e_travessao():
    alvo = (500, 850)
    topo = 500 + faixa_boa(alvo, False) // 2
    erro = round((1000 - 850) / SUBIDA_POR_ERRO)
    resultados = {
        resolver(Chute(alvo=alvo, barra=topo + erro), LONGE, Random(s)).resultado for s in range(50)
    }
    assert resultados == {"trave"}


def test_abaixo_da_faixa_e_chute_fraco_que_o_goleiro_alcanca():
    # aimed at the middle third, near the left: in the band the left dive misses it
    alvo = (333 + 40, 300)
    base = 500 - faixa_boa(alvo, False) // 2
    esquerda = Defesa(lado="esquerda", saida=False)
    assert resolver(Chute(alvo=alvo, barra=base), esquerda, Random(1)).resultado == "gol"
    fraco = resolver(Chute(alvo=alvo, barra=base - 70), esquerda, Random(1))
    assert fraco.resultado == "defesa"
    assert abs(fraco.onde[0] - alvo[0]) <= RUIDO
    assert abs(fraco.onde[1] - (300 - 70 * QUEDA_POR_ERRO)) <= RUIDO  # a weak ball drops


def test_chute_fraco_nao_e_defesa_automatica():
    # the weak shot's extra reach stops at about the exit's: the far corner is still a goal
    for s in range(50):
        lance = resolver(
            Chute(alvo=(900, 300), barra=0), Defesa(lado="esquerda", saida=True), Random(s)
        )
        assert lance.resultado == "gol"
    perto = (333 + ALCANCE_SAIDA + ALCANCE_FRACO + 30, 300)
    lance = resolver(Chute(alvo=perto, barra=0), Defesa(lado="esquerda", saida=True), Random(1))
    assert lance.resultado == "gol"


def test_chute_fraco_no_alto_cai_e_o_goleiro_pega():
    # a weak ball does not reach the top corner: it drops, and the extra reach has no height limit
    def defesas(barra: int) -> float:
        direita = Defesa(lado="direita", saida=False)
        lances = [
            resolver(Chute(alvo=(950, 950), barra=barra), direita, Random(s)) for s in range(500)
        ]
        return sum(lance.resultado == "defesa" for lance in lances) / 500

    assert defesas(0) > 0.9
    assert defesas(500) < 0.4
    fraco = resolver(Chute(alvo=(950, 950), barra=0), LONGE, Random(1))
    assert fraco.onde[1] < 950 - QUEDA_POR_ERRO * 100


def test_chute_fraco_alto_no_vizinho_tambem_e_alcancado():
    alvo = (333 + 40, 700)
    base = 500 - faixa_boa(alvo, False) // 2
    esquerda = Defesa(lado="esquerda", saida=False)
    lance = resolver(Chute(alvo=alvo, barra=base - 70), esquerda, Random(1))
    assert lance.resultado == "defesa"


def test_cavadinha_mira_o_meio():
    chute = Chute(alvo=(100, 900), barra=500, cavadinha=True)
    assert chute.alvo == (500, 500)


def test_cavadinha_contra_quem_fica_e_defesa_e_contra_quem_pula_e_gol():
    chute = Chute(alvo=(500, 500), barra=500, cavadinha=True)
    for s in range(20):
        assert resolver(chute, Defesa(lado="fica", saida=False), Random(s)).resultado == "defesa"
        for lado in ("esquerda", "direita"):
            for saida in (False, True):
                lance = resolver(chute, Defesa(lado=lado, saida=saida), Random(s))
                assert lance.resultado == "gol"


def test_cavadinha_tem_faixa_mais_estreita():
    assert FAIXA_CAVADINHA < faixa_boa((500, 500), falta=False)
    pula = Defesa(lado="direita", saida=False)
    alta = Chute(alvo=(500, 500), barra=500 + FAIXA_CAVADINHA // 2 + 20, cavadinha=True)
    baixa = Chute(alvo=(500, 500), barra=500 - FAIXA_CAVADINHA // 2 - 20, cavadinha=True)
    lance = resolver(alta, pula, Random(1))
    assert lance.resultado == "fora" and lance.onde[1] > 1000
    assert resolver(baixa, pula, Random(1)).resultado == "defesa"


def test_cavadinha_so_no_penalti():
    chute = Chute(alvo=(500, 500), barra=500, trajetoria="por_cima", cavadinha=True)
    with pytest.raises(ValueError):
        resolver(chute, LONGE, Random(0), barreira=BARREIRA, posicao=MEIA_LUA)


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


def _falta(
    chute: Chute,
    semente: int = 0,
    barreira: Barreira = BARREIRA,
    posicao=MEIA_LUA,
    defesa: Defesa = LONGE,
):
    return resolver(chute, defesa, Random(semente), barreira=barreira, posicao=posicao)


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
    reta = Chute(alvo=(450, 300), barra=500, trajetoria="pelo_lado", curva=-0.2)
    curvada = Chute(alvo=(450, 300), barra=500, trajetoria="pelo_lado", curva=-0.8)
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


def test_curva_do_lado_errado_bate_na_barreira():
    # wall at 500 covers 280-720: right of its centre bends right (+), left of it bends left (-)
    for alvo_x, certa in ((620, 0.8), (380, -0.8)):
        acerta = Chute(alvo=(alvo_x, 300), barra=500, trajetoria="pelo_lado", curva=certa)
        erra = Chute(alvo=(alvo_x, 300), barra=500, trajetoria="pelo_lado", curva=-certa)
        assert _falta(acerta, 6).resultado != "barreira"
        assert _falta(erra, 6).resultado == "barreira"


def test_penalti_ignora_trajetoria_curva_e_posicao():
    simples = Chute(alvo=(500, 800), barra=500)
    enfeitado = Chute(alvo=(500, 800), barra=500, trajetoria="rasteira", curva=0.9)
    torta = Posicao(nome="entrada_direita", desvio=80)
    a = resolver(simples, LONGE, Random(7))
    b = resolver(enfeitado, LONGE, Random(7), posicao=torta)
    assert b.onde == a.onde and b.resultado == a.resultado
    assert b.posicao is None


def test_na_falta_o_goleiro_e_o_do_penalti():
    longe = Barreira(n=2, x=900)
    casos = [
        (Chute(alvo=(150, ALTURA_PULO - 2 * RUIDO), barra=500), "esquerda", False),
        (Chute(alvo=(120, 900), barra=500), "esquerda", False),
        (Chute(alvo=(333 + ALCANCE_SAIDA - 2 * RUIDO, 300), barra=500), "esquerda", True),
        (Chute(alvo=(500, 950), barra=500), "fica", False),
    ]
    for chute, lado, saida in casos:
        defesa = Defesa(lado=lado, saida=saida)
        falta = chute.model_copy(update={"trajetoria": "por_cima"})
        for s in range(200):
            penalti = resolver(chute, defesa, Random(s))
            na_falta = _falta(falta, s, barreira=longe, defesa=defesa)
            assert na_falta.resultado == penalti.resultado
