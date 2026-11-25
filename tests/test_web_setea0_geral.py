"""The 7a0 da Geral on the site, and the opponents' lineups on every 7a0 page."""

import json
import re

import pytest
from setea0_fake import dados_de_teste, dados_geral_de_teste
from setea0_times import gulosas
from webkit import make_client

from geral.games.setea0 import dados as setea0_dados
from geral.games.setea0 import motor

API = "/api/jogos/7a0/geral"
DADOS = dados_geral_de_teste()


@pytest.fixture
def game(monkeypatch, store, mailer, clock):
    monkeypatch.setattr(setea0_dados, "carregar", lambda: DADOS)
    monkeypatch.delenv("SETEA0_PREVIA", raising=False)
    return make_client(store, mailer, clock)


def _dados_da_pagina(html: str) -> dict:
    achado = re.search(r'<script type="application/json" id="s7-data">(.*?)</script>', html, re.S)
    assert achado, "page JSON missing"
    return json.loads(achado.group(1))


def test_pagina_da_geral(game) -> None:
    resposta = game.get("/jogos/7a0/geral")

    assert resposta.status_code == 200
    assert 'id="s7-escalar"' in resposta.text  # the game, not the club choice
    jogo = _dados_da_pagina(resposta.text)
    assert jogo["edicao"] == "geral" and jogo["nome"] == "Geral" and jogo["do_nome"] == "da Geral"
    assert jogo["chave"] == motor.adversarios(DADOS, "geral")
    for slug in jogo["chave"]:
        assert jogo["adversarios"][slug] == setea0_dados.chaves()["clube"][slug]["nome"]
    for slug in motor.clubes_da_geral(DADOS):  # the era labels name the club
        assert jogo["adversarios"][slug] == setea0_dados.chaves()["edicao"][slug]["nome"]


def test_geral_fechada_sem_clube_publicado(game, monkeypatch) -> None:
    for edicao in setea0_dados.chaves()["edicao"].values():
        monkeypatch.setitem(edicao, "publicado", False)
    assert game.get("/jogos/7a0/geral").status_code == 404
    assert game.post(f"{API}/oferta", json={"rodada": 0}).status_code == 404


def test_oferta_da_geral_traz_o_clube(game) -> None:
    corpo = game.post(f"{API}/oferta", json={"semente": "fixa", "rodada": 0, "troca": 0}).json()

    rodada = motor.oferta(DADOS, "geral", "fixa", 0, 0)
    assert corpo["epoca"] == {"rotulo": rodada.epoca.rotulo, "clube": rodada.epoca.clube}
    assert corpo["epoca"]["clube"] in motor.clubes_da_geral(DADOS)
    assert [j["id"] for j in corpo["jogadores"]] == [j.id for j in rodada.jogadores]


def test_campanha_da_geral_pela_api_e_o_card(game) -> None:
    semente = "geral1"
    escolhas = gulosas(DADOS, "geral", semente)
    feita = motor.campanha_motor(DADOS, "geral", semente, "classico", "4-4-2", escolhas)
    corpo = {
        "semente": semente,
        "versao": DADOS.versao,
        "modo": "classico",
        "esquema": "4-4-2",
        "escolhas": [e.model_dump() for e in escolhas],
        "cobrancas": [
            [{"resultado": "motor"}] * len(p.disputa.nossas) for p in feita.partidas if p.disputa
        ],
        "n": len(feita.partidas),
    }
    resposta = game.post(f"{API}/jogo", json=corpo).json()

    assert resposta["fim"] and resposta["codigo"]
    assert resposta["campanha"] == feita.model_dump(mode="json")
    card = game.get(f"/jogos/7a0/c/{resposta['codigo']}")
    assert card.status_code == 200
    jogo = _dados_da_pagina(card.text)
    nomes = jogo["compartilhada"]["adversarios"]
    for e in feita.escalacao:  # the card names each player's club
        assert nomes[e.epoca.clube] == DADOS.clubes[e.epoca.clube].nome
    assert 'href="/jogos/7a0/geral"' in card.text  # "jogar o seu" goes to the Geral


def test_escolha_tem_o_cartao_da_geral_e_a_barra_tambem(game, monkeypatch) -> None:
    escolha = game.get("/jogos/7a0").text
    geral = re.search(r'<article class="board hub-card s7-geral">(.*?)</article>', escolha, re.S)
    assert geral and 'href="/jogos/7a0/geral"' in geral.group(1)

    def barra(pagina: str) -> str:
        html = game.get(pagina).text
        achada = re.search(r'<nav class="editions"[^>]*>(.*?)</nav>', html, re.S)
        assert achada, pagina
        return achada.group(1)

    assert 'href="/jogos/7a0/geral" aria-current="page"' in barra("/jogos/7a0/geral")
    monkeypatch.setattr(setea0_dados, "carregar", dados_de_teste)  # the ABC's bracket
    assert 'href="/jogos/7a0/geral"' in barra("/jogos/7a0/abc")


@pytest.mark.parametrize(("edicao", "fake"), [("geral", DADOS), ("abc", dados_de_teste())])
def test_pagina_traz_a_escalacao_de_cada_adversario(game, monkeypatch, edicao, fake) -> None:
    monkeypatch.setattr(setea0_dados, "carregar", lambda: fake)
    jogo = _dados_da_pagina(game.get(f"/jogos/7a0/{edicao}").text)

    assert set(jogo["escalacoes"]) == set(jogo["chave"])
    for slug, escalacao in jogo["escalacoes"].items():
        time = motor.adversario(fake, slug)
        assert escalacao["esquema"] == "4-4-2"
        assert [j["nome"] for j in escalacao["jogadores"]] == [j.nome for j in time]
        assert [j["posicao"] for j in escalacao["jogadores"]] == list(motor.ESQUEMAS["4-4-2"])
        assert escalacao["anos"] == ""  # the velha's all-time XIs have no years
