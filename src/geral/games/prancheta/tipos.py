"""Types shared by the Prancheta's room rules and word bank."""

import random
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

Dificuldade = Literal["facil", "media", "dificil"]
Veredito = Literal["certo", "trave", "errado"]


@dataclass(frozen=True)
class Palavra:
    texto: str
    aceita: tuple[str, ...]
    dificuldade: Dificuldade
    tipo: str


class Banco(Protocol):
    def opcoes(self, rng: random.Random, usadas: set[str]) -> list[Palavra]: ...
    def julgar(self, chute: str, palavra: Palavra) -> Veredito: ...


def normalizar(texto: str) -> str:
    """Lowercase, no accents, punctuation as spaces, spaces collapsed."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split())
