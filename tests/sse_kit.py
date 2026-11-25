"""Helpers for the live rooms' web tests: a fake clock and an events tab talking ASGI."""

import asyncio
import functools
import json
from datetime import datetime, timedelta

from fastapi import FastAPI

ESPERA = 2  # seconds a test waits for an event that must come at once (only when it fails)


def assincrono(teste):
    """Runs an async test in its own event loop (the suite has no async plugin)."""

    @functools.wraps(teste)
    def rodar(*args, **kwargs):
        asyncio.run(teste(*args, **kwargs))

    return rodar


class Relogio:
    def __init__(self, inicio: datetime) -> None:
        self.agora = inicio

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
