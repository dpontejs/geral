"""Profanity filter for nicknames and guesses in the Prancheta."""

from functools import cache
from pathlib import Path

from geral.games.prancheta.tipos import normalizar

LISTA = Path(__file__).with_name("palavroes.txt")


@cache
def _termos() -> frozenset[str]:
    termos = set()
    for linha in LISTA.read_text(encoding="utf-8").splitlines():
        termo = normalizar(linha.split("#", 1)[0])
        if termo:
            termos.add(termo)
    return frozenset(termos)


def tem_palavrao(texto: str) -> bool:
    """True when a listed word (or phrase) appears as whole words in the normalized text."""
    alvo = f" {normalizar(texto)} "
    return any(f" {termo} " in alvo for termo in _termos())
