import pytest

from geral.games.ptwiki import Stint
from geral.games.setea0.importacao import jogador_ptwiki, montar, passagens, posicoes

ABC = "Q338285"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Goleiro", ["GOL"]),
        ("Zagueiro", ["ZAG"]),
        ("Lateral-direito", ["LAT"]),
        ("Volante", ["MEI"]),
        ("Meia-atacante", ["MEI"]),
        ("Centroavante", ["ATA"]),
        ("Ponta-esquerda", ["ATA"]),
        ("Zagueiro, volante e lateral-direito", ["ZAG", "MEI", "LAT"]),
        ("Meia e atacante", ["MEI", "ATA"]),
        ("Lateral-esquerdo, Volante e MeiaAtacante", ["LAT", "MEI"]),
        ("Ponta-de-lança", ["MEI"]),
        ("Coordenador de futebol e volante", ["MEI"]),
        ("", []),
    ],
)
def test_posicoes_normaliza(texto, esperado):
    assert posicoes(texto) == esperado


def test_so_passagens_no_clube_e_funde_consecutivas():
    stints = [
        Stint(1983, 1985, ABC),
        Stint(1986, 1987, "Q1"),  # a loan elsewhere
        Stint(1988, 1990, ABC),
        Stint(1991, 1992, ABC),  # consecutive: one stay
        Stint(None, None, ABC),  # years unreadable
    ]
    assert passagens(stints, ABC) == [(1983, 1985), (1988, 1992)]


def pagina(ano: str, clubes: str, posicao: str = "Atacante", extra: str = "") -> dict:
    return {
        "titulo": "Fulano (futebolista)",
        "qid": "Q99",
        "text": f"{{{{Info/Futebolista\n|nome = Fulano\n|posição = [[{posicao}]]\n"
        f"|ano = {ano}\n|clubes = {clubes}\n{extra}}}}}\nTexto.",
        "clubes": clubes,
        "ids": {"ABC Futebol Clube": ABC, "América Futebol Clube (Rio Grande do Norte)": "Q1"},
    }


def test_pagina_sem_infobox_vira_relatorio():
    sem = {"titulo": "X", "qid": "Q9", "text": "Só texto.", "clubes": "", "ids": {}}
    assert jogador_ptwiki(sem, ABC, 3) == (None, "sem infobox")
    torta = pagina("1990 <br /> 1991", "[[ABC Futebol Clube|ABC]]")
    assert jogador_ptwiki(torta, ABC, 3) == (None, "anos e clubes não batem")
    fora = pagina("1990", "[[América Futebol Clube (Rio Grande do Norte)|América]]")
    assert jogador_ptwiki(fora, ABC, 3) == (None, "sem anos no clube")
    sem_posicao = pagina("1990", "[[ABC Futebol Clube|ABC]]", posicao="Treinador")
    assert jogador_ptwiki(sem_posicao, ABC, 3) == (None, "sem posição")


def test_ida_e_volta_contam_as_duas():
    ida_e_volta = pagina(
        "1990–1992 <br /> 1993–1997 <br /> 1998",
        "[[ABC Futebol Clube|ABC]] <br /> [[América Futebol Clube (Rio Grande do Norte)|América]]"
        " <br /> [[ABC Futebol Clube|ABC]]",
        extra="|selecaonacional = [[Seleção Brasileira de Futebol|Brasil]]\n",
    )
    jogador, motivo = jogador_ptwiki(ida_e_volta, ABC, 7)
    assert motivo is None
    assert jogador == {
        "id": "Q99",
        "nome": "Fulano",
        "posicoes": ["ATA"],
        "passagens": [(1990, 1992), (1998, 1998)],
        "fama": 7,
        "selecao": True,
    }


def test_selecao_de_base_nao_conta():
    base = pagina(
        "1990",
        "[[ABC Futebol Clube|ABC]]",
        extra="|selecaonacional = [[Seleção Brasileira de Futebol Sub-20|Brasil <small>Sub-20"
        "</small>]]<br />[[Seleção Brasileira de Futebol|Brasil]] <small>Sub-17</small>\n",
    )
    assert jogador_ptwiki(base, ABC, 1)[0]["selecao"] is False


def bruto(id_, fama, passagens=((1990, 1995),), posicoes=("ATA",), selecao=False):
    return {
        "id": id_,
        "nome": id_,
        "posicoes": list(posicoes),
        "passagens": list(passagens),
        "fama": fama,
        "selecao": selecao,
    }


def test_montar_versao_muda_com_os_dados():
    brutos = {"abc": [bruto("Q1", 1), bruto("Q2", 50)], "ceara": [bruto("Q3", 9, passagens=())]}
    dados = montar(brutos, {})
    assert dados.clubes["abc"].nome == "ABC"
    q1, q2 = dados.clubes["abc"].jogadores
    assert q2.forca > q1.forca  # fame relative to the club
    assert dados.clubes["ceara"].jogadores[0].passagens == []
    assert dados == montar(brutos, {})
    outro = montar({**brutos, "abc": [bruto("Q1", 1), bruto("Q2", 50, posicoes=["MEI"])]}, {})
    assert len(dados.versao) == 12
    assert outro.versao != dados.versao


def test_idolo_tem_a_forca_fixada():
    dados = montar({"abc": [bruto("Q1", 1), bruto("Q2", 50)]}, {"abc": {"Q1": 95}})
    assert dados.clubes["abc"].jogadores[0].forca == 95


def test_jogadores_velha_mapeia_posicoes_e_nao_tem_passagens():
    from geral.games.setea0.importacao import jogadores_velha
    from geral.games.velha.base import Base, Player

    def player(id_, posicoes, clubes):
        return Player(id_, id_, "", posicoes, (), 10, frozenset(clubes), True, False)

    base = Base(
        players={
            "Q1": player("Q1", ("goleiro",), {"Qc"}),
            "Q2": player("Q2", ("meio-campo", "lateral"), {"Qc"}),
            "Q3": player("Q3", ("atacante",), {"Qoutro"}),
            "Q4": player("Q4", (), {"Qc"}),  # no position: can't be lined up
        },
        clubs={},
        countries={},
    )
    assert jogadores_velha(base, "Qc") == [
        {
            "id": "Q1",
            "nome": "Q1",
            "posicoes": ["GOL"],
            "passagens": [],
            "fama": 10,
            "selecao": True,
        },
        {
            "id": "Q2",
            "nome": "Q2",
            "posicoes": ["MEI", "LAT"],
            "passagens": [],
            "fama": 10,
            "selecao": True,
        },
    ]
