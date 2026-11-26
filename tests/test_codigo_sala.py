from geral.web.codigo_sala import normalizar


def test_normalizar_codigo_de_sala():
    assert normalizar(" K7M-2QX ") == "k7m2qx"
    assert normalizar("k7m 2qx") == "k7m2qx"
    for invalido in ("", "abc", "k7m2q1", "k7m2qx8", "k7m2q!"):
        assert normalizar(invalido) is None, invalido
