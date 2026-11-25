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
import re
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
ABANDONO = timedelta(minutes=10)  # a room with no events connection for this long is closed
DURACAO_MAX = timedelta(hours=3)  # and any room this old
ESPERA_DB = 1.0  # seconds to wait for a locked SQLite: these calls run on the event loop
SCHEMA = """
CREATE TABLE IF NOT EXISTS prancheta_sumulas (
    id TEXT PRIMARY KEY,
    criada_em TEXT NOT NULL,
    encerrada_em TEXT NOT NULL,
    dados TEXT NOT NULL,
    sala TEXT
);
"""
# Since 2026-11-25 each game in a room has its own súmula (`<room>-<n>`) and `sala` says whose
# room it was. Older súmulas have the room's id and no `sala`.
COLUNA_SALA = "ALTER TABLE prancheta_sumulas ADD COLUMN sala TEXT"
INDICE_SALA = "CREATE INDEX IF NOT EXISTS prancheta_sumulas_sala ON prancheta_sumulas (sala)"


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
    forma: Literal["livre", "reta", "ret", "circ"] = "livre"


class Balde(_ComToken):
    tipo: Literal["balde"]
    id: int
    cor: int
    pt: list[int] = Field(min_length=2, max_length=2)


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


class Aceitar(_ComToken):
    tipo: Literal["aceitar"]
    pedido: int


class Recusar(_ComToken):
    tipo: Literal["recusar"]
    pedido: int


class NovaPartida(_ComToken):
    tipo: Literal["nova_partida"]
    rodadas: int


class Dica(_ComToken):
    tipo: Literal["dica"]


class Pular(_ComToken):
    tipo: Literal["pular"]


Acao = Annotated[
    Comecar
    | Escolher
    | Traco
    | Balde
    | Desfazer
    | Limpar
    | Chute
    | Cartao
    | Tirar
    | Sair
    | Aceitar
    | Recusar
    | Dica
    | Pular
    | NovaPartida,
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


class SemToken(logging.Filter):
    """Hides `token=` values in uvicorn's access log: the events URL carries the player's token."""

    PADRAO = re.compile(r"(token=)[^&\s\"]*")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                self.PADRAO.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args
            )
        if isinstance(record.msg, str):
            record.msg = self.PADRAO.sub(r"\1***", record.msg)
        return True


_SEM_TOKEN = SemToken()


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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path, timeout=ESPERA_DB)) as db, db:
            db.executescript(SCHEMA)
            colunas = {linha[1] for linha in db.execute("PRAGMA table_info(prancheta_sumulas)")}
            if "sala" not in colunas:
                db.execute(COLUNA_SALA)
            db.execute(INDICE_SALA)
        logging.getLogger("uvicorn.access").addFilter(_SEM_TOKEN)  # the same one: added once
        self.router = APIRouter(prefix="/api/jogos/prancheta")
        self._rotas()

    # --- leitura ---

    def viva(self, sala_id: str) -> bool:
        viva = self._salas.get(sala_id)
        return viva is not None and not viva.sala.encerrada

    def sumula(self, id_: str) -> dict | None:
        """A game's súmula by its own id, or a room's last one by the room's id; else None."""
        with closing(sqlite3.connect(self.db_path, timeout=ESPERA_DB)) as db:
            linha = db.execute(
                "SELECT dados FROM prancheta_sumulas WHERE id = ? OR sala = ?"
                " ORDER BY encerrada_em DESC, rowid DESC LIMIT 1",
                (id_, id_),
            ).fetchone()
        return json.loads(linha[0]) if linha else None

    def _gravar(
        self, id_: str, sala_id: str, criada_em: datetime, encerrada_em: datetime, dados: dict
    ):
        """Keeps a súmula; the first copy stays (the end is written once, whatever calls it)."""
        with closing(sqlite3.connect(self.db_path, timeout=ESPERA_DB)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO prancheta_sumulas (id, criada_em, encerrada_em, dados, sala)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    id_,
                    criada_em.isoformat(),
                    encerrada_em.isoformat(),
                    json.dumps(dados, ensure_ascii=False),
                    sala_id,
                ),
            )

    # --- laço ---

    async def rodar(self) -> None:
        """The lifespan's task: one step every half second, until cancelled."""
        while True:
            self.passo()
            await self._sleep(INTERVALO)

    def passo(self) -> None:
        """Moves every room's clock (deadlines, hints, absences) and delivers what changed.

        A room nobody has been connected to for 10 minutes, or 3 hours old, is closed: a game in
        progress goes to `fim` (and its súmula is kept), and the room leaves the memory; so does a
        room whose game ended 10 minutes ago with no next one. A room whose step fails is logged
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
                logger.exception("Prancheta room failed in the loop: %s", viva.sala.id)
                try:
                    self._retirar(viva)  # out of memory first, then its streams end
                except Exception:
                    logger.exception("Prancheta room %s: closing its streams failed", viva.sala.id)

    def _retirar(self, viva: _SalaViva) -> None:
        """Out of memory; its events streams end after what is already queued."""
        if self._salas.pop(viva.sala.id, None) is None:
            return  # already out (the end and the cleanup in the same step)
        for conexao in list(viva.conexoes):
            self._encerrar_fluxo(viva, conexao)

    def _encerrar_fluxo(self, viva: _SalaViva, conexao: _Conexao) -> None:
        """Ends a stream after what is already queued; it stops counting as a connection now."""
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
                if evento.exceto is not None and conexao.jogador == evento.exceto:
                    continue
                try:
                    conexao.fila.put_nowait((evento.tipo, evento.dados))
                except asyncio.QueueFull:  # a client that vanished without closing
                    conexao.derrubada = True
                    caidas.append(conexao)
        for conexao in caidas:
            logger.info("Prancheta %s: dropping a stalled events connection", viva.sala.id)
            self._desligar(viva, conexao)
        for conexao in [c for c in viva.conexoes if not viva.sala.esta(c.jogador)]:
            self._encerrar_fluxo(viva, conexao)  # left, sent off or refused: last word was sent
        sala = viva.sala
        for evento in eventos:
            if evento.tipo == "fim":  # a game is over; the room waits for the host's next one
                dados = evento.dados["sumula"]
                try:
                    self._gravar(dados["id"], sala.id, sala.partida_desde, self._now(), dados)
                except Exception:
                    logger.exception("Prancheta room %s: saving the súmula failed", sala.id)
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
            yield _sse(*item)

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
            sala = Sala(self._novo_id(), corpo.rodadas, self._banco, self._rng, agora)
            try:
                jogador, token, _ = sala.entrar(corpo.apelido, agora)
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            self._salas[sala.id] = _SalaViva(sala, vazia_desde=agora)
            return {"id": sala.id, "jogador": jogador, "token": token}

        @router.post("/salas/{sala_id}/entrar")
        async def entrar(sala_id: str, corpo: Entrada):
            """Asks the host to join: the token listens for the answer, then plays if accepted."""
            viva = self._salas.get(sala_id)
            if viva is None:
                return _erro(404, "room not found")
            try:
                pedido, token, eventos = viva.sala.pedir(corpo.apelido, self._now())
            except ErroSala as erro:
                return _erro(erro.status, erro.motivo)
            self._entregar(viva, eventos)
            return {"jogador": pedido, "token": token, "pendente": True}

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
                jogador = viva.sala.identificar(token)  # a request waiting listens too
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
