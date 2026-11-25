"""The Prancheta server: rooms in memory, the API routes, the live events (SSE) and the súmula.

Nothing waits on the real clock: `now` is a fake clock, the loop is driven by `passo()`, and the
events stream is read straight from the ASGI app (httpx's ASGITransport buffers whole bodies).
"""

import asyncio
import functools
import json
import logging
import random
import re
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from prancheta_fakes import T0, BancoFalso
from webkit import make_client

from geral.games.prancheta.tipos import normalizar
from geral.web import prancheta as hub
from geral.web.app import RateLimiter
from geral.web.prancheta import criar_prancheta

API = "/api/jogos/prancheta"
ESPERA = 2  # seconds a test waits for an event that must come at once (only when it fails)


def assincrono(teste):
    """Runs an async test in its own event loop (the suite has no async plugin)."""

    @functools.wraps(teste)
    def rodar(*args, **kwargs):
        asyncio.run(teste(*args, **kwargs))

    return rodar


class Relogio:
    def __init__(self) -> None:
        self.agora = T0

    def __call__(self):
        return self.agora

    def andar(self, segundos: float) -> None:
        self.agora += timedelta(seconds=segundos)


class Ouvinte:
    """One browser tab on `/eventos`, talking ASGI to the app so each event arrives as sent.

    `travar` plays a client that vanished without closing: it reads the first event and then
    never takes another one.
    """

    def __init__(self, app: FastAPI, caminho: str, token: str, travar: bool = False) -> None:
        self._app = app
        self._scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": caminho,
            "raw_path": caminho.encode(),
            "query_string": f"token={token}".encode(),
            "headers": [(b"host", b"geral.test")],
            "client": ("10.0.0.1", 1234),
            "server": ("geral.test", 80),
            "root_path": "",
        }
        self._travar = travar
        self._pediu = False
        self._fechou = asyncio.Event()
        self._comecou = asyncio.Event()
        self._buffer = ""
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.eventos: asyncio.Queue = asyncio.Queue()

    async def abrir(self) -> "Ouvinte":
        self._tarefa = asyncio.create_task(self._app(self._scope, self._receive, self._send))
        await asyncio.wait_for(self._comecou.wait(), ESPERA)
        return self

    async def _receive(self) -> dict:
        if not self._pediu:
            self._pediu = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._fechou.wait()
        return {"type": "http.disconnect"}

    async def _send(self, mensagem: dict) -> None:
        if mensagem["type"] == "http.response.start":
            self.status = mensagem["status"]
            self.headers = {k.decode(): v.decode() for k, v in mensagem.get("headers", [])}
            self._comecou.set()
            return
        self._buffer += mensagem.get("body", b"").decode()
        while "\n\n" in self._buffer:
            bloco, self._buffer = self._buffer.split("\n\n", 1)
            self.eventos.put_nowait(_ler_bloco(bloco))
            if self._travar:
                await asyncio.Event().wait()  # never reads again
        if not mensagem.get("more_body", False):
            self.eventos.put_nowait(None)  # the stream closed

    async def proximo(self) -> tuple[str, dict] | None:
        return await asyncio.wait_for(self.eventos.get(), ESPERA)

    async def ate(self, condicao) -> list[tuple[str, dict]]:
        """Events up to and including the first one that matches `condicao(tipo, dados)`."""
        lidos = []
        while True:
            evento = await self.proximo()
            assert evento is not None, f"the stream closed after {lidos}"
            lidos.append(evento)
            if condicao(*evento):
                return lidos

    async def fechar(self) -> None:
        self._fechou.set()
        await asyncio.wait_for(self._tarefa, ESPERA)


def _ler_bloco(bloco: str) -> tuple[str, dict | None]:
    if bloco.startswith(":"):
        return "comentario", None
    campos = dict(linha.split(": ", 1) for linha in bloco.split("\n"))
    return campos["event"], json.loads(campos["data"])


class Mesa:
    """The test's table: the app with only the Prancheta's router, a fake clock and helpers."""

    def __init__(self, tmp_path, limite: int = 20) -> None:
        self.relogio = Relogio()
        self.prancheta = criar_prancheta(
            tmp_path / "geral.db",
            self.relogio,
            RateLimiter(limite, timedelta(hours=1)),
            banco=BancoFalso(),
            rng=random.Random(7),
        )
        self.app = FastAPI()
        self.app.include_router(self.prancheta.router)
        self.ouvintes: list[Ouvinte] = []
        self.anfitrioes: dict[str, str] = {}  # the creator's token, by room

    def cliente(self, ip: str = "10.0.0.1") -> httpx.AsyncClient:
        transporte = httpx.ASGITransport(self.app, client=(ip, 1234))
        return httpx.AsyncClient(transport=transporte, base_url="http://geral.test")

    async def criar(self, apelido: str = "Ana", rodadas: int = 1) -> dict:
        async with self.cliente() as c:
            resposta = await c.post(f"{API}/salas", json={"apelido": apelido, "rodadas": rodadas})
        assert resposta.status_code == 201, resposta.text
        self.anfitrioes[resposta.json()["id"]] = resposta.json()["token"]
        return resposta.json()

    async def pedir(self, sala: str, apelido: str) -> dict:
        async with self.cliente() as c:
            resposta = await c.post(f"{API}/salas/{sala}/entrar", json={"apelido": apelido})
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    async def entrar(self, sala: str, apelido: str) -> dict:
        """Asks to join and the creator (still the host) accepts."""
        pedido = await self.pedir(sala, apelido)
        aceite = await self.agir(sala, self.anfitrioes[sala], "aceitar", pedido=pedido["jogador"])
        assert aceite.status_code == 204, aceite.text
        return pedido

    async def agir(self, sala: str, token: str, tipo: str, **campos) -> httpx.Response:
        async with self.cliente() as c:
            return await c.post(
                f"{API}/salas/{sala}/acao", json={"token": token, "tipo": tipo, **campos}
            )

    async def ouvir(self, sala: str, token: str, travar: bool = False) -> Ouvinte:
        ouvinte = Ouvinte(self.app, f"{API}/salas/{sala}/eventos", token, travar)
        self.ouvintes.append(ouvinte)
        return await ouvinte.abrir()

    async def foto(self, sala: str, token: str) -> dict:
        """The `estado` a new tab of this player gets."""
        ouvinte = await self.ouvir(sala, token)
        tipo, dados = await ouvinte.proximo()
        await ouvinte.fechar()
        assert tipo == "estado"
        return dados

    async def sala_com(self, n: int, rodadas: int = 1) -> tuple[str, dict[int, str]]:
        """A room with `n` players (Ana is the host); returns its id and the tokens by player."""
        criada = await self.criar(rodadas=rodadas)
        tokens = {criada["jogador"]: criada["token"]}
        for apelido in ["Bia", "Caio", "Davi", "Edu"][: n - 1]:
            entrou = await self.entrar(criada["id"], apelido)
            tokens[entrou["jogador"]] = entrou["token"]
        return criada["id"], tokens

    async def em_desenho(self, sala: str, tokens: dict[int, str], indice: int = 0) -> None:
        """Player 1 (the host) starts and draws the word at `indice` (0 = Bicicleta)."""
        assert (await self.agir(sala, tokens[1], "comecar")).status_code == 204
        assert (await self.agir(sala, tokens[1], "escolher", indice=indice)).status_code == 204

    async def fechar(self) -> None:
        for ouvinte in self.ouvintes:
            if not ouvinte._fechou.is_set():
                await ouvinte.fechar()


@asynccontextmanager
async def mesa(tmp_path, **kw):
    m = Mesa(tmp_path, **kw)
    try:
        yield m
    finally:
        await m.fechar()


def traco(id_: int, pts: list[list[int]], fim: bool = True) -> dict:
    return {"id": id_, "cor": 1, "esp": 2, "pts": pts, "fim": fim}


def presenca(foto: dict) -> dict[int, bool]:
    return {j["id"]: j["presente"] for j in foto["jogadores"]}


# --- rotas ---


@assincrono
async def test_criar_e_entrar(tmp_path):
    async with mesa(tmp_path) as m:
        criada = await m.criar("Ana", rodadas=2)
        assert re.fullmatch(r"[a-z2-7]{6}", criada["id"])
        assert criada["jogador"] == 1 and criada["token"]
        entrou = await m.entrar(criada["id"], "Bia")
        assert entrou["jogador"] == 2 and entrou["token"] != criada["token"]
        assert m.prancheta.viva(criada["id"])
        foto = await m.foto(criada["id"], entrou["token"])
        assert foto["voce"] == 2 and foto["rodadas"] == 2
        assert [j["apelido"] for j in foto["jogadores"]] == ["Ana", "Bia"]


@assincrono
async def test_rodadas_fora_422(tmp_path):
    async with mesa(tmp_path) as m, m.cliente() as c:
        for rodadas in (0, 4, "x"):
            resposta = await c.post(f"{API}/salas", json={"apelido": "Ana", "rodadas": rodadas})
            assert resposta.status_code == 422
        resposta = await c.post(f"{API}/salas", json={"apelido": "A", "rodadas": 1})
        assert resposta.status_code == 422 and resposta.json() == {
            "erro": "nickname must have 2 to 16 characters"
        }


@assincrono
async def test_criar_sala_limitado_por_rede(tmp_path):
    async with mesa(tmp_path, limite=3) as m:
        corpo = {"apelido": "Ana", "rodadas": 1}
        async with m.cliente("10.0.0.1") as c:
            codigos = [(await c.post(f"{API}/salas", json=corpo)).status_code for _ in range(4)]
        assert codigos == [201, 201, 201, 429]
        async with m.cliente("10.0.0.2") as c:
            assert (await c.post(f"{API}/salas", json=corpo)).status_code == 201
        m.relogio.andar(3600)
        async with m.cliente("10.0.0.1") as c:
            assert (await c.post(f"{API}/salas", json=corpo)).status_code == 201


@assincrono
async def test_sala_inexistente_404(tmp_path):
    async with mesa(tmp_path) as m, m.cliente() as c:
        _, tokens = await m.sala_com(2)
        respostas = [
            await c.post(f"{API}/salas/zzzzzz/entrar", json={"apelido": "Bia"}),
            await c.post(f"{API}/salas/zzzzzz/acao", json={"token": tokens[1], "tipo": "sair"}),
            await c.get(f"{API}/salas/zzzzzz/eventos", params={"token": tokens[1]}),
        ]
        assert [r.status_code for r in respostas] == [404, 404, 404]
        assert all(r.json() == {"erro": "room not found"} for r in respostas)
        assert not m.prancheta.viva("zzzzzz")


@assincrono
async def test_acao_fora_da_vez_409(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        resposta = await m.agir(sala, tokens[2], "comecar")
        assert resposta.status_code == 409 and resposta.json() == {"erro": "only the host starts"}
        assert (await m.agir(sala, tokens[1], "comecar")).status_code == 204
        assert (await m.agir(sala, tokens[2], "escolher", indice=0)).status_code == 409
        assert (await m.agir(sala, tokens[1], "escolher", indice=5)).status_code == 422
        assert (await m.agir(sala, tokens[1], "voar")).status_code == 422  # unknown action


@assincrono
async def test_token_de_outra_sala_403(tmp_path):
    async with mesa(tmp_path) as m, m.cliente() as c:
        sala_a, tokens_a = await m.sala_com(2)
        sala_b, _ = await m.sala_com(2)
        resposta = await m.agir(sala_b, tokens_a[1], "comecar")
        assert resposta.status_code == 403 and resposta.json() == {"erro": "invalid token"}
        eventos = await c.get(f"{API}/salas/{sala_b}/eventos", params={"token": tokens_a[1]})
        assert eventos.status_code == 403
        sem_token = await c.post(f"{API}/salas/{sala_a}/acao", json={"tipo": "comecar"})
        assert sem_token.status_code == 422


@assincrono
async def test_expulso_nao_age(tmp_path):
    async with mesa(tmp_path) as m, m.cliente() as c:
        sala, tokens = await m.sala_com(3)
        assert (await m.agir(sala, tokens[1], "tirar", alvo=3)).status_code == 204
        assert (await m.agir(sala, tokens[3], "sair")).status_code == 403
        assert (await m.agir(sala, tokens[3], "cartao", alvo=2)).status_code == 403
        eventos = await c.get(f"{API}/salas/{sala}/eventos", params={"token": tokens[3]})
        assert eventos.status_code == 403


@assincrono
async def test_limites_de_chute_e_traco_429(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(3)
        await m.em_desenho(sala, tokens)
        assert (await m.agir(sala, tokens[2], "chute", texto="apito")).status_code == 204
        assert (await m.agir(sala, tokens[2], "chute", texto="trave")).status_code == 429
        m.relogio.andar(0.5)
        assert (await m.agir(sala, tokens[2], "chute", texto="trave")).status_code == 204

        pedaco = traco(1, [[10, 10]], fim=False)
        codigos = [
            (await m.agir(sala, tokens[1], "traco", **pedaco)).status_code for _ in range(41)
        ]
        assert codigos == [204] * 40 + [429]
        m.relogio.andar(1)
        assert (await m.agir(sala, tokens[1], "traco", **pedaco)).status_code == 204
        foto = await m.foto(sala, tokens[3])
        assert len(foto["tracos"][0]["pts"]) == 41  # the refused piece left nothing


# --- eventos ao vivo ---


@assincrono
async def test_sse_comeca_com_estado(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        ouvinte = await m.ouvir(sala, tokens[2])
        assert ouvinte.status == 200
        assert ouvinte.headers["content-type"].startswith("text/event-stream")
        assert ouvinte.headers["cache-control"] == "no-cache"
        assert ouvinte.headers["x-accel-buffering"] == "no"
        tipo, dados = await ouvinte.proximo()
        assert tipo == "estado" and dados["voce"] == 2 and dados["fase"] == "espera"
        assert dados["seq"] >= 1

        await m.agir(sala, tokens[1], "comecar")
        tipo, dados = await ouvinte.proximo()
        assert tipo == "estado" and dados["fase"] == "escolha" and dados["opcoes"] is None


@assincrono
async def test_palavra_nunca_vaza(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(3)
        quem_chuta = [await m.ouvir(sala, tokens[2]), await m.ouvir(sala, tokens[3])]
        await m.em_desenho(sala, tokens)  # Bicicleta, also "bicicleta de costas"
        m.relogio.andar(1)
        for jogador, chute in [(2, "apito"), (3, "bicic"), (2, "bicicleta")]:
            m.relogio.andar(0.5)
            assert (await m.agir(sala, tokens[jogador], "chute", texto=chute)).status_code == 204
        m.relogio.andar(1)
        m.prancheta.passo()
        assert (
            await m.agir(sala, tokens[3], "chute", texto="bicicleta de costas")
        ).status_code == (204)

        for ouvinte in quem_chuta:
            lidos = await ouvinte.ate(lambda t, d: t == "estado" and d["fase"] == "intervalo")
            *antes, (_, intervalo) = lidos
            for _, dados in antes:
                assert "bicicleta" not in normalizar(json.dumps(dados, ensure_ascii=False))
            assert intervalo["palavra"] == "Bicicleta"
        assert ("trave", {"texto": "bicic", "seq": _seq(lidos, "trave")}) in lidos


def _seq(lidos, tipo) -> int:
    return next(d["seq"] for t, d in lidos if t == tipo)


@assincrono
async def test_traco_chega_aos_outros_e_nao_volta(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        desenha, chuta = await m.ouvir(sala, tokens[1]), await m.ouvir(sala, tokens[2])
        await m.em_desenho(sala, tokens)
        pedaco = traco(7, [[1, 2], [3, 4]], fim=False)
        assert (await m.agir(sala, tokens[1], "traco", **pedaco)).status_code == 204
        *_, (tipo, dados) = await chuta.ate(lambda t, d: t == "traco")
        assert {k: v for k, v in dados.items() if k != "seq"} == pedaco

        assert (await m.agir(sala, tokens[2], "chute", texto="apito")).status_code == 204
        lidos = await desenha.ate(lambda t, d: t == "chute")
        assert "traco" not in [t for t, _ in lidos]
        assert lidos[-1][1]["texto"] == "apito"


@assincrono
async def test_reconectar_recebe_tracos_do_desenho_atual(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(3)
        await m.em_desenho(sala, tokens)
        await m.agir(sala, tokens[1], "traco", **traco(1, [[1, 1], [2, 2]], fim=False))
        await m.agir(sala, tokens[1], "traco", **traco(1, [[3, 3]], fim=True))
        await m.agir(sala, tokens[1], "traco", **traco(2, [[9, 9]]))
        await m.agir(sala, tokens[1], "desfazer")
        foto = await m.foto(sala, tokens[3])
        assert foto["tracos"] == [traco(1, [[1, 1], [2, 2], [3, 3]])]


@assincrono
async def test_duas_abas_mesmo_jogador(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        await m.ouvir(sala, tokens[1])
        aba1, aba2 = await m.ouvir(sala, tokens[2]), await m.ouvir(sala, tokens[2])
        await aba1.fechar()
        m.relogio.andar(31)
        m.prancheta.passo()
        assert presenca(await m.foto(sala, tokens[1])) == {1: True, 2: True}

        await aba2.fechar()
        m.relogio.andar(29)
        m.prancheta.passo()
        assert presenca(await m.foto(sala, tokens[1])) == {1: True, 2: True}
        m.relogio.andar(1)
        m.prancheta.passo()
        assert presenca(await m.foto(sala, tokens[1])) == {1: True, 2: False}


@assincrono
async def test_fila_cheia_derruba_a_conexao(tmp_path, monkeypatch):
    monkeypatch.setattr(hub, "FILA_MAX", 3)
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(3)
        await m.ouvir(sala, tokens[1])
        ouve = await m.ouvir(sala, tokens[3])
        await m.em_desenho(sala, tokens)
        sumiu = await m.ouvir(sala, tokens[2], travar=True)
        for id_ in range(1, 6):  # more than FILA_MAX pieces the vanished tab never takes
            resposta = await m.agir(sala, tokens[1], "traco", **traco(id_, [[1, 1]]))
            assert resposta.status_code == 204
            await ouve.ate(lambda t, d, id_=id_: t == "traco" and d["id"] == id_)  # others do

        m.relogio.andar(30)
        m.prancheta.passo()
        assert presenca(await m.foto(sala, tokens[1])) == {1: True, 2: False, 3: True}

        nova = await m.ouvir(sala, tokens[2])  # the browser reconnects and gets the photo
        tipo, dados = await nova.proximo()
        assert tipo == "estado" and len(dados["tracos"]) == 5
        await sumiu.fechar()  # the dropped tab closing does not count as a second goodbye
        m.relogio.andar(30)
        m.prancheta.passo()
        assert presenca(await m.foto(sala, tokens[1])) == {1: True, 2: True, 3: True}


@assincrono
async def test_acoes_concorrentes_nao_quebram_seq(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(4)
        ouvinte = await m.ouvir(sala, tokens[2])
        await m.em_desenho(sala, tokens)

        async def passo():
            m.prancheta.passo()

        await asyncio.gather(
            *(m.agir(sala, tokens[1], "traco", **traco(i, [[i, i]])) for i in range(30)),
            *(m.agir(sala, tokens[j], "chute", texto=f"nada {j}") for j in (2, 3, 4)),
            *(passo() for _ in range(10)),
            *(m.agir(sala, tokens[j], "cartao", alvo=1) for j in (3,)),
        )
        m.relogio.andar(1)
        assert (await m.agir(sala, tokens[3], "chute", texto="marcador")).status_code == 204
        lidos = await ouvinte.ate(lambda t, d: t == "chute" and d["texto"] == "marcador")
        seqs = [d["seq"] for _, d in lidos]
        assert seqs == sorted(set(seqs))
        assert sum(t == "traco" for t, _ in lidos) == 30


@assincrono
async def test_expulso_tem_a_conexao_fechada(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(4)
        await m.ouvir(sala, tokens[1])
        expulso, saiu = await m.ouvir(sala, tokens[3]), await m.ouvir(sala, tokens[4])
        await m.em_desenho(sala, tokens)
        assert (await m.agir(sala, tokens[1], "tirar", alvo=3)).status_code == 204
        assert (await m.agir(sala, tokens[4], "sair")).status_code == 204
        for ouvinte, quem in ((expulso, 3), (saiu, 4)):
            lidos = []
            while (evento := await ouvinte.proximo()) is not None:
                lidos.append(evento)
            tipo, ultimo = lidos[-1]  # their last view, without them, and then the stream ends
            assert tipo == "estado" and quem not in [j["id"] for j in ultimo["jogadores"]]
        await m.agir(sala, tokens[1], "traco", **traco(1, [[1, 1]]))  # nothing to deliver there

        aba = await m.ouvir(sala, tokens[2])  # the last tab of who is left
        await aba.fechar()
        await m.ouvintes[0].fechar()
        m.relogio.andar(600)
        m.prancheta.passo()  # no spectator keeps the room alive
        assert not m.prancheta.viva(sala)


# --- pedir para entrar, dica e pular ---


@assincrono
async def test_quem_pede_espera_e_o_anfitriao_aceita(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        anfitriao = await m.ouvir(sala, tokens[1])
        await anfitriao.proximo()
        pedido = await m.pedir(sala, "Novato")
        assert pedido == {"jogador": 3, "token": pedido["token"], "pendente": True}
        espera = await m.ouvir(sala, pedido["token"])
        tipo, dados = await espera.proximo()
        assert tipo == "estado" and dados["fase"] == "pedido" and dados["anfitriao"] == "Ana"
        assert "jogadores" not in dados
        *_, (_, visto) = await anfitriao.ate(lambda t, d: t == "estado" and d["pedidos"])
        assert visto["pedidos"] == [{"id": 3, "apelido": "Novato"}]
        resposta = await m.agir(sala, pedido["token"], "chute", texto="bola")
        assert resposta.status_code == 409 and resposta.json() == {"erro": "waiting for the host"}
        assert (await m.agir(sala, tokens[2], "aceitar", pedido=3)).status_code == 409
        assert (await m.agir(sala, tokens[1], "aceitar", pedido=3)).status_code == 204
        *_, (_, dentro) = await espera.ate(lambda t, d: t == "estado" and d["fase"] == "espera")
        assert [j["apelido"] for j in dentro["jogadores"]] == ["Ana", "Bia", "Novato"]
        assert dentro["jogadores"][2]["presente"]
        assert (await m.agir(sala, pedido["token"], "cartao", alvo=2)).status_code == 204


@assincrono
async def test_recusado_e_avisado_e_o_fluxo_fecha(tmp_path):
    async with mesa(tmp_path) as m, m.cliente() as c:
        sala, tokens = await m.sala_com(2)
        pedido = await m.pedir(sala, "Novato")
        espera = await m.ouvir(sala, pedido["token"])
        await espera.proximo()
        assert (await m.agir(sala, tokens[1], "recusar", pedido=3)).status_code == 204
        lidos = []
        while (evento := await espera.proximo()) is not None:
            lidos.append(evento)
        assert [t for t, _ in lidos] == ["recusado"]
        assert (await m.agir(sala, pedido["token"], "sair")).status_code == 403
        eventos = await c.get(f"{API}/salas/{sala}/eventos", params={"token": pedido["token"]})
        assert eventos.status_code == 403


@assincrono
async def test_dica_e_pular_pela_rota(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(3)
        chuta = await m.ouvir(sala, tokens[2])
        await m.em_desenho(sala, tokens)
        assert (await m.agir(sala, tokens[1], "dica")).status_code == 409  # not yet
        m.relogio.andar(40)
        assert (await m.agir(sala, tokens[1], "dica")).status_code == 204
        *_, (_, dica) = await chuta.ate(lambda t, d: t == "dica")
        assert sum(1 for c in dica["dica"] if c) == 1
        assert (
            await m.agir(sala, tokens[1], "traco", **dict(traco(1, [[1, 1]]), cor=12))
        ).status_code == 204
        assert (
            await m.agir(sala, tokens[1], "traco", **dict(traco(2, [[1, 1]]), cor=13))
        ).status_code == 422
        assert (await m.agir(sala, tokens[2], "pular")).status_code == 409
        assert (await m.agir(sala, tokens[1], "pular")).status_code == 204
        lidos = await chuta.ate(lambda t, d: t == "estado" and d["fase"] == "intervalo")
        assert ("pulou", {"jogador": 1, "seq": _seq(lidos, "pulou")}) in lidos
        assert lidos[-1][1]["palavra"] == "Bicicleta"


# --- laço, súmula e limpeza ---


def _linhas(m: Mesa) -> list[tuple]:
    with closing(sqlite3.connect(m.prancheta.db_path)) as db:
        return db.execute(
            "SELECT id, criada_em, encerrada_em, dados FROM prancheta_sumulas"
        ).fetchall()


def _ate_o_fim(m: Mesa, segundos: float) -> None:
    """Steps the loop every half second for `segundos`, as `rodar()` would."""
    for _ in range(int(segundos * 2)):
        m.relogio.andar(0.5)
        m.prancheta.passo()


@assincrono
async def test_fim_grava_sumula(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        ouvinte = await m.ouvir(sala, tokens[2])
        await m.ouvir(sala, tokens[1])
        await m.em_desenho(sala, tokens)  # Ana draws Bicicleta
        m.relogio.andar(1)
        await m.agir(sala, tokens[2], "chute", texto="Bicicleta")  # Bia scores, intervalo
        _ate_o_fim(m, 6 + 15 + 80 + 6)  # Bia's turn: no choice, no guess, then the end

        *_, (tipo, fim) = await ouvinte.ate(lambda t, d: t == "fim")
        assert await ouvinte.proximo() is None  # the stream closes after the end
        assert m.prancheta.sumula(sala) == fim["sumula"]
        assert fim["sumula"]["jogadores"] == [
            {"apelido": "Bia", "pontos": 5, "gols": 1, "assist": 0},
            {"apelido": "Ana", "pontos": 2, "gols": 0, "assist": 1},
        ]
        assert [lance["desenhista"] for lance in fim["sumula"]["lances"]] == ["Ana", "Bia"]
        [(id_, criada_em, encerrada_em, _)] = _linhas(m)
        assert id_ == sala and criada_em == T0.isoformat()
        assert encerrada_em == m.relogio().isoformat()


@assincrono
async def test_sumula_gravada_uma_vez(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        await m.em_desenho(sala, tokens)
        assert (await m.agir(sala, tokens[2], "sair")).status_code == 204  # alone: the end
        primeira = _linhas(m)
        assert len(primeira) == 1
        assert (await m.agir(sala, tokens[1], "sair")).status_code == 404  # out of memory
        _ate_o_fim(m, 3)
        m.relogio.andar(3 * 3600)
        m.prancheta.passo()
        m.prancheta._gravar(sala, T0, m.relogio(), {"outra": "versao"})  # a second write
        assert _linhas(m) == primeira


@assincrono
async def test_sala_abandonada_sai_da_memoria(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        sozinha, _ = await m.sala_com(2)
        aba = await m.ouvir(
            sozinha, tokens[1].replace(tokens[1], (await m.entrar(sozinha, "Gil"))["token"])
        )
        aba_da_sala = await m.ouvir(sala, tokens[1])
        m.relogio.andar(300)
        await aba_da_sala.fechar()  # the 10 minutes count from the last tab closing
        m.relogio.andar(599)
        m.prancheta.passo()
        assert m.prancheta.viva(sala)
        m.relogio.andar(1)
        m.prancheta.passo()
        assert not m.prancheta.viva(sala) and m.prancheta.sumula(sala) is None  # never played
        async with m.cliente() as c:
            resposta = await c.post(f"{API}/salas/{sala}/entrar", json={"apelido": "Hugo"})
        assert resposta.status_code == 404
        assert m.prancheta.viva(sozinha)  # a tab still open keeps the room
        await aba.fechar()


@assincrono
async def test_sala_de_tres_horas_encerra(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        esperando, outros = await m.sala_com(2)
        ouvintes = [await m.ouvir(sala, t) for t in tokens.values()]
        parada = await m.ouvir(esperando, outros[1])
        await m.em_desenho(sala, tokens)
        m.relogio.andar(3 * 3600 - 1)
        m.prancheta.passo()  # a jump: the deadlines would end the game by themselves
        assert m.prancheta.viva(sala)
        m.relogio.andar(1)
        m.prancheta.passo()
        assert not m.prancheta.viva(sala) and not m.prancheta.viva(esperando)
        sumula = m.prancheta.sumula(sala)
        assert sumula is not None and m.prancheta.sumula(esperando) is None
        for ouvinte in ouvintes:
            *_, (_, fim) = await ouvinte.ate(lambda t, d: t == "fim")
            assert fim["sumula"] == sumula
            assert await ouvinte.proximo() is None
        tipos = []  # the waiting room just closes: no game, no fim
        while (evento := await parada.proximo()) is not None:
            tipos.append(evento[0])
        assert set(tipos) == {"estado"}


@assincrono
async def test_viva_e_sumula(tmp_path):
    async with mesa(tmp_path) as m:
        assert not m.prancheta.viva("abcdef") and m.prancheta.sumula("abcdef") is None
        sala, tokens = await m.sala_com(3)
        assert m.prancheta.viva(sala) and m.prancheta.sumula(sala) is None
        await m.em_desenho(sala, tokens)
        await m.agir(sala, tokens[1], "tirar", alvo=3)
        await m.agir(sala, tokens[2], "sair")
        assert not m.prancheta.viva(sala)
        sumula = m.prancheta.sumula(sala)
        assert sumula["id"] == sala
        assert [j["apelido"] for j in sumula["jogadores"]] == ["Ana", "Bia"]  # 3 was sent off


@assincrono
async def test_id_de_sala_nao_repete_sumula(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        await m.em_desenho(sala, tokens)
        await m.agir(sala, tokens[2], "sair")
    async with mesa(tmp_path) as m:  # same SQLite, same draws: the first id is taken
        nova = await m.criar()
        assert nova["id"] != sala and m.prancheta.sumula(sala) is not None


def test_rodar_avanca_as_salas_a_cada_meio_segundo(tmp_path):
    async def jogo():
        m = Mesa(tmp_path)
        dormidas = []

        async def sleep(segundos):
            dormidas.append(segundos)
            m.relogio.andar(segundos)
            if len(dormidas) == 40:  # 20 s: the choice ran out and a word was drawn
                raise asyncio.CancelledError

        m.prancheta._sleep = sleep
        sala, tokens = await m.sala_com(2)
        await m.ouvir(sala, tokens[1])
        await m.ouvir(sala, tokens[2])
        await m.agir(sala, tokens[1], "comecar")
        with pytest.raises(asyncio.CancelledError):
            await m.prancheta.rodar()
        assert set(dormidas) == {0.5}
        foto = await m.foto(sala, tokens[1])
        await m.fechar()
        return foto

    foto = asyncio.run(jogo())
    assert foto["fase"] == "desenho" and foto["palavra"]


@assincrono
async def test_erro_numa_sala_nao_para_as_outras(tmp_path, caplog):
    async with mesa(tmp_path) as m:
        quebrada, tokens_q = await m.sala_com(2)
        boa, tokens_b = await m.sala_com(2)
        ouvinte = await m.ouvir(quebrada, tokens_q[2])
        await m.ouvir(boa, tokens_b[1])
        await m.ouvir(boa, tokens_b[2])
        await m.agir(boa, tokens_b[1], "comecar")

        def quebra(agora):
            raise RuntimeError("bug")

        m.prancheta._salas[quebrada].sala.avancar = quebra
        m.relogio.andar(15)
        m.prancheta.passo()  # must not raise

        assert (await m.foto(boa, tokens_b[1]))["fase"] == "desenho"  # the choice ran out
        assert not m.prancheta.viva(quebrada)
        while await ouvinte.proximo() is not None:  # its streams end
            pass
        assert "Prancheta room failed" in caplog.text


@assincrono
async def test_falha_ao_gravar_sumula_ainda_fecha_a_sala(tmp_path, monkeypatch, caplog):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.sala_com(2)
        ouvinte = await m.ouvir(sala, tokens[1])
        await m.em_desenho(sala, tokens)
        esperas = []

        def travado(*args, timeout=5.0, **kwargs):
            esperas.append(timeout)
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(hub.sqlite3, "connect", travado)
        assert (await m.agir(sala, tokens[2], "sair")).status_code == 204  # the end
        assert esperas == [1.0]  # a short wait: the event loop is not stuck behind the lock
        assert not m.prancheta.viva(sala)
        *_, (tipo, _) = await ouvinte.ate(lambda t, d: t == "fim")
        assert await ouvinte.proximo() is None  # its streams end all the same
        assert f"Prancheta room {sala}: saving the súmula failed" in caplog.text


# --- no app ---


def test_app_liga_a_prancheta(store, mailer, clock):
    with make_client(store, mailer, clock, PRANCHETA_LACO=True) as cliente:  # loop on and off
        resposta = cliente.post(f"{API}/salas", json={"apelido": "Ana", "rodadas": 1})
        assert resposta.status_code == 201
        sala = resposta.json()["id"]
        entrou = cliente.post(f"{API}/salas/{sala}/entrar", json={"apelido": "Bia"})
        assert entrou.json()["jogador"] == 2


def test_token_some_do_access_log(tmp_path):
    Mesa(tmp_path)  # creating the hub puts the filter on uvicorn's access log
    acesso = logging.getLogger("uvicorn.access")
    caminho = f"{API}/salas/abc234/eventos?token=Segredo-_123&x=1"
    registro = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "GET", caminho, "1.1", 200),
        None,
    )
    assert all(filtro.filter(registro) for filtro in acesso.filters)
    mensagem = registro.getMessage()
    assert "Segredo" not in mensagem
    assert f"{API}/salas/abc234/eventos?token=***&x=1" in mensagem
    Mesa(tmp_path)
    assert len([f for f in acesso.filters if isinstance(f, hub.SemToken)]) == 1  # added once
