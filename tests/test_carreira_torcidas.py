from test_carreira_variedade import _temporada

from geral.games.carreira.dados import carregar
from geral.games.carreira.final import vereditos


def _anos(clube_id: str, nome: str, de: int, ate: int, **extra):
    return [_temporada(i, nome, clube_id, **extra) for i in range(de, ate)]


def test_traidor_quem_vai_direto_para_o_rival() -> None:
    temporadas = _anos("abc", "ABC", 16, 20) + _anos("america-rn", "América-RN", 20, 30)

    v = vereditos(carregar(), temporadas)

    assert [x.clube for x in v] == ["ABC", "América-RN"]
    assert v[0].veredito == "Traidor" and "ABC" in v[0].frase


def test_idolo_campeao_em_branco_e_respeitado() -> None:
    temporadas = (
        _anos("sport", "Sport", 16, 22, titulos=["Campeonato Pernambucano"])
        + _anos("bahia", "Bahia", 22, 24, titulos=[], jogos=40, gols=3)
        + [_temporada(24, "Getafe", "getafe", jogos=10, titulos=[])]
        + [_temporada(25, "Vasco", "vasco", jogos=20, titulos=["Campeonato Carioca"])]
    )

    v = {x.clube: x for x in vereditos(carregar(), temporadas)}

    assert v["Sport"].veredito == "Ídolo" and v["Sport"].titulos == 6
    assert v["Bahia"].veredito == "Respeitado"
    assert v["Getafe"].veredito == "Passou em branco"
    assert v["Vasco"].veredito == "Campeão"
    assert all(x.frase for x in v.values())


def test_carreira_terminada_conta_uma_vez_para_o_clube_de_base(tmp_path) -> None:
    from datetime import UTC, datetime

    from geral.web.carreira_placar import PlacarStore

    placar, agora = PlacarStore(tmp_path / "s.db"), datetime(2026, 11, 17, tzinfo=UTC)

    assert placar.registrar("codigo-1", "abc", 70, agora) is True
    assert placar.registrar("codigo-1", "abc", 70, agora) is False  # the same career again
    placar.registrar("codigo-2", "abc", 90, agora)
    placar.registrar("codigo-3", "flamengo", 60, agora)

    abc = next(linha for linha in placar.ranking(20) if linha.clube == "abc")
    assert (abc.carreiras, abc.media, abc.lendas, abc.posicao) == (2, 80, 1, 1)


def test_placar_ordena_por_carreiras_com_media_e_lendas(tmp_path) -> None:
    from datetime import UTC, datetime

    from geral.web.carreira_placar import PlacarStore

    placar, agora = PlacarStore(tmp_path / "s.db"), datetime(2026, 11, 17, tzinfo=UTC)
    for i in range(3):
        placar.registrar(f"n{i}", "nautico", 50, agora)
    for i in range(2):
        placar.registrar(f"f{i}", "flamengo", 95, agora)

    linhas = placar.ranking(20)

    assert [(x.clube, x.carreiras, x.lendas, x.posicao) for x in linhas] == [
        ("nautico", 3, 0, 1),
        ("flamengo", 2, 2, 2),
    ]
    assert placar.posicao("flamengo") == (2, 2)
    assert placar.posicao("abc") == (0, None)


def test_emprestimo_para_o_rival_nao_e_traicao() -> None:
    temporadas = (
        _anos("abc", "ABC", 16, 20)
        + [_temporada(20, "América-RN", "america-rn", chegada="Emprestado pelo ABC")]
        + [_temporada(21, "ABC", "abc", chegada="Voltou do empréstimo ao América-RN")]
        + _anos("abc", "ABC", 22, 26)
    )

    assert all(v.veredito != "Traidor" for v in vereditos(carregar(), temporadas))


def test_carreira_guardada_uma_vez_e_lida_pelo_codigo(tmp_path) -> None:
    from datetime import UTC, datetime

    from geral.web.carreira_placar import PlacarStore

    placar, agora = PlacarStore(tmp_path / "s.db"), datetime(2026, 11, 23, tzinfo=UTC)

    assert placar.guardada("codigo-1") is None
    placar.guardar("codigo-1", '{"final": {"rotulo": "Lenda"}}', agora)
    placar.guardar("codigo-1", '{"final": {"rotulo": "outra"}}', agora)  # the same career again

    assert placar.guardada("codigo-1") == '{"final": {"rotulo": "Lenda"}}'
    assert placar.guardada("codigo-2") is None
