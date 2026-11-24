import pytest

from geral.games.prancheta.filtro import tem_palavrao
from geral.games.prancheta.tipos import normalizar


def test_normalizar():
    assert normalizar("  Pé-de-Anjo! ") == "pe de anjo"


def test_palavrao_palavra_inteira():
    assert tem_palavrao("vai tomar no cu, juiz")
    assert tem_palavrao("Seu MERDA!")
    assert not tem_palavrao("cutucada")
    assert not tem_palavrao("merdeiro")


def test_palavrao_expressao_de_duas_palavras():
    assert tem_palavrao("filho da puta")
    assert tem_palavrao("FILHA-DA-PUTA")


@pytest.mark.parametrize("texto", ["frango", "pipoqueiro", "cavadinha", "Bicicleta", "Pé de Anjo"])
def test_futebol_nao_e_palavrao(texto):
    assert not tem_palavrao(texto)
