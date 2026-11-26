"""The Mano a Mano's pages: create a room, the live room and the súmula left at its link.

The API and the live events are `geral.web.mano`'s; these pages only ask it whether a room is
alive and for a finished match's súmula. `render` is the app's template helper.
"""

from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

REGRAS = [
    "Batedor contra goleiro, um de cada vez: crie a sala, escolha pênaltis ou faltas e mande o "
    "link para um amigo, ou jogue contra o bot.",
    "Quem bate mira num ponto do gol e para a barra na faixa acesa. Perto da trave e do "
    "travessão a faixa estreita. Passou da faixa, a bola sobe (travessão ou pra fora); ficou "
    "abaixo, o chute sai fraco e o goleiro alcança mais longe.",
    "No pênalti dá para bater de cavadinha: a bola vai no meio, com uma faixa mais estreita. "
    "Contra goleiro que pula é gol; contra quem fica, defesa.",
    "Quem defende escolhe às escondidas: pular para um lado ou ficar. Na hora do chute, aperte "
    "espaço, Enter ou toque na tela: saindo no tempo, o goleiro alcança mais longe.",
    "Na falta, o goleiro arma a barreira antes; o batedor escolhe rasteira, por cima ou pelo "
    "lado, e a curva.",
    "Cinco cobranças para cada um, alternando; empatou, alternadas até alguém errar. Cada "
    "partida tem a sua súmula, no seu link.",
]


# Without the free-kick mode (MANO_FALTAS off): the same rules, minus what only free kicks have.
REGRAS_SEM_FALTAS = [
    "Batedor contra goleiro, um de cada vez: crie a sala e mande o link para um amigo, ou jogue "
    "contra o bot.",
    *(r for r in REGRAS[1:] if "barreira" not in r),
]


class Salas(Protocol):
    faltas: bool

    def viva(self, sala_id: str) -> bool: ...
    def cheia(self, sala_id: str) -> bool: ...
    def sumula(self, id_: str) -> dict | None: ...


def paginas_mano(mano: Salas, render: Callable[..., Response]) -> APIRouter:
    router = APIRouter()

    def jogo(request: Request, sala_id: str = "") -> Response:
        cheia = bool(sala_id) and mano.cheia(sala_id)
        return render(
            request,
            "mano.html.j2",
            sala_id=sala_id,
            cheia=cheia,
            faltas=mano.faltas,
            rules=regras(),
        )

    def regras() -> list[str]:
        return REGRAS if mano.faltas else REGRAS_SEM_FALTAS

    @router.get("/jogos/mano", response_class=HTMLResponse)
    def criar(request: Request):
        return jogo(request)

    @router.get("/jogos/mano/s/{sala_id}", response_class=HTMLResponse)
    def sala(request: Request, sala_id: str):
        # A live room (also at the end of a match, waiting for the rematch) is the game; else
        # the súmula of that match (`{sala}-{n}`), or the room's last one.
        if mano.viva(sala_id):
            return jogo(request, sala_id)
        sumula = mano.sumula(sala_id)
        if sumula is not None:
            return render(
                request, "mano_sumula.html.j2", sala_id=sala_id, sumula=sumula, rules=regras()
            )
        return render(
            request,
            "message.html.j2",
            404,
            title="Sala não encontrada",
            text="A sala acabou ou o servidor reiniciou. Crie outra e mande o link de novo.",
            link_url="/jogos/mano",
            link_label="Nova sala",
        )

    return router
