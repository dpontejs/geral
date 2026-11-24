from collections import Counter

from geral.games.prancheta.palavras import DIFICULDADES, carregar
from geral.games.prancheta.tipos import normalizar


def test_minimos_do_banco_de_palavras():
    palavras = carregar().palavras
    assert len(palavras) >= 300
    por_dificuldade = Counter(p.dificuldade for p in palavras)
    for dificuldade in DIFICULDADES:
        assert por_dificuldade[dificuldade] >= 60, dificuldade


def test_sem_palavra_repetida():
    textos = Counter(normalizar(p.texto) for p in carregar().palavras)
    assert [t for t, n in textos.items() if n > 1] == []


def test_aceita_nao_colide_entre_palavras():
    dono: dict[str, str] = {}
    colisoes = []
    for palavra in carregar().palavras:
        for forma in {normalizar(f) for f in (palavra.texto, *palavra.aceita)}:
            if forma in dono and dono[forma] != palavra.texto:
                colisoes.append((forma, dono[forma], palavra.texto))
            dono[forma] = palavra.texto
    assert colisoes == []


def test_aceita_nao_repete_o_texto():
    for palavra in carregar().palavras:
        formas = [normalizar(a) for a in palavra.aceita]
        assert normalizar(palavra.texto) not in formas, palavra.texto
        assert all(formas), palavra.texto
