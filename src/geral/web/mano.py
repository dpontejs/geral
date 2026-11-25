"""The Mano a Mano server: rooms in memory, the API routes and the live events (SSE).

The same design as the Prancheta's hub (`geral.web.prancheta`): one process holds every open
room (`Sala`, the pure rules) in a dict; the routes are `async def` and every touch of a room is
synchronous, so actions, connections and the loop never interleave on the same room. Each events
connection has its own queue; the hub only routes `para`, the privacy is decided in the `Sala`.
The keeper's exit (`saida`) is stamped with the hub's clock when it arrives.
"""

import asyncio
import json
import logging
import random
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from geral.games.mano.sala import ErroSala, Evento, Sala
from geral.games.mano.tipos import Modo, Nivel
from geral.web.sse import SEM_TOKEN, Fluxo, sse
from geral.web.team_requests import network

if TYPE_CHECKING:
    from geral.web.app import RateLimiter

logger = logging.getLogger(__name__)

ALFABETO = "abcdefghijklmnopqrstuvwxyz234567"  # base32, lowercase: the room's short link
TAMANHO_ID = 6
FILA_MAX = 500  # events waiting for one connection; past that the client is gone: drop it
PING = 15.0  # seconds between keep-alive comments on an idle events stream
INTERVALO = 0.25  # seconds between two steps of the loop: the exit window is 600 ms
ABANDONO = timedelta(minutes=10)  # a room with no events connection for this long is closed
DURACAO_MAX = timedelta(hours=3)  # and any room this old
ESPERA_DB = 1.0  # seconds to wait for a locked SQLite: these calls run on the event loop
SCHEMA = """
CREATE TABLE IF NOT EXISTS mano_sumulas (
    id TEXT PRIMARY KEY,
    sala TEXT NOT NULL,
    criada_em TEXT NOT NULL,
    encerrada_em TEXT NOT NULL,
    dados TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS mano_sumulas_sala ON mano_sumulas (sala);
"""


# --- corpos ---


class NovaSala(BaseModel):
    apelido: str = Field(max_length=64)
    modo: Modo
    bot: Nivel | None = None


class Entrada(BaseModel):
    apelido: str = Field(max_length=64)


class _ComToken(BaseModel):
    token: str = Field(max_length=64)


class AcaoBarreira(_ComToken):
    tipo: Literal["barreira"]
    n: int
    x: int


class AcaoChute(_ComToken):
    tipo: Literal["chute"]
    alvo: list[int] = Field(min_length=2, max_length=2)
    barra: int
    trajetoria: str | None = Field(default=None, max_length=16)
    curva: float = 0


class AcaoDefesa(_ComToken):
    tipo: Literal["defesa"]
    lado: str = Field(max_length=16)


class AcaoSaida(_ComToken):
    tipo: Literal["saida"]  # anything else the client sends (its own clock) is ignored


class AcaoRevanche(_ComToken):
    tipo: Literal["revanche"]


class AcaoSair(_ComToken):
    tipo: Literal["sair"]


Acao = Annotated[
    AcaoBarreira | AcaoChute | AcaoDefesa | AcaoSaida | AcaoRevanche | AcaoSair,
    Field(discriminator="tipo"),
]


# --- hub ---


@dataclass(eq=False)
class _Conexao:
    jogador: int
    fila: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=FILA_MAX))
    fechada: bool = False  # no longer counts as a connection of the room
    derrubada: bool = False  # its client stopped reading: send it nothing more


@dataclass(eq=False)
class _SalaViva:
    sala: Sala
    vazia_desde: datetime  # since when nobody is connected (counts only while that is so)
    conexoes: list[_Conexao] = field(default_factory=list)


def _erro(status: int, motivo: str) -> JSONResponse:
    return JSONResponse({"erro": motivo}, status_code=status)


class Mano:
    def __init__(
        self,
        db_path: str | Path,
        now: Callable[[], datetime],
        limite_salas: "RateLimiter",
        sleep: Callable[[float], Awaitable[None]],
        rng: random.Random,
    ) -> None:
        self.db_path = Path(db_path)
        self._now = now
        self._limite = limite_salas
        self._sleep = sleep
        self._rng = rng
        self._salas: dict[str, _SalaViva] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path, timeout=ESPERA_DB)) as db, db:
            db.executescript(SCHEMA)
        logging.getLogger("uvicorn.access").addFilter(SEM_TOKEN)  # the same one: added once
        self.router = APIRouter(prefix="/api/jogos/mano")
        self._rotas()

    # --- leitura ---

    def viva(self, sala_id: str) -> bool:
        viva = self._salas.get(sala_id)
        return viva is not None and not viva.sala.encerrada

    def cheia(self, sala_id: str) -> bool:
        """A live room with no seat left (two players, or one and the bot)."""
        viva = self._salas.get(sala_id)
        return viva is not None and viva.sala.cheia()

    def sumula(self, id_: str) -> dict | None:
        """A match's súmula by its own id, or a room's last one by the room's id; else None."""
        with closing(sqlite3.connect(self.db_path, timeout=ESPERA_DB)) as db:
            linha = db.execute(
                "SELECT dados FROM mano_sumulas WHERE id = ? OR sala = ?"
                " ORDER BY encerrada_em DESC, rowid DESC LIMIT 1",
                (id_, id_),
            ).fetchone()
        return json.loads(linha[0]) if linha else None

    def _gravar(self, sala: Sala, encerrada_em: datetime, dados: dict) -> None:
        """Keeps a súmula; the first copy stays (the end is written once, whatever calls it)."""
        with closing(sqlite3.connect(self.db_path, timeout=ESPERA_DB)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO mano_sumulas (id, sala, criada_em, encerrada_em, dados)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    dados["id"],
                    sala.id,
                    sala.partida_desde.isoformat(),
                    encerrada_em.isoformat(),
                    json.dumps(dados, ensure_ascii=False),
                ),
            )

    # --- laço ---

    async def rodar(self) -> None:
        """The lifespan's task: one step every quarter of a second, until cancelled."""
        while True:
            self.passo()
            await self._sleep(INTERVALO)

    def passo(self) -> None:
        """Moves every room's clock (deadlines, the kick, absences) and delivers what changed.

        A room nobody has been connected to for 10 minutes, or 3 hours old, is closed (a match
        in progress keeps its súmula) and leaves the memory. A room whose step fails is logged
        and leaves the memory too; the others go on.
        """
        agora = self._now()
        for viva in list(self._salas.values()):
            try:
                abandonada = not viva.conexoes and agora - viva.vazia_desde >= ABANDONO
                if abandonada or agora - viva.sala.criada_em >= DURACAO_MAX:
                    self._entregar(viva, viva.sala.encerrar(agora))
                    self._retirar(viva)
                else:
                    self._entregar(viva, viva.sala.avancar(agora))
            except Exception:
                logger.exception("Mano room failed in the loop: %s", viva.sala.id)
                try:
                    self._retirar(viva)  # out of memory first, then its streams end
                except Exception:
                    logger.exception("Mano room %s: closing its streams failed", viva.sala.id)

    def _retirar(self, viva: _SalaViva) -> None:
        """Out of memory; its events streams end after what is already queued."""
        if self._salas.pop(viva.sala.id, None) is None:
            return  # already out
        for conexao in list(viva.conexoes):
            self._encerrar_fluxo(viva, conexao)

    def _encerrar_fluxo(self, viva: _SalaViva, conexao: _Conexao) -> None:
        try:
            conexao.fila.put_nowait(None)
        except asyncio.QueueFull:
            conexao.derrubada = True  # a stalled client: nothing more reaches it anyway
        self._desligar(viva, conexao)

    # --- entrega ---

    def _entregar(self, viva: _SalaViva, eventos: list[Evento]) -> None:
        caidas = []
        for evento in eventos:
            for conexao in viva.conexoes:
                if conexao in caidas:
                    continue
                if evento.para is not None and conexao.jogador != evento.para:
                    continue
                try:
                    conexao.fila.put_nowait((evento.tipo, evento.dados))
                except asyncio.QueueFull:  # a client that vanished without closing
                    conexao.derrubada = True
                    caidas.append(conexao)
        for conexao in caidas:
            logger.info("Mano %s: dropping a stalled events connection", viva.sala.id)
            self._desligar(viva, conexao)
        for conexao in [c for c in viva.conexoes if not viva.sala.esta(c.jogador)]:
            self._encerrar_fluxo(viva, conexao)  # left: the last word was sent
        sala = viva.sala
        for evento in eventos:
            if evento.tipo == "fim":
                try:
                    self._gravar(sala, self._now(), evento.dados["sumula"])
                except Exception:
                    logger.exception("Mano room %s: saving the súmula failed", sala.id)
                    self._retirar(viva)  # nowhere to show it: the room ends here
        if sala.encerrada:
            self._retirar(viva)

    def _desligar(self, viva: _SalaViva, conexao: _Conexao) -> None:
        """Takes a connection out of the room once (closed, or dropped for a full queue)."""
        if conexao.fechada:
            return
        conexao.fechada = True
        viva.conexoes.remove(conexao)
        if not viva.conexoes:
            viva.vazia_desde = self._now()
        self._entregar(viva, viva.sala.desconectou(conexao.jogador, self._now()))

    def _ligar(self, viva: _SalaViva, jogador: int) -> _Conexao:
        """A new events connection: its queue starts with the photo, then what the room sends."""
        conexao = _Conexao(jogador)
        agora = self._now()
        eventos = viva.sala.conectou(jogador, agora)
        conexao.fila.put_nowait(("estado", viva.sala.foto(jogador, agora)))
        self._entregar(viva, eventos)
        viva.conexoes.append(conexao)
        return conexao

    async def _fluxo(self, conexao: _Conexao) -> AsyncIterator[str]:
        while not conexao.derrubada:
            try:
                item = await asyncio.wait_for(conexao.fila.get(), PING)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None:
                return
            yield sse(*item)

    # --- rotas ---

    def _novo_id(self) -> str:
        while True:
            sala_id = "".join(self._rng.choice(ALFABETO) for _ in range(TAMANHO_ID))
            if sala_id not in self._salas and self.sumula(sala_id) is None:
                return sala_id

    def _rotas(self) -> None:
        router = self.router

        @router.post("/salas", status_code=201)
        async def criar_sala(request: Request, corpo: NovaSala):
            ip = request.client.host if request.client else ""
            if not self._limite.allow(network(ip), self._now()):
                return _erro(429, "too many rooms, try later")
            agora = self._now()
            sala = Sala(self._novo_id(), corpo.modo, corpo.bot, agora, self._rng)
            try:
                jogador, token, _ = sala.entrar(corpo.apelido, agora)
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            self._salas[sala.id] = _SalaViva(sala, vazia_desde=agora)
            return {"id": sala.id, "jogador": jogador, "token": token}

        @router.post("/salas/{sala_id}/entrar")
        async def entrar(sala_id: str, corpo: Entrada):
            viva = self._salas.get(sala_id)
            if viva is None:
                return _erro(404, "room not found")
            try:
                jogador, token, eventos = viva.sala.entrar(corpo.apelido, self._now())
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            self._entregar(viva, eventos)
            return {"jogador": jogador, "token": token}

        @router.post("/salas/{sala_id}/acao", status_code=204)
        async def agir(sala_id: str, corpo: Annotated[Acao, Body()]):
            viva = self._salas.get(sala_id)
            if viva is None:
                return _erro(404, "room not found")
            try:
                jogador = viva.sala.jogador(corpo.token)
                eventos = viva.sala.agir(jogador, corpo.model_dump(exclude={"token"}), self._now())
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            self._entregar(viva, eventos)
            return Response(status_code=204)

        @router.get("/salas/{sala_id}/eventos")
        async def eventos(sala_id: str, token: str = ""):
            viva = self._salas.get(sala_id)
            if viva is None:
                return _erro(404, "room not found")
            try:
                jogador = viva.sala.jogador(token)
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            conexao = self._ligar(viva, jogador)
            return Fluxo(
                self._fluxo(conexao),
                ao_fechar=lambda: self._desligar(viva, conexao),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )


def criar_mano(
    db_path: str | Path,
    now: Callable[[], datetime],
    limite_salas: "RateLimiter",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> Mano:
    """The hub with its router; `rodar()` is the loop the app's lifespan runs."""
    return Mano(db_path, now, limite_salas, sleep, rng or random.SystemRandom())
