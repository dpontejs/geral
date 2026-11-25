import pytest

from geral.games.mano.disputa import SERIE, Disputa


def _jogar(disputa: Disputa, gols: list[bool]) -> Disputa:
    for gol in gols:
        disputa.registrar(gol)
    return disputa


def test_batedor_alterna_comecando_pelo_zero():
    disputa = Disputa()
    assert disputa.batedor() == 0
    disputa.registrar(True)
    assert disputa.batedor() == 1
    disputa.registrar(False)
    assert disputa.batedor() == 0
    assert disputa.cobrancas == [(0, True), (1, False)]


def test_disputa_alternada_e_morte_subita():
    # 4x4 after 5 each: player 0 misses the 1st, player 1 misses the 2nd
    serie = [False, True, True, False] + [True, True] * 3
    disputa = _jogar(Disputa(), serie)
    assert len(disputa.cobrancas) == 2 * SERIE
    assert disputa.placar() == (4, 4)
    assert not disputa.acabou()
    _jogar(disputa, [True, True])
    assert not disputa.acabou()
    _jogar(disputa, [False, True])
    assert disputa.acabou()
    assert disputa.vencedor() == 1
    assert disputa.placar() == (5, 6)


def test_disputa_acaba_quando_nao_da_mais_para_alcancar():
    disputa = _jogar(Disputa(), [True, False, True, False, True])
    assert not disputa.acabou()
    disputa.registrar(False)
    assert disputa.placar() == (3, 0)
    assert disputa.acabou()
    assert disputa.vencedor() == 0


def test_disputa_acaba_no_gol_de_quem_lidera():
    # after 6 kicks 0 has 3/3 and 1 has 1/3 (can still reach 3); 0's 4th goal ends it
    disputa = _jogar(Disputa(), [True, False, True, False, True, True])
    assert not disputa.acabou()
    disputa.registrar(True)
    assert disputa.placar() == (4, 1)
    assert disputa.acabou()


def test_morte_subita_so_decide_apos_o_par():
    disputa = _jogar(Disputa(), [True, True] * SERIE)
    disputa.registrar(True)
    assert not disputa.acabou()
    disputa.registrar(True)
    assert not disputa.acabou()
    disputa.registrar(False)
    assert not disputa.acabou()
    disputa.registrar(False)
    assert not disputa.acabou()
    assert disputa.vencedor() is None


def test_quem_sai_perde_por_wo():
    disputa = _jogar(Disputa(), [True, False, True])
    disputa.wo(1)
    assert disputa.acabou()
    assert disputa.vencedor() == 0
    assert disputa.placar() == (2, 0)


def test_wo_de_quem_esta_ganhando():
    disputa = _jogar(Disputa(), [True, False])
    disputa.wo(0)
    assert disputa.vencedor() == 1


def test_registrar_depois_do_fim_da_erro():
    disputa = _jogar(Disputa(), [True, False] * 3)
    assert disputa.acabou()
    with pytest.raises(ValueError):
        disputa.registrar(True)
    with pytest.raises(ValueError):
        Disputa().wo(2)
