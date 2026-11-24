import pytest
from prancheta_fakes import em, sala_com, traco

from geral.games.prancheta.sala import ErroSala, Evento

COMECAR = {"tipo": "comecar"}


def _status(excinfo) -> int:
    return excinfo.value.status


def em_desenho(n: int = 3, indice: int = 0, **kw):
    """Room with `n` players, game started and player 1 drawing the chosen word."""
    sala, tokens = sala_com(n, **kw)
    sala.agir(1, COMECAR, em(0))
    sala.agir(1, {"tipo": "escolher", "indice": indice}, em(1))
    return sala, tokens


# --- Task 2: entrar, começar, escolher e desenhar ---


def test_anfitriao_comeca_com_dois():
    sala, _ = sala_com(2)
    assert sala.foto(2, em(0))["fase"] == "espera"
    assert [j["anfitriao"] for j in sala.foto(2, em(0))["jogadores"]] == [True, False]
    eventos = sala.agir(1, COMECAR, em(0))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2}
    foto = sala.foto(2, em(0))
    assert (foto["fase"], foto["rodada"], foto["rodadas"], foto["desenhista"]) == (
        "escolha",
        1,
        1,
        1,
    )
    assert foto["prazo"] == em(15).isoformat()
    assert foto["agora"] == em(0).isoformat()
    assert foto["voce"] == 2


def test_so_anfitriao_comeca_409():
    sala, _ = sala_com(2)
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, COMECAR, em(0))
    assert _status(excinfo) == 409
    sozinho, _ = sala_com(1)
    with pytest.raises(ErroSala) as excinfo:
        sozinho.agir(1, COMECAR, em(0))
    assert _status(excinfo) == 409


def test_opcoes_so_para_quem_desenha():
    sala, _ = sala_com(3)
    eventos = sala.agir(1, COMECAR, em(0))
    por_jogador = {e.para: e.dados for e in eventos if e.tipo == "estado"}
    assert por_jogador[1]["opcoes"] == [
        {"texto": "Bicicleta", "dificuldade": "facil"},
        {"texto": "Gol olímpico", "dificuldade": "media"},
        {"texto": "Frasqueira", "dificuldade": "dificil"},
    ]
    assert por_jogador[2]["opcoes"] is None and por_jogador[3]["opcoes"] is None
    assert sala.foto(2, em(0))["opcoes"] is None
    sala.agir(1, {"tipo": "escolher", "indice": 2}, em(1))
    assert sala.foto(1, em(1))["palavra"] == "Frasqueira"
    assert sala.foto(1, em(1))["opcoes"] is None
    assert sala.foto(2, em(1))["palavra"] is None
    assert sala.foto(2, em(1))["fase"] == "desenho"
    assert sala.foto(2, em(1))["prazo"] == em(81).isoformat()


def test_escolher_fora_da_vez_ou_indice_invalido():
    sala, _ = sala_com(2)
    sala.agir(1, COMECAR, em(0))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, {"tipo": "escolher", "indice": 0}, em(1))
    assert _status(excinfo) == 409
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, {"tipo": "escolher", "indice": 3}, em(1))
    assert _status(excinfo) == 422


def test_escolha_vencida_sorteia():
    sala, _ = sala_com(2)
    sala.agir(1, COMECAR, em(0))
    assert sala.avancar(em(14.5)) == []
    eventos = sala.avancar(em(15))
    assert {e.tipo for e in eventos} == {"estado"}
    assert sala.foto(1, em(15))["fase"] == "desenho"
    assert sala.foto(1, em(15))["palavra"] in {"Bicicleta", "Gol olímpico", "Frasqueira"}


def test_traco_fora_da_vez_409():
    sala, _ = sala_com(2)
    sala.agir(1, COMECAR, em(0))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, traco(1, [[10, 10]]), em(1))
    assert _status(excinfo) == 409
    sala.agir(1, {"tipo": "escolher", "indice": 0}, em(1))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, traco(1, [[10, 10]]), em(2))
    assert _status(excinfo) == 409


def test_traco_repassado_exceto_desenhista():
    sala, _ = em_desenho()
    seq = sala.foto(2, em(2))["seq"]
    eventos = sala.agir(1, traco(7, [[0, 0], [1000, 750]], fim=False), em(2))
    assert eventos == [
        Evento(
            "traco",
            {
                "id": 7,
                "cor": 1,
                "esp": 2,
                "pts": [[0, 0], [1000, 750]],
                "fim": False,
                "seq": seq + 1,
            },
            exceto=1,
        )
    ]
    sala.agir(1, traco(7, [[500, 500]]), em(2.1))
    assert sala.foto(2, em(3))["tracos"] == [
        {"id": 7, "cor": 1, "esp": 2, "pts": [[0, 0], [1000, 750], [500, 500]], "fim": True}
    ]


@pytest.mark.parametrize(
    "acao",
    [
        traco(1, [[0, 0]] * 65),
        traco(1, [[0, 1001]]),
        traco(1, [[-1, 0]]),
        traco(1, [[0.5, 0]]),
        traco(1, [[0, 0, 0]]),
        traco(1, [[0, 0]], cor=8),
        traco(1, [[0, 0]], esp=4),
        {"tipo": "traco", "id": 1, "cor": 1, "esp": 1, "pts": [[0, 0]]},
        {"tipo": "traco", "id": "1", "cor": 1, "esp": 1, "pts": [[0, 0]], "fim": True},
    ],
)
def test_traco_invalido_422(acao):
    sala, _ = em_desenho()
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, acao, em(2))
    assert _status(excinfo) == 422
    assert sala.foto(2, em(2))["tracos"] == []


def test_traco_com_teto_de_pontos_por_desenho():
    sala, _ = em_desenho()
    pedaco = [[1, 1]] * 64
    for i in range(312):  # 19 968 pontos
        sala.agir(1, traco(i, pedaco), em(2 + i * 0.05))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, traco(999, pedaco), em(30))
    assert _status(excinfo) == 422
    sala.agir(1, traco(999, [[1, 1]] * 32), em(30))


def test_desfazer_e_limpar():
    sala, _ = em_desenho()
    sala.agir(1, traco(1, [[1, 1]]), em(2))
    sala.agir(1, traco(2, [[2, 2]]), em(3))
    eventos = sala.agir(1, {"tipo": "desfazer"}, em(4))
    assert [(e.tipo, e.dados["id"], e.exceto) for e in eventos] == [("desfazer", 2, 1)]
    assert [t["id"] for t in sala.foto(2, em(4))["tracos"]] == [1]
    eventos = sala.agir(1, {"tipo": "limpar"}, em(5))
    assert [(e.tipo, e.exceto) for e in eventos] == [("limpar", 1)]
    assert sala.foto(2, em(5))["tracos"] == []
    assert sala.agir(1, {"tipo": "desfazer"}, em(6)) == []
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, {"tipo": "limpar"}, em(6))
    assert _status(excinfo) == 409


def _desenhistas(sala, ate: int) -> list[int]:
    """Lets every choice and drawing time out, collecting who draws, up to `ate` seconds."""
    vistos: list[int] = []
    t = 0.0
    while t <= ate and sala.foto(1, em(t))["fase"] != "fim":
        foto = sala.foto(1, em(t))
        if foto["fase"] == "escolha" and (not vistos or vistos[-1] != foto["desenhista"]):
            vistos.append(foto["desenhista"])
        t += 0.5
        sala.avancar(em(t))
        for jogador in range(1, 11):
            if jogador in {j["id"] for j in foto["jogadores"]}:
                sala.conectou(jogador, em(t))
                sala.desconectou(jogador, em(t))
    return vistos


def test_entra_no_meio_vai_para_o_fim_da_fila():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    jogador, _, eventos = sala.entrar("Novato", em(0.2))
    assert jogador == 4
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3, 4}
    sala.conectou(4, em(0.2))
    assert _desenhistas(sala, 1000) == [1, 2, 3, 4]
    assert sala.foto(1, em(1000))["fase"] == "fim"


def test_sala_cheia_409():
    sala, _ = sala_com(10)
    with pytest.raises(ErroSala) as excinfo:
        sala.entrar("Kiko", em(1))
    assert _status(excinfo) == 409


@pytest.mark.parametrize("apelido", ["ana", " ANA ", "Aná", "A", "x" * 17, "  "])
def test_apelido_repetido_422(apelido):
    sala, _ = sala_com(2)
    with pytest.raises(ErroSala) as excinfo:
        sala.entrar(apelido, em(1))
    assert _status(excinfo) == 422


def test_apelido_aparado_e_nos_limites():
    sala, _ = sala_com(1)
    jogador, _, _ = sala.entrar("  Zé  ", em(1))
    sala.entrar("y" * 16, em(1))
    assert sala.foto(jogador, em(1))["jogadores"][1]["apelido"] == "Zé"


def test_apelido_com_palavrao_422():
    sala, _ = sala_com(1)
    with pytest.raises(ErroSala) as excinfo:
        sala.entrar("Caralho", em(1))
    assert _status(excinfo) == 422


def test_token_invalido_403():
    sala, tokens = sala_com(2)
    assert sala.jogador(tokens[2]) == 2
    outra, outros = sala_com(2)
    assert outros[1] != tokens[1]
    with pytest.raises(ErroSala) as excinfo:
        sala.jogador(outros[1])
    assert _status(excinfo) == 403
    with pytest.raises(ErroSala) as excinfo:
        sala.jogador("")
    assert _status(excinfo) == 403


def test_acao_desconhecida_422():
    sala, _ = sala_com(2)
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, {"tipo": "voar"}, em(0))
    assert _status(excinfo) == 422
