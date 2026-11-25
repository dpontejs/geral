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
        traco(1, [[0, 0]], cor=13),
        traco(1, [[0, 0]], cor=-1),
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


DICA = {"tipo": "dica"}


def test_dicas_so_quando_quem_desenha_pede():
    sala, _ = em_desenho(indice=2)  # Frasqueira, drawing from 1 s to 81 s
    assert sala.foto(2, em(1))["dica"] == [None] * 10
    assert sala.avancar(em(41)) == [] and sala.avancar(em(61)) == []  # nothing by itself
    assert sala.foto(2, em(61))["dica"] == [None] * 10
    eventos = sala.agir(1, DICA, em(61))
    assert [(e.tipo, e.para, e.exceto) for e in eventos] == [("dica", None, 1), ("estado", 1, None)]
    acesas = [c for c in eventos[0].dados["dica"] if c]
    assert len(acesas) == 1 and acesas[0] in "Frasqueira"
    assert eventos[1].dados["dicas"]["dadas"] == 1
    eventos = sala.agir(1, DICA, em(61.5))  # both thresholds passed: two hints to give
    dica = eventos[0].dados["dica"]
    assert sum(1 for c in dica if c) == 2
    assert all(c is None or c == "Frasqueira"[i] for i, c in enumerate(dica))
    assert sala.foto(2, em(62))["dica"] == dica
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, DICA, em(62))
    assert _status(excinfo) == 409


def test_dica_liberada_aos_50_e_75_porcento():
    sala, _ = em_desenho(indice=2)
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, DICA, em(40.9))
    assert _status(excinfo) == 409
    sala.agir(1, DICA, em(41))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, DICA, em(60.9))  # one hint per threshold
    assert _status(excinfo) == 409
    sala.agir(1, DICA, em(61))
    assert sum(1 for c in sala.foto(2, em(61))["dica"] if c) == 2


def test_foto_de_quem_desenha_traz_os_marcos_das_dicas():
    sala, _ = em_desenho(indice=2)
    assert sala.foto(1, em(2))["dicas"] == {
        "dadas": 0,
        "marcos": [em(41).isoformat(), em(61).isoformat()],
    }
    assert sala.foto(2, em(2))["dicas"] is None
    curta, _ = em_desenho(banco=BancoDe("Gol"))
    assert curta.foto(1, em(2))["dicas"]["marcos"] == [em(41).isoformat()]  # 1/3 of 3 letters
    escolhendo, _ = sala_com(2)
    escolhendo.agir(1, COMECAR, em(0))
    assert escolhendo.foto(1, em(0))["dicas"] is None


def test_so_quem_desenha_da_dica_409():
    sala, _ = em_desenho(indice=2)
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, DICA, em(41))
    assert _status(excinfo) == 409
    escolhendo, _ = sala_com(2)
    escolhendo.agir(1, COMECAR, em(0))
    with pytest.raises(ErroSala) as excinfo:
        escolhendo.agir(1, DICA, em(14))
    assert _status(excinfo) == 409


def test_dica_nunca_passa_de_um_terco():
    sala, _ = em_desenho(banco=BancoDe("Gol"))
    sala.agir(1, DICA, em(41))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, DICA, em(61))
    assert _status(excinfo) == 409
    assert sum(1 for c in sala.foto(2, em(61))["dica"] if c) == 1


def test_dica_mostra_o_que_nao_e_letra():
    sala, _ = em_desenho(banco=BancoDe("7 a 1-0."))
    assert sala.foto(2, em(1))["dica"] == ["7", " ", None, " ", "1", "-", "0", "."]
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, DICA, em(61))  # one letter: no hint at all
    assert _status(excinfo) == 409


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
    guarda(sala.agir(1, {"tipo": "dica"}, em(41)), 41)
    t = 41.0
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


# --- Task 4: ausência, saída, cartão vermelho e súmula ---

SAIR = {"tipo": "sair"}


def ids(sala, quem: int = 1, t: float = 0) -> list[int]:
    """Players in the room, as `quem` sees them."""
    return [j["id"] for j in sala.foto(quem, em(t))["jogadores"]]


def cartao(alvo: int) -> dict:
    return {"tipo": "cartao", "alvo": alvo}


def tirar(alvo: int) -> dict:
    return {"tipo": "tirar", "alvo": alvo}


def test_ausente_depois_de_30_s_sem_conexao():
    sala, _ = sala_com(3)
    sala.desconectou(2, em(0))
    assert sala.avancar(em(29.9)) == []
    eventos = sala.avancar(em(30))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3}
    assert [j["presente"] for j in sala.foto(1, em(30))["jogadores"]] == [True, False, True]
    eventos = sala.conectou(2, em(31))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3}
    assert sala.foto(1, em(31))["jogadores"][1]["presente"]


def test_reconectar_antes_de_30_s_nao_fica_ausente():
    sala, _ = sala_com(2)
    sala.desconectou(2, em(0))
    sala.conectou(2, em(20))
    assert sala.avancar(em(60)) == []


def test_vez_de_ausente_e_pulada():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    sala.desconectou(2, em(0))
    sala.avancar(em(15))  # choice timed out: drawing until 95 s
    sala.avancar(em(30))
    assert not sala.foto(1, em(30))["jogadores"][1]["presente"]
    sala.avancar(em(95))
    assert sala.foto(1, em(95))["fase"] == "intervalo"
    sala.avancar(em(101))
    assert sala.foto(1, em(101))["desenhista"] == 3


def test_quem_desenha_sai_lance_vai_ao_intervalo():
    sala, _ = em_desenho(3)
    sala.agir(2, chute("Bicicleta"), em(2))
    eventos = sala.agir(1, SAIR, em(3))
    assert {e.para for e in eventos if e.tipo == "estado"} >= {2, 3}
    foto = sala.foto(2, em(3))
    assert (foto["fase"], foto["palavra"], foto["prazo"]) == (
        "intervalo",
        "Bicicleta",
        em(9).isoformat(),
    )
    assert foto["jogadores"][0]["pontos"] == 5
    sala.avancar(em(9))
    assert sala.foto(2, em(9))["desenhista"] == 2


def test_quem_desenha_fica_ausente_lance_vai_ao_intervalo():
    sala, _ = em_desenho(3)
    sala.desconectou(1, em(2))
    sala.avancar(em(32))
    assert sala.foto(2, em(32))["fase"] == "intervalo"


def test_quem_desenha_expulso_lance_vai_ao_intervalo():
    sala, _ = em_desenho(3)
    sala.agir(2, cartao(1), em(2))
    sala.agir(3, cartao(1), em(2))
    assert sala.foto(2, em(2))["fase"] == "intervalo"
    assert ids(sala, 2) == [2, 3]


def test_desenhista_sai_na_escolha():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    sala.agir(1, SAIR, em(1))
    foto = sala.foto(2, em(1))
    assert (foto["fase"], foto["palavra"], foto["opcoes"]) == ("intervalo", None, None)
    sala.avancar(em(7))
    assert sala.foto(2, em(7))["desenhista"] == 2
    assert sala.foto(2, em(7))["fase"] == "escolha"


def test_anfitriao_passa_ao_mais_antigo():
    sala, _ = sala_com(4)
    sala.desconectou(2, em(0))
    sala.avancar(em(30))
    sala.agir(1, SAIR, em(31))
    anfitriao = [j["id"] for j in sala.foto(3, em(31))["jogadores"] if j["anfitriao"]]
    assert anfitriao == [3]  # 2 is away
    sala.conectou(2, em(32))
    sala.desconectou(3, em(32))
    sala.avancar(em(62))
    anfitriao = [j["id"] for j in sala.foto(2, em(62))["jogadores"] if j["anfitriao"]]
    assert anfitriao == [2]
    sala.agir(2, tirar(4), em(63))
    assert ids(sala, 2, 63) == [2, 3]


def test_cartao_vermelho_por_maioria():
    sala, tokens = sala_com(5)
    assert {e.para for e in sala.agir(1, cartao(5), em(1))} == {1, 2, 3, 4, 5}
    sala.agir(2, cartao(5), em(1))
    sala.agir(2, cartao(5), em(1))  # voting twice counts once
    assert 5 in ids(sala, 1, 1)
    eventos = sala.agir(3, cartao(5), em(1))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3, 4, 5}
    assert ids(sala, 1, 1) == [1, 2, 3, 4]
    with pytest.raises(ErroSala) as excinfo:
        sala.jogador(tokens[5])
    assert _status(excinfo) == 403


def test_estado_traz_cartoes_por_jogador():
    sala, _ = sala_com(5)
    eventos = sala.agir(1, cartao(3), em(1))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3, 4, 5}
    for evento in eventos:
        jogadores = {j["id"]: j for j in evento.dados["jogadores"]}
        assert {i: j["cartoes"] for i, j in jogadores.items()} == {1: 0, 2: 0, 3: 1, 4: 0, 5: 0}
        # a strict majority of the 4 present players besides the target
        assert {j["cartoes_para_sair"] for j in jogadores.values()} == {3}
    sala.desconectou(4, em(1))
    sala.avancar(em(31))  # 4 is absent: 3 others besides any target
    jogadores = sala.foto(1, em(31))["jogadores"]
    assert {j["id"]: j["cartoes_para_sair"] for j in jogadores} == {1: 2, 2: 2, 3: 2, 4: 3, 5: 2}


def test_ausente_nao_conta_na_maioria():
    sala, _ = sala_com(5)
    sala.desconectou(3, em(0))
    sala.desconectou(4, em(0))
    sala.avancar(em(30))
    sala.agir(1, cartao(5), em(31))
    assert 5 in ids(sala, 1, 31)
    sala.agir(2, cartao(5), em(31))
    assert 5 not in ids(sala, 1, 31)


def test_cartao_invalido_422():
    sala, _ = sala_com(3)
    for acao in (cartao(1), cartao(9), cartao("2"), {"tipo": "cartao"}):
        with pytest.raises(ErroSala) as excinfo:
            sala.agir(1, acao, em(1))
        assert _status(excinfo) == 422


def test_voto_cai_quando_votante_sai():
    sala, _ = sala_com(5)
    sala.agir(1, cartao(5), em(1))
    sala.agir(2, cartao(5), em(1))
    sala.agir(1, SAIR, em(2))
    assert 5 in ids(sala, 2, 2)
    sala.agir(3, cartao(5), em(3))
    assert 5 not in ids(sala, 2, 3)


def test_expulso_nao_age():
    sala, tokens = sala_com(3)
    eventos = sala.agir(1, tirar(3), em(1))
    estado_do_expulso = next(e.dados for e in eventos if e.para == 3)
    assert 3 not in [j["id"] for j in estado_do_expulso["jogadores"]]
    with pytest.raises(ErroSala) as excinfo:
        sala.jogador(tokens[3])
    assert _status(excinfo) == 403
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(3, chute("bola"), em(2))
    assert _status(excinfo) == 403
    novo, _, _ = sala.entrar("Caio", em(3))  # the nickname is free again
    assert novo == 4


def test_so_anfitriao_tira_409():
    sala, _ = sala_com(3)
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, tirar(3), em(1))
    assert _status(excinfo) == 409
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, tirar(1), em(1))
    assert _status(excinfo) == 422


def test_sair_invalida_o_token():
    sala, tokens = sala_com(3)
    sala.agir(2, SAIR, em(1))
    with pytest.raises(ErroSala) as excinfo:
        sala.jogador(tokens[2])
    assert _status(excinfo) == 403


def test_reconectar_recebe_tracos_do_desenho_atual():
    sala, _ = em_desenho()
    sala.agir(1, traco(1, [[1, 1]], fim=False), em(2))
    sala.agir(1, traco(1, [[2, 2]]), em(2.1))
    sala.agir(1, traco(2, [[3, 3]], cor=0, esp=3), em(2.2))
    sala.desconectou(2, em(3))
    sala.conectou(2, em(4))
    assert sala.foto(2, em(4))["tracos"] == [
        {"id": 1, "cor": 1, "esp": 2, "pts": [[1, 1], [2, 2]], "fim": True},
        {"id": 2, "cor": 0, "esp": 3, "pts": [[3, 3]], "fim": True},
    ]


def test_menos_de_dois_presentes_vai_ao_fim():
    sala, _ = em_desenho(2)
    sala.desconectou(2, em(2))
    eventos = sala.avancar(em(32))
    assert [e.tipo for e in eventos].count("fim") == 1
    assert sala.encerrada


def test_espera_nao_acaba_quando_sai_gente():
    sala, _ = sala_com(2)
    sala.agir(1, SAIR, em(1))
    assert not sala.encerrada
    assert sala.foto(2, em(1))["jogadores"][0]["anfitriao"]


def test_fim_uma_vez_so():
    sala, _ = em_desenho(2)
    eventos = sala.agir(2, SAIR, em(2))
    fins = [e for e in eventos if e.tipo == "fim"]
    assert len(fins) == 1 and fins[0].para is None
    assert sala.encerrada
    assert sala.foto(1, em(2))["fase"] == "fim"
    assert sala.avancar(em(500)) == []
    assert sala.desconectou(1, em(500)) == []
    assert sala.avancar(em(600)) == []
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, SAIR, em(601))
    assert _status(excinfo) == 409
    with pytest.raises(ErroSala) as excinfo:
        sala.entrar("Novo", em(601))
    assert _status(excinfo) == 409


def test_encerrar_em_jogo_vai_ao_fim_com_o_lance_atual():
    sala, _ = em_desenho(3)
    eventos = sala.encerrar(em(5))
    assert [e.tipo for e in eventos].count("fim") == 1 and sala.encerrada
    fim = next(e for e in eventos if e.tipo == "fim")
    assert fim.dados["sumula"]["lances"] == [
        {"desenhista": "Ana", "palavra": "Bicicleta", "acertaram": []}
    ]
    assert sala.encerrar(em(6)) == []


def test_encerrar_na_espera_so_fecha():
    sala, _ = sala_com(3)
    assert sala.encerrar(em(5)) == []
    assert sala.encerrada


def test_sumula_ordenada_por_pontos():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    sala.agir(1, {"tipo": "escolher", "indice": 2}, em(1))  # Frasqueira
    sala.agir(3, chute("frasqueira"), em(2))
    sala.agir(2, chute("Torcida do ABC"), em(3))  # everyone scored: interval until 9 s
    sala.avancar(em(9))
    sala.agir(2, {"tipo": "escolher", "indice": 0}, em(10))  # Escanteio
    sala.agir(1, chute("escanteio"), em(11))
    sala.agir(2, SAIR, em(12))  # drawer leaves: interval; 3 draws next
    sala.avancar(em(18))
    sala.agir(3, {"tipo": "escolher", "indice": 1}, em(19))  # Impedimento, nobody scores
    sala.avancar(em(99))
    eventos = sala.avancar(em(105))
    fim = [e.dados for e in eventos if e.tipo == "fim"]
    assert len(fim) == 1
    sumula = sala.sumula()
    assert fim[0]["sumula"] == sumula
    assert sumula == {
        "id": "abc234",
        "jogadores": [
            {"apelido": "Bia", "pontos": 11, "gols": 1, "assist": 1},
            {"apelido": "Caio", "pontos": 10, "gols": 1, "assist": 0},
            {"apelido": "Ana", "pontos": 9, "gols": 1, "assist": 2},
        ],
        "lances": [
            {"desenhista": "Ana", "palavra": "Frasqueira", "acertaram": ["Caio", "Bia"]},
            {"desenhista": "Bia", "palavra": "Escanteio", "acertaram": ["Ana"]},
            {"desenhista": "Caio", "palavra": "Impedimento", "acertaram": []},
        ],
    }
    assert sala.foto(1, em(105))["palavra"] == "Impedimento"


# --- 2026-11-24: mais cores, pedir para entrar e pular a vez ---


def test_doze_gizes_e_o_apagador():
    sala, _ = em_desenho()
    for cor in range(13):
        sala.agir(1, traco(cor + 1, [[10, 10]], cor=cor), em(2 + cor * 0.05))
    assert [t["cor"] for t in sala.foto(2, em(3))["tracos"]] == list(range(13))


def aceitar(pedido: int) -> dict:
    return {"tipo": "aceitar", "pedido": pedido}


def recusar(pedido: int) -> dict:
    return {"tipo": "recusar", "pedido": pedido}


def pedidos(sala, quem: int = 1, t: float = 0):
    return sala.foto(quem, em(t))["pedidos"]


def test_quem_abre_o_link_pede_para_entrar():
    sala, _ = sala_com(2)
    pedido, token, eventos = sala.pedir(" Novato ", em(1))
    assert pedido == 3 and token
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3}
    assert pedidos(sala) == [{"id": 3, "apelido": "Novato"}]
    assert pedidos(sala, 2) is None  # only the host sees the requests
    assert ids(sala) == [1, 2]  # not a player yet
    assert sala.foto(3, em(1)) == {
        "seq": sala.foto(1, em(1))["seq"],
        "voce": 3,
        "fase": "pedido",
        "agora": em(1).isoformat(),
        "apelido": "Novato",
        "anfitriao": "Ana",
    }
    assert sala.identificar(token) == 3 and sala.esta(3)
    with pytest.raises(ErroSala) as excinfo:
        sala.jogador(token)  # waiting: cannot act yet
    assert _status(excinfo) == 409


def test_anfitriao_aceita_o_pedido():
    sala, _ = sala_com(2)
    pedido, token, _ = sala.pedir("Novato", em(1))
    sala.conectou(pedido, em(1))
    eventos = sala.agir(1, aceitar(pedido), em(2))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3}
    assert ids(sala) == [1, 2, 3] and pedidos(sala) == []
    assert sala.jogador(token) == 3
    foto = sala.foto(3, em(2))
    assert foto["fase"] == "espera" and foto["voce"] == 3
    assert foto["jogadores"][2]["presente"]
    sala.agir(1, COMECAR, em(3))
    assert _desenhistas(sala, 1000) == [1, 2, 3]


def test_aceito_no_meio_vai_para_o_fim_da_fila():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    pedido, _, _ = sala.pedir("Novato", em(0.2))
    sala.conectou(pedido, em(0.2))
    sala.agir(1, aceitar(pedido), em(0.3))
    assert _desenhistas(sala, 1000) == [1, 2, 3, 4]


def test_anfitriao_recusa_o_pedido():
    sala, _ = sala_com(2)
    pedido, token, _ = sala.pedir("Novato", em(1))
    eventos = sala.agir(1, recusar(pedido), em(2))
    assert Evento("recusado", {"seq": eventos[0].dados["seq"]}, para=3) in eventos
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2}
    assert pedidos(sala) == [] and ids(sala) == [1, 2]
    assert not sala.esta(3)
    for buscar in (sala.jogador, sala.identificar):
        with pytest.raises(ErroSala) as excinfo:
            buscar(token)
        assert _status(excinfo) == 403
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, aceitar(pedido), em(3))  # too late
    assert _status(excinfo) == 422


@pytest.mark.parametrize("acao", [aceitar(3), recusar(3)])
def test_so_anfitriao_responde_pedido_409(acao):
    sala, _ = sala_com(2)
    sala.pedir("Novato", em(1))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, acao, em(2))
    assert _status(excinfo) == 409


@pytest.mark.parametrize("pedido", [2, 9, "3", None, True])
def test_pedido_invalido_422(pedido):
    sala, _ = sala_com(2)
    sala.pedir("Novato", em(1))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, {"tipo": "aceitar", "pedido": pedido}, em(2))
    assert _status(excinfo) == 422


def test_novo_anfitriao_herda_os_pedidos():
    sala, _ = sala_com(3)
    sala.pedir("Novato", em(1))
    sala.agir(1, SAIR, em(2))
    assert pedidos(sala, 2, 2) == [{"id": 4, "apelido": "Novato"}]
    assert sala.foto(4, em(2))["anfitriao"] == "Bia"
    sala.agir(2, aceitar(4), em(3))
    assert ids(sala, 2, 3) == [2, 3, 4]


def test_pedidos_nao_ocupam_vaga_e_tem_teto():
    sala, _ = sala_com(9)
    novos = [sala.pedir(f"Novo{i}", em(1))[0] for i in range(10)]
    with pytest.raises(ErroSala) as excinfo:
        sala.pedir("Mais um", em(1))
    assert _status(excinfo) == 409
    sala.agir(1, aceitar(novos[0]), em(2))
    assert len(ids(sala, 1, 2)) == 10
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, aceitar(novos[1]), em(2))  # the room is full: the request waits
    assert _status(excinfo) == 409
    assert len(pedidos(sala, 1, 2)) == 9


def test_apelido_de_pedido_nao_repete():
    sala, _ = sala_com(2)
    sala.pedir("Novato", em(1))
    for apelido in ("bia", "NOVATO", "x", "porra"):
        with pytest.raises(ErroSala) as excinfo:
            sala.pedir(apelido, em(1))
        assert _status(excinfo) == 422
    with pytest.raises(ErroSala) as excinfo:
        sala.entrar("Novato", em(1))
    assert _status(excinfo) == 422


def test_pedido_sem_conexao_cai_depois_de_30_s():
    sala, _ = sala_com(2)
    pedido, token, _ = sala.pedir("Novato", em(0))
    outro, _, _ = sala.pedir("Outro", em(0))
    sala.conectou(outro, em(1))
    assert sala.avancar(em(29.9)) == []
    eventos = sala.avancar(em(30))
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, outro}
    assert pedidos(sala, 1, 30) == [{"id": outro, "apelido": "Outro"}]
    with pytest.raises(ErroSala) as excinfo:
        sala.identificar(token)
    assert _status(excinfo) == 403
    sala.desconectou(outro, em(31))
    sala.avancar(em(61))
    assert pedidos(sala, 1, 61) == []


def test_pedido_em_sala_encerrada_409():
    sala, _ = sala_com(2)
    sala.agir(1, COMECAR, em(0))
    sala.agir(2, SAIR, em(1))
    with pytest.raises(ErroSala) as excinfo:
        sala.pedir("Novato", em(2))
    assert _status(excinfo) == 409


PULAR = {"tipo": "pular"}


def test_quem_desenha_pula_e_o_lance_vai_ao_intervalo():
    sala, _ = em_desenho(3)
    sala.agir(2, chute("Bicicleta"), em(2))
    eventos = sala.agir(1, PULAR, em(3))
    assert eventos[0] == Evento("pulou", {"jogador": 1, "seq": eventos[0].dados["seq"]})
    assert {e.para for e in eventos if e.tipo == "estado"} == {1, 2, 3}
    foto = sala.foto(3, em(3))
    assert (foto["fase"], foto["palavra"], foto["prazo"]) == (
        "intervalo",
        "Bicicleta",
        em(9).isoformat(),
    )
    assert [(j["pontos"], j["gols"], j["assist"]) for j in foto["jogadores"]] == [
        (2, 0, 1),
        (5, 1, 0),
        (0, 0, 0),
    ]
    sala.avancar(em(9))
    assert sala.foto(2, em(9))["desenhista"] == 2
    assert sala.sumula()["lances"][0] == {
        "desenhista": "Ana",
        "palavra": "Bicicleta",
        "acertaram": ["Bia"],
    }


def test_quem_desenha_pula_na_escolha():
    sala, _ = sala_com(3)
    sala.agir(1, COMECAR, em(0))
    sala.agir(1, PULAR, em(1))
    foto = sala.foto(2, em(1))
    assert (foto["fase"], foto["palavra"], foto["opcoes"]) == ("intervalo", None, None)
    sala.avancar(em(7))
    assert sala.foto(2, em(7))["desenhista"] == 2


def test_so_quem_desenha_pula_409():
    sala, _ = em_desenho(3)
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(2, PULAR, em(2))
    assert _status(excinfo) == 409
    sala.agir(1, PULAR, em(3))
    with pytest.raises(ErroSala) as excinfo:
        sala.agir(1, PULAR, em(4))  # already in the break
    assert _status(excinfo) == 409
