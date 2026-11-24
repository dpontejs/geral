import json
import re
import sqlite3

import pytest
from setea0_fake import dados_de_teste
from setea0_times import gulosas
from webkit import make_client

from geral.games.setea0 import dados as setea0_dados
from geral.games.setea0 import motor

API = "/api/jogos/7a0/abc"
SEMENTE = "s48"  # the greedy XI wins it all, with two shootouts (games 2 and 4)
DADOS = dados_de_teste()


@pytest.fixture
def publicado(monkeypatch):
    monkeypatch.setattr(setea0_dados, "carregar", lambda: DADOS)
    monkeypatch.setitem(setea0_dados.chaves()["edicao"]["abc"], "publicado", True)
    monkeypatch.delenv("SETEA0_PREVIA", raising=False)


@pytest.fixture
def game(publicado, store, mailer, clock):
    return make_client(store, mailer, clock)


def _dados_da_pagina(html: str) -> dict:
    achado = re.search(r'<script type="application/json" id="s7-data">(.*?)</script>', html, re.S)
    assert achado, "page JSON missing"
    return json.loads(achado.group(1))


def _terminada(semente: str = SEMENTE, esquema: str = "4-4-2") -> dict:
    """A finished campaign's last call: the greedy XI, the engine taking every penalty."""
    escolhas = gulosas(DADOS, "abc", semente, esquema)
    feita = motor.campanha_motor(DADOS, "abc", semente, "classico", esquema, escolhas)
    return {
        "semente": semente,
        "versao": DADOS.versao,
        "modo": "classico",
        "esquema": esquema,
        "escolhas": [e.model_dump() for e in escolhas],
        "cobrancas": [
            [{"resultado": "motor"}] * len(p.disputa.nossas) for p in feita.partidas if p.disputa
        ],
        "n": len(feita.partidas),
    }


def _guardadas(store) -> int:
    with sqlite3.connect(store.path) as db:
        return db.execute("SELECT COUNT(*) FROM setea0_guardado").fetchone()[0]


def test_pagina_do_clube_publicado(game) -> None:
    resposta = game.get("/jogos/7a0/abc")

    assert resposta.status_code == 200
    jogo = _dados_da_pagina(resposta.text)
    assert jogo["edicao"] == "abc" and jogo["nome"] == "ABC"
    assert "4-3-3" in jogo["esquemas"] and set(jogo["modos"]) == {"classico", "almanaque"}
    escolha = game.get("/jogos/7a0")
    assert escolha.status_code == 200 and "/jogos/7a0/abc" in escolha.text


def test_clube_nao_publicado_da_404(game, monkeypatch) -> None:
    monkeypatch.setitem(setea0_dados.chaves()["edicao"]["nautico"], "publicado", False)
    assert game.get("/jogos/7a0/nautico").status_code == 404
    assert game.post("/api/jogos/7a0/nautico/oferta", json={"rodada": 0}).status_code == 404
    assert game.get("/jogos/7a0/nao-existe").status_code == 404

    monkeypatch.setenv("SETEA0_PREVIA", "1")
    monkeypatch.setitem(setea0_dados.chaves()["edicao"]["abc"], "publicado", False)
    assert game.get("/jogos/7a0/abc").status_code == 200


def test_oferta_sorteia_semente(game) -> None:
    resposta = game.post(f"{API}/oferta", json={"rodada": 0, "troca": 0, "modo": "classico"})

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["semente"] and corpo["versao"] == DADOS.versao
    assert corpo["epoca"]["rotulo"].startswith("anos ")
    assert corpo["trocas_restantes"] == 3
    jogador = corpo["jogadores"][0]
    assert set(jogador) == {"id", "nome", "posicoes", "anos", "estrelas", "idolo"}
    assert re.fullmatch(r"\d{4}(–\d{4})?", jogador["anos"])
    assert all(1 <= j["estrelas"] <= 5 for j in corpo["jogadores"])
    assert "forca" not in resposta.text
    outra = game.post(f"{API}/oferta", json={"rodada": 0, "troca": 0}).json()
    assert outra["semente"] != corpo["semente"]
    mesma = game.post(f"{API}/oferta", json={"semente": corpo["semente"], "rodada": 0, "troca": 0})
    assert mesma.json() == corpo


def test_estrelas_vao_de_1_a_5(game) -> None:
    rodada = motor.oferta(DADOS, "abc", "fixa", 0, 0)
    corpo = game.post(f"{API}/oferta", json={"semente": "fixa", "rodada": 0, "troca": 0}).json()

    esperadas = [1 + (j.forca - 1) * 5 // 99 for j in rodada.jogadores]
    assert [j["estrelas"] for j in corpo["jogadores"]] == esperadas


def test_almanaque_sem_estrelas(game) -> None:
    corpo = game.post(
        f"{API}/oferta", json={"semente": "fixa", "rodada": 0, "troca": 1, "modo": "almanaque"}
    ).json()

    assert corpo["trocas_restantes"] == 0
    assert all(j["estrelas"] is None for j in corpo["jogadores"])
    estourou = game.post(
        f"{API}/oferta", json={"semente": "fixa", "rodada": 0, "troca": 2, "modo": "almanaque"}
    )
    assert estourou.status_code == 422


def test_campanha_inteira_pela_api(game, store) -> None:
    escolhas = gulosas(DADOS, "abc", SEMENTE)
    for escolha in escolhas:
        oferta = game.post(
            f"{API}/oferta", json={"semente": SEMENTE, "rodada": escolha.rodada, "troca": 0}
        ).json()
        assert escolha.jogador in {j["id"] for j in oferta["jogadores"]}
    pedido = _terminada() | {"cobrancas": [], "n": 1}
    disputa_de = None  # the game the last shootout list belongs to
    pedidos = 0
    while True:
        resposta = game.post(f"{API}/jogo", json=pedido)
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["adversario"]["nome"]
        if "pedido" in corpo:
            pedidos += 1
            if corpo["pedido"]["n"] != disputa_de:
                pedido["cobrancas"].append([])
                disputa_de = corpo["pedido"]["n"]
            pedido["cobrancas"][-1].append({"resultado": "motor"})
            continue
        assert corpo["partida"]["n"] == pedido["n"]
        if corpo["fim"]:
            break
        assert corpo["campanha"] is None and corpo["codigo"] is None
        pedido["n"] += 1

    assert pedidos > 0 and len(pedido["cobrancas"]) == 2
    assert corpo["partida"]["n"] == 7 and corpo["campanha"]["campeao"]
    assert corpo["codigo"] and len(corpo["codigo"]) == 10
    assert corpo["campanha"] == motor.campanha_motor(
        DADOS, "abc", SEMENTE, "classico", "4-4-2", escolhas
    ).model_dump(mode="json")
    game.post(f"{API}/jogo", json=pedido)  # the same campaign finished twice: one row
    assert _guardadas(store) == 1


def test_link_abre_apos_mudar_os_dados(game, monkeypatch) -> None:
    corpo = game.post(f"{API}/jogo", json=_terminada()).json()
    novos = dados_de_teste(semente=8).model_copy(update={"versao": "outra"})
    monkeypatch.setattr(setea0_dados, "carregar", lambda: novos)

    resposta = game.get(f"/jogos/7a0/c/{corpo['codigo']}")

    assert resposta.status_code == 200
    compartilhada = _dados_da_pagina(resposta.text)["compartilhada"]
    assert compartilhada["codigo"] == corpo["codigo"]
    assert compartilhada["campanha"] == corpo["campanha"]
    assert compartilhada["adversarios"]["america-rn"]


def test_link_desconhecido_da_404(game) -> None:
    resposta = game.get("/jogos/7a0/c/naoexiste0")

    assert resposta.status_code == 404
    assert "Esse link do 7a0 não abre. Que tal montar o seu time?" in resposta.text


def test_versao_diferente_da_409(game) -> None:
    for caminho, corpo in [
        ("oferta", {"semente": "x", "versao": "velha", "rodada": 0}),
        ("jogo", _terminada() | {"versao": "velha"}),
    ]:
        resposta = game.post(f"{API}/{caminho}", json=corpo)
        assert resposta.status_code == 409
        assert resposta.json() == {
            "detail": "O 7a0 foi atualizado enquanto você jogava. Comece um time novo.",
            "atualizado": True,
        }


def test_cobranca_forjada_da_422_e_nao_guarda(game, store) -> None:
    certa = _terminada()
    sobra = certa | {"cobrancas": [*certa["cobrancas"], [{"resultado": "gol"}]]}
    a_mais = certa | {"cobrancas": [c + [{"resultado": "gol"}] for c in certa["cobrancas"]]}
    escolhas = [dict(e) for e in certa["escolhas"]]
    escolhas[0]["jogador"] = "Qnao-estava"
    fora_da_oferta = certa | {"escolhas": escolhas}

    for forjada in (sobra, a_mais, fora_da_oferta):
        assert game.post(f"{API}/jogo", json=forjada).status_code == 422

    assert _guardadas(store) == 0


def test_limite_por_rede_nao_guarda(publicado, store, mailer, clock, monkeypatch) -> None:
    monkeypatch.setattr("geral.web.app.SETEA0_POR_REDE", 2)
    game = make_client(store, mailer, clock)
    codigos = []
    for semente in (SEMENTE, "s4", "s5"):
        resposta = game.post(f"{API}/jogo", json=_terminada(semente))
        assert resposta.status_code == 200 and resposta.json()["fim"]
        codigos.append(resposta.json()["codigo"])

    assert codigos[0] and codigos[1] and codigos[2] is None
    assert _guardadas(store) == 2
    repetida = game.post(f"{API}/jogo", json=_terminada(SEMENTE)).json()
    assert repetida["codigo"] == codigos[0]  # a campaign already kept keeps its link


def test_pagina_tem_o_js_e_os_dados(game) -> None:
    html = game.get("/jogos/7a0/abc").text
    assert "/static/geral/setea0.js" in html and "/static/geral/penalti.js" in html
    assert 'id="s7-escalar"' in html  # the screens are on the page
    assert 'id="s7-pontos-pen"' in html and 'id="s7-pen-jogo"' in html  # the shootout lamps
    jogo = _dados_da_pagina(html)
    assert jogo["edicao"] == "abc" and jogo["nome"] == "ABC"
    assert jogo["esquemas"]["4-3-3"][0] == "GOL" and len(jogo["esquemas"]["4-3-3"]) == 11
    chave = setea0_dados.chaves()["edicao"]["abc"]
    assert jogo["chave"] == [*chave["adversarios"], chave["final"]]
    assert jogo["adversarios"]["america-rn"] == "América-RN"


def test_card_compartilhado_traz_os_nomes_dos_adversarios(game) -> None:
    codigo = game.post(f"{API}/jogo", json=_terminada()).json()["codigo"]
    jogo = _dados_da_pagina(game.get(f"/jogos/7a0/c/{codigo}").text)
    adversarios = {p["adversario"] for p in jogo["compartilhada"]["campanha"]["partidas"]}
    assert adversarios <= set(jogo["compartilhada"]["adversarios"])


def test_almanaque_nao_entrega_a_forca_pela_ordem(game) -> None:
    def nomes(modo):
        corpo = {"semente": "fixa", "rodada": 0, "troca": 0, "modo": modo}
        return [j["nome"] for j in game.post(f"{API}/oferta", json=corpo).json()["jogadores"]]

    classico, almanaque = nomes("classico"), nomes("almanaque")
    assert sorted(classico) == sorted(almanaque)  # the same draw
    assert almanaque == sorted(almanaque)  # but in name order, not by strength


def test_escolha_do_clube_tem_um_cartao_por_clube(game) -> None:
    html = game.get("/jogos/7a0").text
    cartoes = re.findall(r'<article class="board hub-card s7-clube">(.*?)</article>', html, re.S)
    publicados = [s for s, e in setea0_dados.chaves()["edicao"].items() if e["publicado"]]
    assert len(cartoes) == len(publicados)
    abc = next(c for c in cartoes if 'href="/jogos/7a0/abc"' in c)
    assert "América-RN" in abc and "Nordeste" in abc


def test_pagina_do_jogo_tem_a_barra_dos_clubes(game) -> None:
    html = game.get("/jogos/7a0/abc").text
    barra = re.search(r'<nav class="editions"[^>]*>(.*?)</nav>', html, re.S)
    assert barra, "no editions bar"
    publicados = [s for s, e in setea0_dados.chaves()["edicao"].items() if e["publicado"]]
    for slug in publicados:
        assert f'href="/jogos/7a0/{slug}"' in barra.group(1)
    assert re.search(r'href="/jogos/7a0/abc" aria-current="page"', barra.group(1))
