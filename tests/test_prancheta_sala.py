import json

import pytest
from prancheta_fakes import BancoFalso, em, sala_com, traco

from geral.games.prancheta.sala import ErroSala, Evento
from geral.games.prancheta.tipos import Palavra, normalizar

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


# --- Task 3: chutes, dicas, pontos e fim do lance ---


def chute(texto: str) -> dict:
    return {"tipo": "chute", "texto": texto}


class BancoDe(BancoFalso):
    """Always offers the same given word in every difficulty slot."""

    def __init__(self, texto: str) -> None:
        super().__init__()
        self.palavra = Palavra(texto, (), "media", "lance")

    def opcoes(self, rng, usadas):
        return [self.palavra] * 3


@pytest.mark.parametrize(
    ("indice", "esperado"),
    [(2, [10, 9, 8, 7, 6, 5, 4, 3, 2]), (0, [5, 4, 3, 2, 2, 2, 2, 2, 2])],
)
def test_pontos_por_ordem_e_dificuldade(indice, esperado):
    sala, _ = em_desenho(10, indice=indice)
    palavra = sala.foto(1, em(2))["palavra"]
    ganhos = []
    for jogador in range(2, 11):
        eventos = sala.agir(jogador, chute(palavra), em(2))
        ganhos.append(next(e.dados["pontos"] for e in eventos if e.tipo == "acerto"))
    assert ganhos == esperado


def test_assistencia_de_quem_desenha():
    sala, _ = em_desenho(4, indice=1)
    sala.agir(2, chute("gol olimpico"), em(2))
    sala.agir(3, chute("Gol de escanteio"), em(3))
    jogadores = {j["id"]: j for j in sala.foto(1, em(3))["jogadores"]}
    assert (jogadores[1]["pontos"], jogadores[1]["assist"], jogadores[1]["gols"]) == (4, 2, 0)
    assert (jogadores[2]["pontos"], jogadores[2]["gols"], jogadores[2]["acertou"]) == (7, 1, True)
    assert (jogadores[3]["pontos"], jogadores[3]["gols"]) == (6, 1)
    assert (jogadores[4]["pontos"], jogadores[4]["acertou"]) == (0, False)


def test_chute_certo_nao_aparece():
    sala, _ = em_desenho()
    eventos = sala.agir(2, chute("Bicicleta"), em(2))
    assert [(e.tipo, e.para, e.exceto) for e in eventos] == [("acerto", None, None)]
    assert eventos[0].dados == {"jogador": 2, "pontos": 5, "seq": eventos[0].dados["seq"]}


def test_chute_errado_vai_para_todos():
    sala, _ = em_desenho()
    eventos = sala.agir(2, chute("  Pênalti "), em(2))
    assert [(e.tipo, e.dados["jogador"], e.dados["texto"], e.para) for e in eventos] == [
        ("chute", 2, "Pênalti", None)
    ]


def test_trave_e_palavrao_nao_sao_transmitidos():
    sala, _ = em_desenho()
    eventos = sala.agir(2, chute("bicicletinha"), em(2))
    assert [(e.tipo, e.dados["texto"], e.para) for e in eventos] == [("trave", "bicicletinha", 2)]
    eventos = sala.agir(2, chute("que merda de desenho"), em(3))
    assert [(e.tipo, e.para) for e in eventos] == [("chute", 2)]
    eventos = sala.agir(2, chute("linda bicicleta"), em(4))
    assert [(e.tipo, e.para) for e in eventos] == [("chute", 2)]


def test_trave_so_para_quem_chutou():
    sala, _ = em_desenho(4)
    eventos = sala.agir(3, chute("Bicicl"), em(2))
    assert [(e.tipo, e.para) for e in eventos] == [("trave", 3)]


def test_julgar_recebe_o_texto_cru():
    banco = BancoFalso()
    sala, _ = em_desenho(banco=banco)
    sala.agir(2, chute("  BICICLETA!! "), em(2))
    assert banco.julgados == ["  BICICLETA!! "]


def test_chute_invalido_ou_fora_da_vez():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    for jogador, acao, status in [
        (2, chute("bola"), 409),  # still choosing
    ]:
        with pytest.raises(ErroSala) as excinfo:
            sala.agir(jogador, acao, em(0.5))
        assert _status(excinfo) == status
    sala.agir(1, {"tipo": "escolher", "indice": 0}, em(1))
    sala.agir(2, chute("bicicleta"), em(2))
    for jogador, acao, status in [
        (1, chute("bola"), 409),  # who draws
        (2, chute("bola"), 409),  # already scored
        (3, chute("x" * 41), 422),
        (3, chute("   "), 422),
        (3, {"tipo": "chute"}, 422),
    ]:
        with pytest.raises(ErroSala) as excinfo:
            sala.agir(jogador, acao, em(3))
        assert _status(excinfo) == status
    sala.agir(3, chute("x" * 40), em(3))


def test_chute_rapido_demais_429():
    sala, _ = em_desenho()
    sala.agir(2, chute("bola"), em(2))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, chute("rede"), em(2.4))
    assert _status(excinfo) == 429
    sala.agir(3, chute("rede"), em(2.4))
    sala.agir(2, chute("rede"), em(2.5))


def test_dicas_aos_50_e_75_porcento():
    sala, _ = em_desenho(indice=2)  # Frasqueira, drawing from 1 s to 81 s
    assert sala.foto(2, em(1))["dica"] == [None] * 10
    assert sala.avancar(em(40.9)) == []
    eventos = sala.avancar(em(41))
    assert [(e.tipo, e.exceto) for e in eventos] == [("dica", 1)]
    acesas = [c for c in eventos[0].dados["dica"] if c]
    assert len(acesas) == 1 and acesas[0] in "Frasqueira"
    assert sala.avancar(em(60.9)) == []
    eventos = sala.avancar(em(61))
    dica = eventos[0].dados["dica"]
    assert sum(1 for c in dica if c) == 2
    assert all(c is None or c == "Frasqueira"[i] for i, c in enumerate(dica))
    assert sala.foto(2, em(61))["dica"] == dica
    assert [e.tipo for e in sala.avancar(em(80.9))] == []


def test_dica_nunca_passa_de_um_terco():
    sala, _ = em_desenho(banco=BancoDe("Gol"))
    assert len(sala.avancar(em(41))) == 1
    assert sala.avancar(em(61)) == []
    assert sum(1 for c in sala.foto(2, em(61))["dica"] if c) == 1


def test_dica_mostra_o_que_nao_e_letra():
    sala, _ = em_desenho(banco=BancoDe("7 a 1-0."))
    assert sala.foto(2, em(1))["dica"] == ["7", " ", None, " ", "1", "-", "0", "."]
    assert sala.avancar(em(41)) == [] and sala.avancar(em(61)) == []


def test_ultimo_acerto_encerra_o_lance():
    sala, _ = em_desenho()
    sala.agir(2, chute("Bicicleta"), em(2))
    eventos = sala.agir(3, chute("bicicleta de costas"), em(2))
    assert [e.tipo for e in eventos] == ["acerto", "estado", "estado", "estado"]
    for jogador in (1, 2, 3):
        foto = sala.foto(jogador, em(2))
        assert (foto["fase"], foto["palavra"]) == ("intervalo", "Bicicleta")
    assert sala.foto(1, em(2))["prazo"] == em(8).isoformat()
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(3, chute("bola"), em(3))
    assert _status(excinfo) == 409


def test_lance_acaba_quando_todos_acertam():
    sala, _ = em_desenho(4)
    sala.agir(2, chute("Bicicleta"), em(2))
    sala.agir(3, chute("Bicicleta"), em(3))
    assert sala.foto(1, em(3))["fase"] == "desenho"
    sala.agir(4, chute("Bicicleta"), em(4))
    assert sala.foto(1, em(4))["fase"] == "intervalo"


def test_lance_acaba_no_prazo():
    sala, _ = em_desenho()
    sala.avancar(em(80.9))
    assert sala.foto(2, em(80.9))["fase"] == "desenho"
    sala.avancar(em(81))
    assert sala.foto(2, em(81))["fase"] == "intervalo"
    assert sala.foto(2, em(81))["palavra"] == "Bicicleta"
    sala.avancar(em(87))
    foto = sala.foto(2, em(87))
    assert (foto["fase"], foto["desenhista"], foto["palavra"], foto["tracos"]) == (
        "escolha",
        2,
        None,
        [],
    )
    assert all(not j["acertou"] for j in foto["jogadores"])


def test_palavra_nunca_vaza():
    sala, _ = sala_com(4)
    vistos: list = []

    def guarda(eventos, t):
        vistos.extend(e.dados for e in eventos if e.para in (None, 3, 4) and e.exceto not in (3, 4))
        vistos.extend(sala.foto(j, em(t)) for j in (3, 4))

    guarda(sala.agir(1, COMECAR, em(0)), 0)
    guarda(sala.agir(1, {"tipo": "escolher", "indice": 2}, em(1)), 1)
    guarda(sala.agir(1, traco(1, [[1, 1], [2, 2]]), em(2)), 2)
    guarda(sala.agir(2, chute("frasq"), em(3)), 3)
    guarda(sala.agir(2, chute("a frasqueira!"), em(4)), 4)
    guarda(sala.agir(2, chute("torcida do ABC lá"), em(5)), 5)
    guarda(sala.agir(3, chute("arquibancada"), em(6)), 6)
    guarda(sala.agir(2, chute("Frasqueira"), em(7)), 7)
    t = 7.0
    while sala.foto(1, em(t))["fase"] == "desenho":
        t += 0.5
        guarda(sala.avancar(em(t)), t)
    assert sala.foto(3, em(t))["fase"] == "intervalo"
    assert any(e.get("dica") for e in vistos)
    assert any("jogador" in e and e.get("texto") == "arquibancada" for e in vistos)
    for dados in vistos:
        if dados.get("fase") == "intervalo":
            continue
        texto = normalizar(json.dumps(dados, ensure_ascii=False))
        assert "frasqueira" not in texto and "torcida do abc" not in texto, dados
