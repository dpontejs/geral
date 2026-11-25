"""Pieces shared by the live rooms' events streams (Prancheta, Mano a Mano)."""

import json
import logging
import re
from collections.abc import Callable

from fastapi.responses import StreamingResponse


class Fluxo(StreamingResponse):
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


SEM_TOKEN = SemToken()  # the one instance: adding it again to a logger is a no-op


def sse(tipo: str, dados: dict) -> str:
    return f"event: {tipo}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"
