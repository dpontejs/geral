import pytest

from geral.games.setea0.forca import forca, percentis


def test_forca_cresce_com_fama_anos_e_selecao():
    base = forca(0.5, 3, False)
    assert forca(0.9, 3, False) > base
    assert forca(0.5, 6, False) > base
    assert forca(0.5, 3, True) > base
    assert forca(0.5, None, False) == forca(0.5, 4, False)


def test_forca_entre_1_e_99():
    assert forca(1.0, 30, True) == 99
    assert 1 <= forca(0.0, 0, False) <= 99
    assert forca(0.0, 0, False) == 35


def test_percentil_e_relativo_ao_clube():
    assert percentis([1, 1, 5, 50]) == pytest.approx([0, 0, 0.67, 1], abs=0.01)
    assert percentis([7]) == [0.5]
    assert percentis([]) == []
