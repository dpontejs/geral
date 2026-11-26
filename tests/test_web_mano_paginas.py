"""Mano a Mano pages: create a room, the live room, the súmula and the notice for a gone room."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from geral.web.app import templates
from geral.web.mano_paginas import paginas_mano

SUMULA = {
    "id": "k7m2qx-1",
    "sala": "k7m2qx",
    "partida": 1,
    "modo": "penaltis",
    "jogadores": [
        {"apelido": "Marquinho", "bot": False},
        {"apelido": "Zé da Geral", "bot": False},
    ],
    "placar": [3, 2],
    "vencedor": 0,
    "wo": False,
    "cobrancas": [
        {"batedor": 0, "resultado": "gol", "onde": [120, 300]},
        {"batedor": 1, "resultado": "defesa", "onde": [800, 200]},
        {"batedor": 0, "resultado": "trave", "onde": [0, 500]},
        {"batedor": 1, "resultado": "gol", "onde": [500, 900]},
    ],
}


class ManoFalso:
    """Only what the pages ask of the server's `Mano`."""

    def __init__(self, vivas=(), sumulas=None, cheias=(), faltas=True) -> None:
        self.faltas = faltas
        self.vivas = set(vivas)
        self.sumulas = sumulas or {}
        self.cheias = set(cheias)

    def cheia(self, sala_id: str) -> bool:
        return sala_id in self.cheias

    def viva(self, sala_id: str) -> bool:
        return sala_id in self.vivas

    def sumula(self, id_: str) -> dict | None:
        if id_ in self.sumulas:
            return self.sumulas[id_]
        da_sala = [s for s in self.sumulas.values() if s.get("sala") == id_]
        return da_sala[-1] if da_sala else None


def render(request: Request, name: str, status: int = 200, **context):
    context.setdefault("public_url", "https://geral.test")
    context.setdefault("tabs", [])
    return templates.TemplateResponse(request, name, context, status_code=status)


@pytest.fixture
def cliente():
    def fazer(mano: ManoFalso) -> TestClient:
        app = FastAPI()
        app.include_router(paginas_mano(mano, render))
        return TestClient(app, base_url="https://geral.test")

    return fazer


def test_pagina_de_criar_abre(cliente):
    resposta = cliente(ManoFalso()).get("/jogos/mano")
    assert resposta.status_code == 200
    html = resposta.text
    assert "<h1>Mano a Mano</h1>" in html
    assert 'data-sala=""' in html
    assert "mano.js" in html and "mano.css" in html
    assert 'type="module"' in html  # the scene is an ES module
    assert "Como jogar" in html


def test_link_de_sala_viva_abre_o_jogo(cliente):
    resposta = cliente(ManoFalso(vivas={"k7m2qx"})).get("/jogos/mano/s/k7m2qx")
    assert resposta.status_code == 200
    assert 'data-sala="k7m2qx"' in resposta.text
    assert "mano.js" in resposta.text


def test_link_de_sala_cheia_avisa_sem_pedir_apelido(cliente):
    """A full room (or a match against the bot): the page knows before the join form."""
    cheia = cliente(ManoFalso(vivas={"k7m2qx"}, cheias={"k7m2qx"})).get("/jogos/mano/s/k7m2qx")
    assert 'data-cheia="1"' in cheia.text
    livre = cliente(ManoFalso(vivas={"k7m2qx"})).get("/jogos/mano/s/k7m2qx")
    assert 'data-cheia=""' in livre.text


def test_sala_viva_vale_mais_que_sumula(cliente):
    """A finished match waits for the rematch: the room's link is still the live room."""
    mano = ManoFalso(vivas={"k7m2qx"}, sumulas={"k7m2qx-1": SUMULA})
    html = cliente(mano).get("/jogos/mano/s/k7m2qx").text
    assert 'data-sala="k7m2qx"' in html and 'id="mn-sumula"' not in html


@pytest.mark.parametrize("caminho", ["k7m2qx-1", "k7m2qx"])
def test_link_de_sala_encerrada_mostra_a_sumula(cliente, caminho):
    resposta = cliente(ManoFalso(sumulas={"k7m2qx-1": SUMULA})).get(f"/jogos/mano/s/{caminho}")
    assert resposta.status_code == 200
    html = resposta.text
    assert 'id="mn-sumula"' in html
    for texto in ("Marquinho", "Zé da Geral", "Pênaltis", "Sala k7m2qx · partida 1"):
        assert texto in html
    assert "Marquinho venceu" in html
    for resultado in ("Gol", "Defendeu", "Na trave"):
        assert resultado in html
    assert "https://geral.test/jogos/mano/s/k7m2qx-1" in html  # each match's own link
    assert "mano.js" not in html  # nothing live on the súmula
    assert 'href="/jogos/mano"' in html


def test_sumula_por_wo_e_contra_o_bot(cliente):
    sumula = SUMULA | {
        "modo": "faltas",
        "jogadores": [
            {"apelido": "Marquinho", "bot": False},
            {"apelido": "Bot difícil", "bot": True},
        ],
        "placar": [0, 1],
        "vencedor": 1,
        "wo": True,
        "cobrancas": [{"batedor": 1, "resultado": "gol", "onde": [100, 100]}],
    }
    html = cliente(ManoFalso(sumulas={"k7m2qx-1": sumula})).get("/jogos/mano/s/k7m2qx-1").text
    assert "Faltas" in html
    assert "W.O." in html
    assert "Bot difícil venceu" in html


def test_sumula_empatada_sem_vencedor(cliente):
    sumula = SUMULA | {"placar": [0, 0], "vencedor": None, "cobrancas": []}
    html = cliente(ManoFalso(sumulas={"k7m2qx-1": sumula})).get("/jogos/mano/s/k7m2qx-1").text
    assert "Sem vencedor" in html
    assert "acabou antes da primeira cobrança" in html


def test_apelidos_da_sumula_escapados(cliente):
    sumula = SUMULA | {"jogadores": [{"apelido": "<b>x</b>", "bot": False}, SUMULA["jogadores"][1]]}
    html = cliente(ManoFalso(sumulas={"k7m2qx-1": sumula})).get("/jogos/mano/s/k7m2qx-1").text
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_sala_inexistente_mostra_aviso(cliente):
    resposta = cliente(ManoFalso()).get("/jogos/mano/s/zzzzzz")
    assert resposta.status_code == 404  # as the Prancheta's: the notice page, not a broken game
    assert "a sala acabou ou o servidor reiniciou" in resposta.text.lower()
    assert "Nova sala" in resposta.text
    assert 'href="/jogos/mano"' in resposta.text


def test_app_liga_as_paginas_ao_servidor(store, mailer, clock):
    """In the real app: a room created by the API opens the game at its short link."""
    from webkit import make_client

    app = make_client(store, mailer, clock)
    sala = app.post(
        "/api/jogos/mano/salas", json={"apelido": "Marquinho", "time": "abc", "modo": "penaltis"}
    )
    assert sala.status_code == 201
    pagina = app.get(f"/jogos/mano/s/{sala.json()['id']}")
    assert pagina.status_code == 200
    assert f'data-sala="{sala.json()["id"]}"' in pagina.text
    assert app.get("/jogos/mano").status_code == 200
    assert app.get("/jogos/mano/s/zzzzzz").status_code == 404


def test_jogos_tem_o_cartao_do_mano_a_mano(store, mailer, clock):
    from webkit import make_client

    app = make_client(store, mailer, clock)
    jogos = app.get("/jogos").text
    assert "Mano a Mano" in jogos and 'href="/jogos/mano"' in jogos
    assert 'href="/jogos/mano"' in app.get("/jogos/velha").text  # in every game's tabs
    propria = app.get("/jogos/mano").text
    assert 'href="/jogos/mano" aria-current="page">Mano a Mano' in propria


def test_vendor_com_cache_longo_e_gzip(store, mailer, clock):
    from webkit import make_client

    app = make_client(store, mailer, clock)
    resposta = app.get("/static/vendor/three/three.core.js", headers={"Accept-Encoding": "gzip"})
    assert resposta.status_code == 200
    assert resposta.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert resposta.headers["content-encoding"] == "gzip"
    assert "REVISION = '187'" in resposta.text  # the client unzipped it: the file itself
    # the rest of /static keeps its own caching and is not zipped here
    outro = app.get("/static/geral/mano.css", headers={"Accept-Encoding": "gzip"})
    assert "immutable" not in outro.headers.get("cache-control", "")
    assert "content-encoding" not in outro.headers


def test_cena_importada_com_a_versao_dos_arquivos(store, mailer, clock):
    """mano.js imports mano-cena.js: an import map pins it to the deploy's version."""
    from webkit import make_client

    html = make_client(store, mailer, clock).get("/jogos/mano").text
    assert '<script type="importmap">' in html
    assert '"/static/geral/mano-cena.js": "/static/geral/mano-cena.js?v=' in html


def test_sem_faltas_a_pagina_nem_oferece_nem_explica(cliente):
    ligada = cliente(ManoFalso()).get("/jogos/mano").text
    assert 'data-faltas="1"' in ligada and "barreira" in ligada
    desligada = cliente(ManoFalso(faltas=False)).get("/jogos/mano").text
    assert 'data-faltas=""' in desligada
    assert "barreira" not in desligada and "pênaltis ou faltas" not in desligada


def test_sumula_com_os_times(cliente):
    sumula = SUMULA | {
        "jogadores": [
            {"apelido": "Marquinho", "bot": False, "time": "flamengo", "time_nome": "Flamengo"},
            {"apelido": "Zé da Geral", "bot": False, "time": "abc", "time_nome": "ABC"},
        ]
    }
    html = cliente(ManoFalso(sumulas={"k7m2qx-1": sumula})).get("/jogos/mano/s/k7m2qx-1").text
    assert "FLAMENGO × ABC" in html
    assert "<td>Flamengo · Marquinho</td>" in html
    assert "Marquinho (Flamengo) venceu" in html


def test_sumula_antiga_sem_times(cliente):
    html = cliente(ManoFalso(sumulas={"k7m2qx-1": SUMULA})).get("/jogos/mano/s/k7m2qx-1").text
    assert "mn-confronto" not in html and "None" not in html
    assert "<td>Marquinho</td>" in html
    assert "Marquinho venceu" in html
