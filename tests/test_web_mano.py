"""The Mano a Mano server: rooms in memory, the API routes, the live events (SSE) and the súmula.

Nothing waits on the real clock: `now` is a fake clock and the loop is driven by `passo()`.
"""

import asyncio
import json
import logging
import random
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sse_kit import Ouvinte, Relogio, assincrono
from webkit import make_client

from geral.games.mano import sala as sala_mod
from geral.games.mano.sala import CORRIDA, FOLGA, JANELA, PRAZO_ESCOLHA, RESULTADO
from geral.web.app import RateLimiter
from geral.web.mano import criar_mano
from geral.web.sse import SemToken

API = "/api/jogos/mano"
T0 = datetime(2026, 11, 25, 20, 0, tzinfo=UTC)
GOL = {"alvo": [150, 300], "barra": 500}  # left third, low: only "esquerda" saves it
SAIDA = {"alvo": [380, 300], "barra": 500}  # middle third near the left: "esquerda" + exit
VOO = (CORRIDA + JANELA + FOLGA).total_seconds()


@pytest.fixture(autouse=True)
def ana_comeca(monkeypatch):
    """Ana (player 0) kicks first: the draw itself is tested in test_mano_sala."""
    monkeypatch.setattr(sala_mod, "sortear_primeiro", lambda rng: 0)


class Mesa:
    """The test's table: the app with only the Mano's router, a fake clock and helpers."""

    def __init__(self, tmp_path, limite: int = 20, faltas: bool = True) -> None:
        self.relogio = Relogio(T0)
        self.mano = criar_mano(
            tmp_path / "geral.db",
            self.relogio,
            RateLimiter(limite, timedelta(hours=1)),
            rng=random.Random(7),
            faltas=faltas,
        )
        self.app = FastAPI()
        self.app.include_router(self.mano.router)
        self.ouvintes: list[Ouvinte] = []

    def cliente(self, ip: str = "10.0.0.1") -> httpx.AsyncClient:
        transporte = httpx.ASGITransport(self.app, client=(ip, 1234))
        return httpx.AsyncClient(transport=transporte, base_url="http://geral.test")

    async def post(self, caminho: str, ip: str = "10.0.0.1", **corpo) -> httpx.Response:
        async with self.cliente(ip) as c:
            return await c.post(f"{API}{caminho}", json=corpo)

    async def criar(self, modo: str = "penaltis", bot: str | None = None, ip="10.0.0.1") -> dict:
        resposta = await self.post("/salas", ip, apelido="Ana", time="flamengo", modo=modo, bot=bot)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    async def dupla(
        self, modo: str = "penaltis", presentes: bool = True
    ) -> tuple[str, dict[int, str]]:
        """Ana and Bia in a room; `presentes`: each with an events tab open (else W.O. at 30 s)."""
        criada = await self.criar(modo)
        entrou = await self.post(f"/salas/{criada['id']}/entrar", apelido="Bia", time="abc")
        assert entrou.status_code == 200, entrou.text
        tokens = {0: criada["token"], 1: entrou.json()["token"]}
        if presentes:
            for token in tokens.values():
                await self.ouvir(criada["id"], token)
        return criada["id"], tokens

    async def agir(self, sala: str, token: str, tipo: str, **campos) -> httpx.Response:
        return await self.post(f"/salas/{sala}/acao", token=token, tipo=tipo, **campos)

    async def ouvir(self, sala: str, token: str) -> Ouvinte:
        ouvinte = Ouvinte(self.app, f"{API}/salas/{sala}/eventos", token)
        self.ouvintes.append(ouvinte)
        return await ouvinte.abrir()

    async def foto(self, sala: str, token: str) -> dict:
        ouvinte = await self.ouvir(sala, token)
        tipo, dados = await ouvinte.proximo()
        await ouvinte.fechar()
        assert tipo == "estado"
        return dados

    def andar(self, segundos: float) -> None:
        self.relogio.andar(segundos)
        self.mano.passo()


@asynccontextmanager
async def mesa(tmp_path, **kwargs):
    m = Mesa(tmp_path, **kwargs)
    try:
        yield m
    finally:
        for ouvinte in m.ouvintes:
            ouvinte._fechou.set()
        await asyncio.gather(*(o._tarefa for o in m.ouvintes), return_exceptions=True)


@assincrono
async def test_criar_e_entrar(tmp_path):
    async with mesa(tmp_path) as m:
        criada = await m.criar()
        assert criada["jogador"] == 0 and len(criada["id"]) == 6 and criada["token"]
        entrou = await m.post(f"/salas/{criada['id']}/entrar", apelido="Bia", time="abc")
        assert entrou.status_code == 200
        assert entrou.json()["jogador"] == 1
        assert m.mano.viva(criada["id"])
        foto = await m.foto(criada["id"], criada["token"])
        assert foto["fase"] == "escolha" and foto["papel"] == "batedor"


@assincrono
async def test_cheia_para_a_pagina_avisar_antes_do_apelido(tmp_path):
    async with mesa(tmp_path) as m:
        criada = await m.criar()
        assert not m.mano.cheia(criada["id"])
        await m.post(f"/salas/{criada['id']}/entrar", apelido="Bia", time="abc")
        assert m.mano.cheia(criada["id"])
        assert not m.mano.cheia("zzzzzz")


@assincrono
async def test_corpo_invalido_422(tmp_path):
    async with mesa(tmp_path) as m:
        for corpo in (
            {"apelido": "Ana", "time": "abc", "modo": "escanteio", "bot": None},
            {"apelido": "Ana", "time": "abc", "modo": "penaltis", "bot": "impossivel"},
            {"apelido": "A", "time": "abc", "modo": "penaltis", "bot": None},
        ):
            assert (await m.post("/salas", **corpo)).status_code == 422
        criada = await m.criar()
        resposta = await m.post(f"/salas/{criada['id']}/entrar", apelido="porra", time="abc")
        assert resposta.status_code == 422


@assincrono
async def test_sala_cheia_409(tmp_path):
    async with mesa(tmp_path) as m:
        sala, _ = await m.dupla()
        assert (
            await m.post(f"/salas/{sala}/entrar", apelido="Caio", time="abc")
        ).status_code == 409
        contra_bot = await m.criar(bot="facil")
        resposta = await m.post(f"/salas/{contra_bot['id']}/entrar", apelido="Caio", time="abc")
        assert resposta.status_code == 409


@assincrono
async def test_sala_inexistente_404(tmp_path):
    async with mesa(tmp_path) as m:
        assert (await m.post("/salas/zzzzzz/entrar", apelido="Bia", time="abc")).status_code == 404
        assert (await m.agir("zzzzzz", "x", "sair")).status_code == 404
        async with m.cliente() as c:
            assert (await c.get(f"{API}/salas/zzzzzz/eventos?token=x")).status_code == 404


@assincrono
async def test_token_de_outra_sala_403(tmp_path):
    async with mesa(tmp_path) as m:
        sala, _ = await m.dupla()
        _, outros = await m.dupla()
        assert (await m.agir(sala, outros[0], "chute", **GOL)).status_code == 403
        async with m.cliente() as c:
            resposta = await c.get(f"{API}/salas/{sala}/eventos?token={outros[0]}")
        assert resposta.status_code == 403


@assincrono
async def test_criar_sala_limitado_por_rede(tmp_path):
    async with mesa(tmp_path, limite=2) as m:
        await m.criar(ip="10.0.0.1")
        await m.criar(ip="10.0.0.1")
        resposta = await m.post(
            "/salas", "10.0.0.1", apelido="Ana", time="flamengo", modo="penaltis", bot=None
        )
        assert resposta.status_code == 429
        await m.criar(ip="10.0.0.2")  # another address


@assincrono
async def test_limite_de_acoes_429(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        assert (await m.agir(sala, tokens[0], "chute", **GOL)).status_code == 204
        resposta = await m.agir(sala, tokens[0], "chute", **GOL)
        assert resposta.status_code == 429
        m.relogio.andar(0.3)
        assert (await m.agir(sala, tokens[0], "chute", **GOL)).status_code == 409  # locked


@assincrono
async def test_papel_errado_e_fora_da_fase_409(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        assert (await m.agir(sala, tokens[1], "chute", **GOL)).status_code == 409
        assert (await m.agir(sala, tokens[0], "defesa", lado="fica")).status_code == 409
        m.relogio.andar(0.3)
        assert (await m.agir(sala, tokens[0], "revanche")).status_code == 409


@assincrono
async def test_acao_invalida_422(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla("faltas")
        assert (await m.agir(sala, tokens[1], "barreira", n=9, x=500)).status_code == 422
        assert (await m.agir(sala, tokens[1], "danca")).status_code == 422
        m.relogio.andar(0.3)
        assert (await m.agir(sala, tokens[1], "barreira", n=3, x=500)).status_code == 204
        assert (await m.agir(sala, tokens[0], "chute", **GOL)).status_code == 422  # no trajetoria
        m.relogio.andar(0.3)
        resposta = await m.agir(sala, tokens[0], "chute", trajetoria="rasteira", **GOL)
        assert resposta.status_code == 204


@assincrono
async def test_eventos_sse_privados(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        goleiro = await m.ouvir(sala, tokens[1])
        batedor = await m.ouvir(sala, tokens[0])
        assert (await goleiro.proximo())[0] == "estado"
        await m.agir(sala, tokens[0], "chute", alvo=[123, 456], barra=789)
        await m.agir(sala, tokens[1], "defesa", lado="direita")
        m.andar(CORRIDA.total_seconds())
        m.andar((JANELA + FOLGA).total_seconds())
        lidos = await goleiro.ate(lambda tipo, _: tipo == "cobranca")
        antes = json.dumps([dados for _, dados in lidos[:-1]])
        assert "alvo" not in antes and "789" not in antes
        assert [t for t, _ in lidos].count("cobranca_inicio") == 1
        assert lidos[-1][1]["lance"]["chute"]["alvo"] == [123, 456]
        do_batedor = await batedor.ate(lambda tipo, _: tipo == "cobranca")
        assert "direita" not in json.dumps([d for t, d in do_batedor[:-1]])


@assincrono
async def test_reconectar_recebe_a_foto(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        await m.agir(sala, tokens[0], "chute", alvo=[123, 456], barra=789)
        foto = await m.foto(sala, tokens[1])
        assert foto["travou"] == {"voce": False, "outro": True}
        assert "789" not in json.dumps(foto)
        de_novo = await m.foto(sala, tokens[0])
        assert de_novo["escolha"]["alvo"] == [123, 456]


@assincrono
async def test_saida_carimbada_pelo_relogio_do_servidor(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        goleiro = await m.ouvir(sala, tokens[1])
        await m.agir(sala, tokens[0], "chute", **SAIDA)
        await m.agir(sala, tokens[1], "defesa", lado="esquerda")
        m.andar(CORRIDA.total_seconds() + 0.1)
        resposta = await m.agir(sala, tokens[1], "saida", ms=999_999)  # the client's clock: ignored
        assert resposta.status_code == 204
        m.andar((JANELA + FOLGA).total_seconds())
        lidos = await goleiro.ate(lambda tipo, _: tipo == "cobranca")
        assert lidos[-1][1]["lance"]["defesa"]["saida"] is True
        assert lidos[-1][1]["lance"]["resultado"] == "defesa"


async def _jogar_3_a_0(m: Mesa, sala: str, tokens: dict[int, str]) -> None:
    """Ana scores three, Bia misses three: the end, after the replay."""
    for _ in range(3):
        for batedor, lado in ((0, "direita"), (1, "esquerda")):
            resposta = await m.agir(sala, tokens[batedor], "chute", **GOL)
            assert resposta.status_code == 204, resposta.text
            assert (await m.agir(sala, tokens[1 - batedor], "defesa", lado=lado)).status_code == 204
            m.andar(CORRIDA.total_seconds())
            m.andar((JANELA + FOLGA).total_seconds())
            m.andar(RESULTADO.total_seconds())


def _sumulas(tmp_path) -> list[tuple]:
    with closing(sqlite3.connect(tmp_path / "geral.db")) as db:
        return db.execute("SELECT id, sala, dados FROM mano_sumulas ORDER BY rowid").fetchall()


@assincrono
async def test_fim_grava_sumula(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        ouvinte = await m.ouvir(sala, tokens[0])
        await _jogar_3_a_0(m, sala, tokens)
        lidos = await ouvinte.ate(lambda tipo, _: tipo == "fim")
        sumula = lidos[-1][1]["sumula"]
        assert sumula["placar"] == [3, 0] and sumula["vencedor"] == 0
        assert sumula["wo"] is False
        ((id_, dono, dados),) = _sumulas(tmp_path)
        assert (id_, dono) == (f"{sala}-1", sala)
        assert json.loads(dados) == sumula
        assert m.mano.sumula(f"{sala}-1") == sumula
        assert m.mano.sumula(sala) == sumula  # the room's last one
        assert m.mano.sumula("naoexiste") is None
        assert m.mano.viva(sala)  # waiting for a rematch


@assincrono
async def test_revanche_grava_a_sumula_de_cada_partida(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        await _jogar_3_a_0(m, sala, tokens)
        assert (await m.agir(sala, tokens[0], "revanche")).status_code == 204
        assert (await m.foto(sala, tokens[0]))["fase"] == "fim"
        assert (await m.agir(sala, tokens[1], "revanche")).status_code == 204
        m.relogio.andar(0.3)
        await _jogar_3_a_0(m, sala, tokens)
        assert [linha[0] for linha in _sumulas(tmp_path)] == [f"{sala}-1", f"{sala}-2"]
        assert m.mano.sumula(sala)["partida"] == 2


@assincrono
async def test_quem_sai_perde_por_wo_e_o_fluxo_fecha(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        quem_sai = await m.ouvir(sala, tokens[0])
        fica = await m.ouvir(sala, tokens[1])
        assert (await m.agir(sala, tokens[0], "sair")).status_code == 204
        lidos = await fica.ate(lambda tipo, _: tipo == "fim")
        assert lidos[-1][1]["sumula"]["wo"] is True
        assert lidos[-1][1]["sumula"]["vencedor"] == 1
        while await quem_sai.proximo() is not None:
            pass  # its stream ends
        assert (await m.agir(sala, tokens[0], "chute", **GOL)).status_code == 403
        assert m.mano.sumula(sala)["wo"] is True


@assincrono
async def test_ausente_30s_perde_por_wo(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla(presentes=False)
        await m.ouvir(sala, tokens[0])  # Ana stays; Bia never opens the events
        for _ in range(29):
            m.andar(1)
        assert m.mano.sumula(sala) is None
        m.andar(1)
        sumula = m.mano.sumula(sala)
        assert sumula["wo"] is True and sumula["vencedor"] == 0


@assincrono
async def test_sala_abandonada_e_encerrada(tmp_path):
    async with mesa(tmp_path) as m:
        criada = await m.criar()  # alone, waiting: nobody listening
        m.andar(9 * 60)
        assert m.mano.viva(criada["id"])
        m.andar(60)
        assert not m.mano.viva(criada["id"])
        resposta = await m.post(f"/salas/{criada['id']}/entrar", apelido="Bia", time="abc")
        assert resposta.status_code == 404


@assincrono
async def test_sala_de_tres_horas_encerra(tmp_path):
    async with mesa(tmp_path) as m:
        criada = await m.criar()  # waiting, but listening: not abandoned
        ouvinte = await m.ouvir(criada["id"], criada["token"])
        for _ in range(17):
            m.andar(10 * 60)
        assert m.mano.viva(criada["id"])
        m.andar(10 * 60)
        assert not m.mano.viva(criada["id"])
        while await ouvinte.proximo() is not None:
            pass  # its stream ends


@assincrono
async def test_partida_inteira_contra_o_bot_pela_api(tmp_path):
    async with mesa(tmp_path) as m:
        criada = await m.criar(bot="dificil")
        sala, token = criada["id"], criada["token"]
        ouvinte = await m.ouvir(sala, token)
        for _ in range(60):
            foto = await m.foto(sala, token)
            if foto["fase"] == "fim":
                break
            if foto["papel"] == "batedor":
                assert (await m.agir(sala, token, "chute", **GOL)).status_code == 204
            else:
                assert (await m.agir(sala, token, "defesa", lado="fica")).status_code == 204
            m.andar(CORRIDA.total_seconds())
            m.andar((JANELA + FOLGA).total_seconds())
            m.andar(RESULTADO.total_seconds())
        lidos = await ouvinte.ate(lambda tipo, _: tipo == "fim")
        assert lidos[-1][1]["sumula"]["jogadores"][1]["bot"] is True
        assert m.mano.sumula(sala) is not None
        assert (await m.agir(sala, token, "revanche")).status_code == 204
        assert (await m.foto(sala, token))["partida"] == 2


@assincrono
async def test_prazo_pelo_laco(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        ouvinte = await m.ouvir(sala, tokens[0])
        m.andar(PRAZO_ESCOLHA.total_seconds())
        lidos = await ouvinte.ate(lambda tipo, _: tipo == "cobranca_inicio")
        assert lidos[-1][1]["chute_em"]


def test_rodar_avanca_as_salas_a_cada_quarto_de_segundo(tmp_path):
    pausas = []

    async def dormir(segundos):
        pausas.append(segundos)
        if len(pausas) == 3:
            raise asyncio.CancelledError

    mano = criar_mano(
        tmp_path / "geral.db", lambda: T0, RateLimiter(20, timedelta(hours=1)), sleep=dormir
    )
    passos = []
    mano.passo = lambda: passos.append(1)
    try:
        asyncio.run(mano.rodar())
    except asyncio.CancelledError:
        pass
    assert pausas == [0.25, 0.25, 0.25] and len(passos) == 3


@assincrono
async def test_erro_numa_sala_nao_para_as_outras(tmp_path, caplog):
    async with mesa(tmp_path) as m:
        ruim, _ = await m.dupla()
        boa, _ = await m.dupla()

        def quebra(agora):
            raise RuntimeError("boom")

        m.mano._salas[ruim].sala.avancar = quebra
        with caplog.at_level(logging.ERROR):
            m.andar(1)
        assert not m.mano.viva(ruim)
        assert m.mano.viva(boa)
        assert f"Mano room failed in the loop: {ruim}" in caplog.text


def test_token_some_do_access_log(tmp_path):
    criar_mano(tmp_path / "geral.db", lambda: T0, RateLimiter(20, timedelta(hours=1)))
    filtros = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, SemToken)]
    assert len(filtros) == 1


def test_app_liga_o_mano(store, mailer, clock):
    with make_client(store, mailer, clock, MANO_LACO=True, MANO_FALTAS=True) as cliente:
        resposta = cliente.post(
            f"{API}/salas", json={"apelido": "Ana", "time": "csa", "modo": "faltas", "bot": "medio"}
        )
        assert resposta.status_code == 201
        assert cliente.get("/jogos/mano").status_code == 200  # the page came in slice 4


def test_app_sem_faltas_por_padrao(store, mailer, clock):
    """Free kicks are off until the dev refines them (2026-11-25): MANO_FALTAS turns them on."""
    with make_client(store, mailer, clock) as cliente:
        corpo = {"apelido": "Ana", "time": "abc", "bot": "medio"}
        assert cliente.post(f"{API}/salas", json={**corpo, "modo": "faltas"}).status_code == 422
        assert cliente.post(f"{API}/salas", json={**corpo, "modo": "penaltis"}).status_code == 201
        assert 'data-faltas=""' in cliente.get("/jogos/mano").text


@assincrono
async def test_criar_falta_desligada_da_422(tmp_path):
    async with mesa(tmp_path, faltas=False) as m:
        resposta = await m.post(
            "/salas", "10.0.0.1", apelido="Ana", time="flamengo", modo="faltas", bot=None
        )
        assert resposta.status_code == 422
        assert (
            await m.post(
                "/salas", "10.0.0.1", apelido="Ana", time="flamengo", modo="penaltis", bot=None
            )
        ).status_code == 201


@assincrono
async def test_cavadinha_pela_api(tmp_path):
    async with mesa(tmp_path) as m:
        sala, tokens = await m.dupla()
        resposta = await m.agir(sala, tokens[0], "chute", cavadinha="talvez", **GOL)
        assert resposta.status_code == 422
        m.relogio.andar(0.3)
        goleiro = await m.ouvir(sala, tokens[1])
        assert (await m.agir(sala, tokens[0], "chute", cavadinha=True, **GOL)).status_code == 204
        await m.agir(sala, tokens[1], "defesa", lado="direita")
        m.andar(VOO)
        lidos = await goleiro.ate(lambda tipo, _: tipo == "cobranca")
        assert lidos[-1][1]["lance"]["chute"]["cavadinha"] is True


@assincrono
async def test_time_na_criacao_e_na_entrada(tmp_path):
    async with mesa(tmp_path) as m:
        sem = await m.post("/salas", apelido="Ana", modo="penaltis", bot=None)
        assert sem.status_code == 422
        errado = await m.post("/salas", apelido="Ana", time="botafogo", modo="penaltis", bot=None)
        assert errado.status_code == 422
        criada = await m.criar()
        caminho = f"/salas/{criada['id']}/entrar"
        assert (await m.post(caminho, apelido="Bia")).status_code == 422
        assert (await m.post(caminho, apelido="Bia", time="xxx")).status_code == 422
        assert (await m.post(caminho, apelido="Bia", time="flamengo")).status_code == 200
        ana = await m.ouvir(criada["id"], criada["token"])
        estado = (await ana.ate(lambda tipo, d: tipo == "estado" and len(d["jogadores"]) == 2))[-1][
            1
        ]
        assert [(j["time"], j["uniforme"]) for j in estado["jogadores"]] == [
            ("flamengo", "casa"),
            ("flamengo", "fora"),
        ]
