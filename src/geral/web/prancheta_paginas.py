"""The Prancheta's pages: create a room, the live room and the súmula left at its short link.

The API and the live events are slice D's (`geral.web.prancheta`); these pages only ask it
whether a room is alive and for a finished room's súmula. `render` is the app's template helper.
"""

from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

REGRAS = [
    "Crie a sala, escolha quantas rodadas e mande o link no grupo. De 2 a 10 jogadores.",
    "Na sua vez, escolha uma de 3 palavras e desenhe na prancheta. Nada de escrever a palavra.",
    "Os outros chutam. Quanto mais cedo e mais difícil a palavra, mais pontos; quem desenha "
    "ganha 2 por acerto.",
    '"Na trave" quer dizer que você chegou perto: só você vê. Aos 40 e aos 20 segundos acende '
    "uma letra.",
]


class Salas(Protocol):
    def viva(self, sala_id: str) -> bool: ...
    def sumula(self, sala_id: str) -> dict | None: ...


def paginas_prancheta(prancheta: Salas, render: Callable[..., Response]) -> APIRouter:
    router = APIRouter()

    def jogo(request: Request, sala_id: str = "") -> Response:
        return render(request, "prancheta.html.j2", sala_id=sala_id, rules=REGRAS)

    @router.get("/jogos/prancheta", response_class=HTMLResponse)
    def criar(request: Request):
        return jogo(request)

    @router.get("/jogos/prancheta/s/{sala_id}", response_class=HTMLResponse)
    def sala(request: Request, sala_id: str):
        # A room that just ended may still be in memory: its súmula wins.
        sumula = prancheta.sumula(sala_id)
        if sumula is not None:
            return render(
                request, "prancheta_sumula.html.j2", sala_id=sala_id, sumula=sumula, rules=REGRAS
            )
        if prancheta.viva(sala_id):
            return jogo(request, sala_id)
        return render(
            request,
            "message.html.j2",
            404,
            title="Sala não encontrada",
            text="A sala acabou ou o servidor reiniciou. Crie outra e mande o link de novo.",
            link_url="/jogos/prancheta",
            link_label="Nova sala",
        )

    return router
