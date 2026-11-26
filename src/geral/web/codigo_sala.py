"""The live rooms' short code (Prancheta, Mano a Mano): the 6 characters at the end of the link.

People can type it instead of sending the whole link, like in the Gartic (dev, 2026-11-26), so
it is read loosely: any case, with spaces or hyphens in the middle.
"""

import re

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

CODIGO = re.compile(r"[a-z2-7]{6}")  # the rooms' alphabet: base32, lowercase


def normalizar(texto: str) -> str | None:
    """The code as the room's id, or None when it cannot be one."""
    codigo = re.sub(r"[\s-]+", "", texto).lower()
    return codigo if CODIGO.fullmatch(codigo) else None


def entrar(request: Request, jogo: str, codigo: str, render) -> Response:
    """`GET /jogos/{jogo}/entrar?codigo=`: to the room's page, or a notice for a bad code."""
    sala_id = normalizar(codigo)
    if sala_id is not None:
        return RedirectResponse(f"/jogos/{jogo}/s/{sala_id}", status_code=303)
    return render(
        request,
        "message.html.j2",
        404,
        title="Código inválido",
        text="O código da sala tem 6 letras e números, como K7M2QX. Confira com quem te chamou.",
        link_url=f"/jogos/{jogo}",
        link_label="Voltar",
    )


def em_minusculas(jogo: str, sala_id: str) -> Response | None:
    """A link typed in capitals goes to the room's own (lowercase) link."""
    if sala_id != sala_id.lower():
        return RedirectResponse(f"/jogos/{jogo}/s/{sala_id.lower()}", status_code=301)
    return None
