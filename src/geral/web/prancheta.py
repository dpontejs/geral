"""The Prancheta's server: rooms in memory, the API routes and the live events (SSE).

One process holds every open room (`Sala`, the pure rules) in a dict. The routes are `async def`
and every touch of a room is synchronous (no `await` between reading a room and delivering what it
returned), so actions, connections and the loop never interleave on the same room: in asyncio that
is the lock. Each events connection has its own queue; the hub only routes `para`/`exceto`, the
privacy is decided inside the `Sala`.
"""

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from geral.games.prancheta import palavras
from geral.games.prancheta.sala import ErroSala, Evento, Sala
from geral.games.prancheta.tipos import Banco
from geral.web.team_requests import network

if TYPE_CHECKING:
    from geral.web.app import RateLimiter

logger = logging.getLogger(__name__)

ALFABETO = "abcdefghijklmnopqrstuvwxyz234567"  # base32, lowercase: the room's short link
TAMANHO_ID = 6
FILA_MAX = 500  # events waiting for one connection; past that the client is gone: drop it
PING = 15.0  # seconds between keep-alive comments on an idle events stream
INTERVALO = 0.5  # seconds between two steps of the loop


# --- corpos ---


class NovaSala(BaseModel):
    apelido: str = Field(max_length=64)
    rodadas: int = Field(ge=1, le=3)


class Entrada(BaseModel):
    apelido: str = Field(max_length=64)


class _ComToken(BaseModel):
    token: str = Field(max_length=64)


class Comecar(_ComToken):
    tipo: Literal["comecar"]


class Escolher(_ComToken):
    tipo: Literal["escolher"]
    indice: int


class Traco(_ComToken):
    tipo: Literal["traco"]
    id: int
    cor: int
    esp: int
    pts: list[list[int]] = Field(max_length=64)
    fim: bool


class Desfazer(_ComToken):
    tipo: Literal["desfazer"]


class Limpar(_ComToken):
    tipo: Literal["limpar"]


class Chute(_ComToken):
    tipo: Literal["chute"]
    texto: str = Field(max_length=200)  # the room allows 40 after trimming


class Cartao(_ComToken):
    tipo: Literal["cartao"]
    alvo: int


class Tirar(_ComToken):
    tipo: Literal["tirar"]
    alvo: int


class Sair(_ComToken):
    tipo: Literal["sair"]


Acao = Annotated[
    Comecar | Escolher | Traco | Desfazer | Limpar | Chute | Cartao | Tirar | Sair,
    Field(discriminator="tipo"),
]


# --- hub ---


@dataclass(eq=False)
class _Conexao:
    jogador: int
    fila: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=FILA_MAX))
    fechada: bool = False


@dataclass(eq=False)
class _SalaViva:
    sala: Sala
    conexoes: list[_Conexao] = field(default_factory=list)


class _Fluxo(StreamingResponse):
    """An events stream that says goodbye however it ends: closed, dropped, cancelled or broken.

    Starlette leaves a stream's generator unclosed when the client goes away while a chunk is
    being sent, so its `finally` would only run whenever the garbage collector gets to it.
    """

    def __init__(self, conteudo, ao_fechar: Callable[[], None], **kwargs) -> None:
        super().__init__(conteudo, **kwargs)
        self._ao_fechar = ao_fechar

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._ao_fechar()


def _erro(status: int, motivo: str) -> JSONResponse:
    return JSONResponse({"erro": motivo}, status_code=status)


def _sse(tipo: str, dados: dict) -> str:
    return f"event: {tipo}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


class Prancheta:
    def __init__(
        self,
        db_path: str | Path,
        now: Callable[[], datetime],
        limite_salas: "RateLimiter",
        sleep: Callable[[float], Awaitable[None]],
        banco: Banco,
        rng: random.Random,
    ) -> None:
        self.db_path = Path(db_path)
        self._now = now
        self._limite = limite_salas
        self._sleep = sleep
        self._banco = banco
        self._rng = rng
        self._salas: dict[str, _SalaViva] = {}
        self.router = APIRouter(prefix="/api/jogos/prancheta")
        self._rotas()

    # --- leitura ---

    def viva(self, sala_id: str) -> bool:
        viva = self._salas.get(sala_id)
        return viva is not None and not viva.sala.encerrada

    # --- laço ---

    async def rodar(self) -> None:
        """The lifespan's task: one step every half second, until cancelled."""
        while True:
            try:
                self.passo()
            except Exception:  # one bad step must not stop every room
                logger.exception("Prancheta loop step failed")
            await self._sleep(INTERVALO)

    def passo(self) -> None:
        """Moves every room's clock (deadlines, hints, absences) and delivers what changed."""
        agora = self._now()
        for viva in list(self._salas.values()):
            self._entregar(viva, viva.sala.avancar(agora))

    # --- entrega ---

    def _entregar(self, viva: _SalaViva, eventos: list[Evento]) -> None:
        caidas = []
        for evento in eventos:
            for conexao in viva.conexoes:
                if conexao in caidas:
                    continue
                if evento.para is not None and conexao.jogador != evento.para:
                    continue
                if evento.exceto is not None and conexao.jogador == evento.exceto:
                    continue
                try:
                    conexao.fila.put_nowait((evento.tipo, evento.dados))
                except asyncio.QueueFull:  # a client that vanished without closing
                    caidas.append(conexao)
        for conexao in caidas:
            logger.info("Prancheta %s: dropping a stalled events connection", viva.sala.id)
            self._desligar(viva, conexao)

    def _desligar(self, viva: _SalaViva, conexao: _Conexao) -> None:
        """Takes a connection out of the room once (closed, or dropped for a full queue)."""
        if conexao.fechada:
            return
        conexao.fechada = True
        viva.conexoes.remove(conexao)
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
        while not conexao.fechada:
            try:
                item = await asyncio.wait_for(conexao.fila.get(), PING)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None or conexao.fechada:
                return
            yield _sse(*item)

    # --- rotas ---

    def _novo_id(self) -> str:
        while True:
            sala_id = "".join(self._rng.choice(ALFABETO) for _ in range(TAMANHO_ID))
            if sala_id not in self._salas:
                return sala_id

    def _rotas(self) -> None:
        router = self.router

        @router.post("/salas", status_code=201)
        async def criar_sala(request: Request, corpo: NovaSala):
            ip = request.client.host if request.client else ""
            if not self._limite.allow(network(ip), self._now()):
                return _erro(429, "too many rooms, try later")
            agora = self._now()
            sala = Sala(self._novo_id(), corpo.rodadas, self._banco, self._rng, agora)
            try:
                jogador, token, _ = sala.entrar(corpo.apelido, agora)
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            self._salas[sala.id] = _SalaViva(sala)
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
            return _Fluxo(
                self._fluxo(conexao),
                ao_fechar=lambda: self._desligar(viva, conexao),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )


def criar_prancheta(
    db_path: str | Path,
    now: Callable[[], datetime],
    limite_salas: "RateLimiter",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    banco: Banco | None = None,
    rng: random.Random | None = None,
) -> Prancheta:
    """The hub with its router; `rodar()` is the loop the app's lifespan runs."""
    return Prancheta(
        db_path,
        now,
        limite_salas,
        sleep,
        banco or palavras.carregar(),
        rng or random.SystemRandom(),
    )
