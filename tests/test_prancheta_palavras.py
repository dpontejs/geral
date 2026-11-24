import random

import pytest

from geral.games.prancheta.palavras import BancoToml, carregar
from geral.games.prancheta.tipos import Palavra

PEQUENO = """
[[palavra]]
texto = "Gol olímpico"
aceita = ["gol de escanteio"]
dificuldade = "media"
tipo = "lance"

[[palavra]]
texto = "Bicicleta"
dificuldade = "facil"
tipo = "lance"

[[palavra]]
texto = "Apito"
dificuldade = "facil"
tipo = "objeto"

[[palavra]]
texto = "VAR"
dificuldade = "facil"
tipo = "objeto"

[[palavra]]
texto = "Folha seca"
dificuldade = "dificil"
tipo = "lance"

[[palavra]]
texto = "Cera"
dificuldade = "media"
tipo = "lance"
"""


@pytest.fixture
def banco(tmp_path) -> BancoToml:
    path = tmp_path / "palavras.toml"
    path.write_text(PEQUENO, encoding="utf-8")
    return carregar(path)


def _palavra(banco: BancoToml, texto: str) -> Palavra:
    return next(p for p in banco.palavras if p.texto == texto)


def test_carrega_e_valida_dominio(banco, tmp_path):
    gol = _palavra(banco, "Gol olímpico")
    assert gol == Palavra("Gol olímpico", ("gol de escanteio",), "media", "lance")
    assert _palavra(banco, "Apito").aceita == ()

    ruim = tmp_path / "ruim.toml"
    ruim.write_text('[[palavra]]\ntexto = "X"\ndificuldade = "facil"\ntipo = "bolo"\n')
    with pytest.raises(ValueError, match="tipo"):
        carregar(ruim)
    ruim.write_text('[[palavra]]\ntexto = "X"\ndificuldade = "moleza"\ntipo = "lance"\n')
    with pytest.raises(ValueError, match="dificuldade"):
        carregar(ruim)


def test_carregar_padrao_usa_o_arquivo_ao_lado():
    assert carregar() is carregar()
    assert carregar().palavras


def test_opcoes_uma_por_dificuldade_em_ordem(banco):
    for semente in range(20):
        opcoes = banco.opcoes(random.Random(semente), set())
        assert [p.dificuldade for p in opcoes] == ["facil", "media", "dificil"]


def test_opcoes_respeita_usadas(banco):
    usadas = {"Bicicleta", "Apito", "Cera"}
    for semente in range(20):
        opcoes = banco.opcoes(random.Random(semente), usadas)
        assert [p.texto for p in opcoes] == ["VAR", "Gol olímpico", "Folha seca"]


def test_opcoes_sem_repetir_ate_esgotar_e_depois_libera(banco):
    rng = random.Random(1)
    usadas: set[str] = set()
    faceis = []
    for _ in range(3):
        escolhida = banco.opcoes(rng, usadas)[0]
        faceis.append(escolhida.texto)
        usadas.add(escolhida.texto)
    assert sorted(faceis) == ["Apito", "Bicicleta", "VAR"]
    # Todas as fáceis usadas: a dificuldade libera de novo, as outras seguem iguais.
    opcoes = banco.opcoes(rng, usadas)
    assert opcoes[0].texto in faceis
    assert [p.dificuldade for p in opcoes] == ["facil", "media", "dificil"]


def test_julgar_normaliza_acento_e_apelido(banco):
    gol = _palavra(banco, "Gol olímpico")
    assert banco.julgar("gol olimpico", gol) == "certo"
    assert banco.julgar("  GOL OLÍMPICO! ", gol) == "certo"
    assert banco.julgar("Gol de escanteio", gol) == "certo"


def test_texto_a_mais_e_trave(banco):
    bicicleta = _palavra(banco, "Bicicleta")
    assert banco.julgar("bicicleta linda", bicicleta) == "trave"
    assert banco.julgar("que bicicleta", bicicleta) == "trave"


def test_quase_e_trave(banco):
    bicicleta = _palavra(banco, "Bicicleta")
    assert banco.julgar("bicicléta", bicicleta) == "certo"
    assert banco.julgar("biciclta", bicicleta) == "trave"
    assert banco.julgar("biscicleta", bicicleta) == "trave"


def test_palavra_curta_so_trave_com_uma_letra_trocada(banco):
    cera = _palavra(banco, "Cera")
    assert banco.julgar("cerq", cera) == "trave"
    assert banco.julgar("cer", cera) == "trave"
    assert banco.julgar("cervo", cera) == "errado"
    assert banco.julgar("pera", cera) == "trave"
    assert banco.julgar("peru", cera) == "errado"
    var = _palavra(banco, "VAR")
    assert banco.julgar("bar", var) == "trave"
    assert banco.julgar("mar", var) == "trave"
    assert banco.julgar("vara", var) == "trave"
    assert banco.julgar("vez", var) == "errado"
    # Contém a palavra curta inteira, mas é outra palavra: não entrega nada.
    assert banco.julgar("variante", var) == "errado"
    assert banco.julgar("o var", var) == "trave"


def test_longe_e_errado(banco):
    assert banco.julgar("escanteio", _palavra(banco, "Bicicleta")) == "errado"
    assert banco.julgar("", _palavra(banco, "Apito")) == "errado"
    assert banco.julgar("!!!", _palavra(banco, "Apito")) == "errado"
