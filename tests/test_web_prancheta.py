"""The Prancheta server: rooms in memory, the API routes, the live events (SSE) and the súmula.

Nothing waits on the real clock: `now` is a fake clock, the loop is driven by `passo()`, and the
events stream is read straight from the ASGI app (httpx's ASGITransport buffers whole bodies).
"""

import asyncio
import functools
import json
import random
import re
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
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

    def cliente(self, ip: str = "10.0.0.1") -> httpx.AsyncClient:
        transporte = httpx.ASGITransport(self.app, client=(ip, 1234))
        return httpx.AsyncClient(transport=transporte, base_url="http://geral.test")

    async def criar(self, apelido: str = "Ana", rodadas: int = 1) -> dict:
        async with self.cliente() as c:
            resposta = await c.post(f"{API}/salas", json={"apelido": apelido, "rodadas": rodadas})
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    async def entrar(self, sala: str, apelido: str) -> dict:
        async with self.cliente() as c:
            resposta = await c.post(f"{API}/salas/{sala}/entrar", json={"apelido": apelido})
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

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
        assert (await m.agir(sala, tokens[1], "pular")).status_code == 422  # unknown action


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


# --- no app ---


def test_app_liga_a_prancheta(store, mailer, clock):
    with make_client(store, mailer, clock, PRANCHETA_LACO=True) as cliente:  # loop on and off
        resposta = cliente.post(f"{API}/salas", json={"apelido": "Ana", "rodadas": 1})
        assert resposta.status_code == 201
        sala = resposta.json()["id"]
        entrou = cliente.post(f"{API}/salas/{sala}/entrar", json={"apelido": "Bia"})
        assert entrou.json()["jogador"] == 2
