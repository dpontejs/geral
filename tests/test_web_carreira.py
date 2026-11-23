import pytest
from webkit import make_client

from geral.games.carreira import regras
from geral.games.carreira.codigo import decodificar
from geral.games.carreira.motor import MAX_RESPOSTAS

API = "/api/jogos/carreira"
CRAQUE = {"nome": "Zé", "camisa": 10, "posicao": "atacante", "pe": "direito", "clube": "bahia"}


@pytest.fixture
def game(store, mailer, clock):
    return make_client(store, mailer, clock)


def _comeco(game, edicao="geral") -> dict:
    oferta = game.post(f"{API}/{edicao}/oferta", json={"clube": CRAQUE["clube"]})
    assert oferta.status_code == 200
    corpo = oferta.json()
    lendas = corpo["lendas"]
    assert len(lendas) == 10 and all(set(x["notas"]) == set(regras.ATRIBUTOS) for x in lendas)
    roubos = [
        {"lenda": lenda["nome"], "atributo": a}
        for lenda, a in zip(lendas, regras.ATRIBUTOS, strict=False)
    ]
    return {"semente_draft": corpo["semente_draft"], "craque": CRAQUE, "roubos": roubos}


def test_oferta_e_simulacao_ate_o_fim(game) -> None:
    pedido = _comeco(game) | {"escolhas": []}  # no modo: Completa, the only one offered

    for _ in range(MAX_RESPOSTAS + 1):
        resposta = game.post(f"{API}/geral/simular", json=pedido)
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        pedido["semente"] = corpo["semente"]  # the server drew it on the first call
        if corpo["carreira"]["final"]:
            break
        assert corpo["codigo"] is None
        pedido["escolhas"].append(0)

    final = corpo["carreira"]["final"]
    assert final["rotulo"] and corpo["codigo"]
    assert decodificar(corpo["codigo"]).resumo.rotulo == final["rotulo"]
    assert corpo["carreira"]["temporadas"][0]["clube"] == "Bahia"


def test_mesma_semente_mesma_carreira(game) -> None:
    pedido = _comeco(game) | {"semente": "fixa", "escolhas": []}

    primeira = game.post(f"{API}/geral/simular", json=pedido).json()

    assert game.post(f"{API}/geral/simular", json=pedido).json() == primeira


@pytest.mark.parametrize("edicao", ["xyz", "vasco"])  # one edition only: geral
def test_edicao_desconhecida_e_404(game, edicao) -> None:
    assert game.post(f"{API}/{edicao}/oferta", json={}).status_code == 404
    pedido = _comeco(game) | {"escolhas": []}
    assert game.post(f"{API}/{edicao}/simular", json=pedido).status_code == 404


def test_roubo_invalido_escolha_fora_e_escolha_sobrando_sao_422(game) -> None:
    pedido = _comeco(game) | {"semente": "fixa", "escolhas": []}
    ruim = dict(pedido, roubos=[*pedido["roubos"][:7], pedido["roubos"][0]])
    assert game.post(f"{API}/geral/simular", json=ruim).status_code == 422

    escolhas: list[int] = []
    while not (c := game.post(f"{API}/geral/simular", json=pedido | {"escolhas": escolhas}).json())[
        "carreira"
    ]["final"]:
        escolhas.append(0)
    sobrando = game.post(f"{API}/geral/simular", json=pedido | {"escolhas": [*escolhas, 0]})
    assert sobrando.status_code == 422 and "detail" in sobrando.json()
    if escolhas:
        fora = game.post(f"{API}/geral/simular", json=pedido | {"escolhas": [7]})
        assert fora.status_code == 422
    assert c["codigo"]


def test_nome_longo_e_422(game) -> None:
    pedido = _comeco(game) | {"escolhas": []}
    pedido["craque"] = CRAQUE | {"nome": "x" * 25}

    assert game.post(f"{API}/geral/simular", json=pedido).status_code == 422


def _codigo(game) -> tuple[str, dict]:
    pedido = _comeco(game) | {"semente": "fixa", "escolhas": []}
    while not (corpo := game.post(f"{API}/geral/simular", json=pedido).json())["codigo"]:
        pedido["escolhas"].append(0)
    return corpo["codigo"], corpo["carreira"]["final"]


def test_link_do_card_reabre_a_carreira(game) -> None:
    codigo, final = _codigo(game)

    page = game.get(f"/jogos/carreira/c/{codigo}")

    assert page.status_code == 200
    assert final["rotulo"] in page.text and "Zé" in page.text


def test_link_de_versao_velha_mostra_o_resumo(game) -> None:
    from geral.games.carreira.codigo import codificar

    codigo, final = _codigo(game)
    velho = decodificar(codigo)
    codigo_velho = codificar("00000000", velho.edicao, velho.entrada, velho.resumo)

    page = game.get(f"/jogos/carreira/c/{codigo_velho}")

    assert page.status_code == 200 and final["rotulo"] in page.text and "Jogar a sua" in page.text


def test_link_invalido_e_404(game) -> None:
    assert game.get("/jogos/carreira/c/nao-e-um-codigo").status_code == 404


def test_carreira_aparece_em_jogos_sem_numero_do_dia(game) -> None:
    page = game.get("/jogos")

    assert "Carreira" in page.text and "/jogos/carreira" in page.text
    assert "#None" not in page.text


def test_pagina_unica_com_todos_os_clubes_brasileiros(game) -> None:
    page = game.get("/jogos/carreira")

    assert page.status_code == 200
    assert '"bahia"' in page.text and '"abc"' in page.text and '"vasco"' in page.text


@pytest.mark.parametrize("edicao", ["vasco", "abc", "xyz"])
def test_edicao_de_time_redireciona_para_a_unica(game, edicao) -> None:
    page = game.get(f"/jogos/carreira/{edicao}", follow_redirects=False)

    assert page.status_code in (301, 308) and page.headers["location"] == "/jogos/carreira"


def test_modo_completo_comeca_com_o_dia_a_dia(game) -> None:
    pedido = _comeco(game) | {"semente": "fixa", "escolhas": [], "modo": "completa"}

    corpo = game.post(f"{API}/geral/simular", json=pedido).json()

    pendente = corpo["carreira"]["pendente"]
    assert pendente["tipo"] == "dia" and pendente["info"]
    assert decodificar_ok(game, pedido)


def decodificar_ok(game, pedido) -> bool:
    """A Completa career replays from its share code (the mode goes in the code)."""
    escolhas: list[int] = []
    while not (c := game.post(f"{API}/geral/simular", json=pedido | {"escolhas": escolhas}).json())[
        "codigo"
    ]:
        escolhas.append(0)
    aberto = decodificar(c["codigo"])
    return aberto.entrada.modo == "completa" and len(c["codigo"]) < 2000


def test_oferta_de_quem_comeca_no_abc_traz_idolos_do_nordeste(game) -> None:
    corpo = game.post(f"{API}/geral/oferta", json={"clube": "abc"}).json()

    assert sum(x["regiao"] == "nordeste" for x in corpo["lendas"]) >= 2


def test_pagina_sabe_o_tipo_de_cada_taca(game) -> None:
    import json
    import re

    page = game.get("/jogos/carreira").text
    jogo = json.loads(re.search(r'id="cr-data">(.*?)</script>', page, re.S).group(1))

    assert jogo["tacas"]["Brasileirão"] == "liga"
    assert jogo["tacas"]["Copa do Brasil"] == "copa"
    assert jogo["tacas"]["Libertadores"] == "continental"
    assert jogo["tacas"]["Campeonato Potiguar"] == "estadual"
    assert jogo["tacas"]["Copa do Nordeste"] == "nordeste"
    assert jogo["tacas"]["Copa do Mundo"] == "mundo"


def _ate_o_fim(game, semente="fixa", clube="bahia") -> dict:
    pedido = _comeco(game) | {"semente": semente, "escolhas": []}
    pedido["craque"] = CRAQUE | {"clube": clube}
    while not (corpo := game.post(f"{API}/geral/simular", json=pedido).json())["codigo"]:
        pedido["escolhas"].append(0)
    return corpo


def test_resposta_final_traz_a_posicao_do_clube(game) -> None:
    corpo = _ate_o_fim(game)

    assert corpo["placar"] == {
        "clube": "Bahia",
        "pelo": "pelo Bahia",
        "carreiras": 1,
        "posicao": 1,
        "novo": True,
    }
    assert corpo["carreira"]["final"]["vereditos"]
    linhas = game.get(f"{API}/placar").json()
    assert linhas[0]["nome"] == "Bahia" and linhas[0]["carreiras"] == 1


def test_mesma_carreira_de_novo_e_link_compartilhado_nao_contam(game) -> None:
    pedido = _comeco(game) | {"semente": "fixa", "escolhas": []}
    while not (corpo := game.post(f"{API}/geral/simular", json=pedido).json())["codigo"]:
        pedido["escolhas"].append(0)
    game.post(f"{API}/geral/simular", json=pedido)  # the same final request: a retry
    game.get(f"/jogos/carreira/c/{corpo['codigo']}")

    assert game.get(f"{API}/placar").json()[0]["carreiras"] == 1


def test_limite_por_rede_nao_quebra_a_carreira(store, mailer, clock) -> None:
    from geral.web import app as web

    limite = web.CARREIRAS_POR_REDE
    web.CARREIRAS_POR_REDE = 2
    try:
        game = make_client(store, mailer, clock)
        contadas = [_ate_o_fim(game, f"s{i}")["placar"] for i in range(3)]
    finally:
        web.CARREIRAS_POR_REDE = limite

    assert contadas[1]["carreiras"] == 2 and contadas[2] is None  # the third still ends fine
    assert game.get(f"{API}/placar").json()[0]["carreiras"] == 2


def _final_em(game, clube: str) -> tuple[dict, dict]:
    """A finished career starting at `clube`: (the last request, its answer)."""
    oferta = game.post(f"{API}/geral/oferta", json={"clube": clube}).json()
    roubos = [
        {"lenda": x["nome"], "atributo": a}
        for x, a in zip(oferta["lendas"], regras.ATRIBUTOS, strict=False)
    ]
    pedido = {
        "semente_draft": oferta["semente_draft"],
        "semente": "fixa",
        "craque": CRAQUE | {"clube": clube},
        "roubos": roubos,
        "escolhas": [],
    }
    while not (corpo := game.post(f"{API}/geral/simular", json=pedido).json())["codigo"]:
        pedido["escolhas"].append(0)
    return pedido, corpo


def test_mais_um_craque_concorda_com_o_clube_e_repeticao_nao_conta_de_novo(game) -> None:
    pedido, corpo = _final_em(game, "ponte-preta")

    assert corpo["placar"]["pelo"] == "pela Ponte Preta" and corpo["placar"]["novo"] is True
    de_novo = game.post(f"{API}/geral/simular", json=pedido).json()["placar"]
    assert de_novo["novo"] is False and de_novo["carreiras"] == 1


def test_link_forjado_de_carreira_inacabada_mostra_so_o_resumo(game) -> None:
    import json
    import re

    from geral.games.carreira.codigo import codificar

    _, corpo = _final_em(game, "bahia")
    aberto = decodificar(corpo["codigo"])
    inacabada = aberto.entrada.model_copy(update={"escolhas": [], "modo": "completa"})
    codigo = codificar(aberto.versao, aberto.edicao, inacabada, aberto.resumo)

    page = game.get(f"/jogos/carreira/c/{codigo}")

    assert page.status_code == 200
    dados = json.loads(re.search(r'id="cr-data">(.*?)</script>', page.text, re.S).group(1))
    assert dados["compartilhada"]["carreira"] is None


def test_placar_com_banco_fora_responde_503(game, monkeypatch) -> None:
    import sqlite3

    from geral.web.carreira_placar import PlacarStore

    def quebra(self, limite):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(PlacarStore, "ranking", quebra)

    assert game.get(f"{API}/placar").status_code == 503


def test_nome_so_com_espacos_e_422(game) -> None:
    pedido = _comeco(game) | {"escolhas": []}
    pedido["craque"] = CRAQUE | {"nome": "   "}

    assert game.post(f"{API}/geral/simular", json=pedido).status_code == 422


def test_link_antigo_ainda_abre(game) -> None:
    from test_carreira_codigo import LINK_ANTIGO

    page = game.get(f"/jogos/carreira/c/{LINK_ANTIGO}")

    assert page.status_code == 200 and "Artilheiro nato" in page.text


def test_payload_traz_opcao_arriscada_e_marcas_do_final(game) -> None:
    from test_carreira_caminhos import _mais_arriscada, jogar
    from test_carreira_motor import entrada

    from geral.games.carreira.dados import carregar

    dados = carregar()
    for i in range(100):
        e = entrada(f"p{i}").model_copy(update={"modo": "completa"})
        carreira, e, perguntas = jogar(dados, e, _mais_arriscada)
        risco = next((n for n, p in enumerate(perguntas) if any(x.arriscada for x in p.info)), None)
        if risco is not None and carreira.final.marcas:
            break
    else:
        pytest.fail("nenhuma carreira com opção arriscada e marca em 100 sementes")
    pedido = e.model_dump()

    pendente = game.post(f"{API}/geral/simular", json=pedido | {"escolhas": e.escolhas[:risco]})
    fim = game.post(f"{API}/geral/simular", json=pedido)

    info = pendente.json()["carreira"]["pendente"]["info"]
    assert any(x["arriscada"] for x in info)
    final = fim.json()["carreira"]["final"]
    assert final["marcas"] == carreira.final.marcas and final["posicao"]
    marcas = [m for t in fim.json()["carreira"]["temporadas"] for m in t["marcas"]]
    assert len(marcas) >= 1


def test_link_mostra_a_posicao_final(game) -> None:
    from test_carreira_caminhos import _mais_arriscada, jogar
    from test_carreira_motor import entrada

    from geral.games.carreira.codigo import codificar, resumir
    from geral.games.carreira.dados import carregar

    dados = carregar()
    for i in range(200):
        e = entrada(f"p{i}").model_copy(update={"modo": "completa"})
        carreira, e, _ = jogar(dados, e, _mais_arriscada)
        if carreira.final.posicao != e.craque.posicao:
            break
    else:
        pytest.fail("nenhuma carreira que mudou de posição em 200 sementes")
    codigo = codificar(dados.versao, "geral", e, resumir(e, carreira), dados)

    page = game.get(f"/jogos/carreira/c/{codigo}")

    assert f"A carreira de Zé · {carreira.final.posicao}" in page.text


def test_pagina_nao_oferece_mais_o_modo_rapida(game) -> None:
    page = game.get("/jogos/carreira").text
    assert 'data-modo="rapida"' not in page and "cr-modes" not in page


def test_carreira_nova_sem_modo_e_completa(game) -> None:
    pedido = _comeco(game) | {"semente": "fixa", "escolhas": []}
    corpo = game.post(f"{API}/geral/simular", json=pedido).json()
    assert corpo["carreira"]["pendente"]["tipo"] == "dia"
