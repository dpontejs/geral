"""Prancheta pages: create a room, the live room, the súmula and the notice for a gone room."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from geral.web.app import templates
from geral.web.prancheta_paginas import paginas_prancheta

SUMULA = {
    "id": "K7M2QX",
    "jogadores": [
        {"apelido": "Marquinho", "pontos": 31, "gols": 4, "assist": 3},
        {"apelido": "Zé da Geral", "pontos": 24, "gols": 3, "assist": 2},
    ],
    "lances": [
        {"desenhista": "Marquinho", "palavra": "Gol olímpico", "acertaram": ["Zé da Geral"]},
        {"desenhista": "Zé da Geral", "palavra": "Frasqueira", "acertaram": []},
    ],
}


class PranchetaFalsa:
    """Only what the pages ask of slice D's `Prancheta`."""

    def __init__(self, vivas=(), sumulas=None) -> None:
        self.vivas = set(vivas)
        self.sumulas = sumulas or {}

    def viva(self, sala_id: str) -> bool:
        return sala_id in self.vivas

    def sumula(self, sala_id: str) -> dict | None:
        return self.sumulas.get(sala_id)


def render(request: Request, name: str, status: int = 200, **context):
    context.setdefault("public_url", "https://geral.test")
    context.setdefault("tabs", [])
    return templates.TemplateResponse(request, name, context, status_code=status)


@pytest.fixture
def cliente():
    def fazer(prancheta: PranchetaFalsa) -> TestClient:
        app = FastAPI()
        app.include_router(paginas_prancheta(prancheta, render))
        return TestClient(app, base_url="https://geral.test")

    return fazer


def test_pagina_de_criar(cliente):
    resposta = cliente(PranchetaFalsa()).get("/jogos/prancheta")
    assert resposta.status_code == 200
    html = resposta.text
    assert "<h1>Prancheta</h1>" in html
    assert 'data-sala=""' in html
    assert "prancheta.js" in html and "prancheta.css" in html


def test_sala_viva_abre_o_jogo(cliente):
    resposta = cliente(PranchetaFalsa(vivas={"K7M2QX"})).get("/jogos/prancheta/s/K7M2QX")
    assert resposta.status_code == 200
    assert 'data-sala="K7M2QX"' in resposta.text
    assert "prancheta.js" in resposta.text


def test_sala_encerrada_mostra_sumula(cliente):
    prancheta = PranchetaFalsa(sumulas={"K7M2QX": SUMULA})
    resposta = cliente(prancheta).get("/jogos/prancheta/s/K7M2QX")
    assert resposta.status_code == 200
    html = resposta.text
    assert 'id="pr-sumula"' in html
    for nome in ("Marquinho", "Zé da Geral", "Gol olímpico", "Frasqueira"):
        assert nome in html
    assert "ninguém acertou" in html
    assert "<canvas" not in html  # the súmula never has a drawing
    assert "prancheta.js" not in html  # nothing live on the súmula


def test_sumula_vale_mais_que_sala_viva(cliente):
    """A room that just ended may still be in memory: its link already shows the súmula."""
    prancheta = PranchetaFalsa(vivas={"K7M2QX"}, sumulas={"K7M2QX": SUMULA})
    assert 'id="pr-sumula"' in cliente(prancheta).get("/jogos/prancheta/s/K7M2QX").text


def test_sala_inexistente_mostra_aviso(cliente):
    resposta = cliente(PranchetaFalsa()).get("/jogos/prancheta/s/ZZZZZZ")
    assert resposta.status_code == 404
    assert "a sala acabou ou o servidor reiniciou" in resposta.text.lower()
    assert "Nova sala" in resposta.text
    assert 'href="/jogos/prancheta"' in resposta.text


def test_apelidos_da_sumula_escapados(cliente):
    sumula = SUMULA | {
        "jogadores": [{"apelido": "<b>x</b>", "pontos": 1, "gols": 1, "assist": 0}],
        "lances": [],
    }
    html = cliente(PranchetaFalsa(sumulas={"AAAAAA": sumula})).get("/jogos/prancheta/s/AAAAAA")
    assert "<b>x</b>" not in html.text
    assert "&lt;b&gt;x&lt;/b&gt;" in html.text


def test_app_liga_as_paginas_ao_servidor(store, mailer, clock):
    """In the real app: a room created by the API opens the game at its short link."""
    from webkit import make_client

    app = make_client(store, mailer, clock)
    sala = app.post("/api/jogos/prancheta/salas", json={"apelido": "Marquinho", "rodadas": 1})
    assert sala.status_code == 201
    pagina = app.get(f"/jogos/prancheta/s/{sala.json()['id']}")
    assert pagina.status_code == 200
    assert f'data-sala="{sala.json()["id"]}"' in pagina.text
    assert app.get("/jogos/prancheta").status_code == 200
    assert app.get("/jogos/prancheta/s/zzzzzz").status_code == 404
