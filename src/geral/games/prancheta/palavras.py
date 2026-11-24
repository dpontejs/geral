"""The Prancheta word bank: curated `palavras.toml`, the three options and the guess judge."""

import random
import tomllib
from functools import cache
from pathlib import Path
from typing import get_args

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from geral.games.prancheta.tipos import Dificuldade, Palavra, Veredito, normalizar

PALAVRAS = Path(__file__).with_name("palavras.toml")
DIFICULDADES: tuple[Dificuldade, ...] = get_args(Dificuldade)
TIPOS = frozenset(
    {"lance", "jogador", "clube", "estadio", "mascote", "apelido", "torcida", "objeto", "tecnico"}
)
TRAVE = 80  # fuzz.ratio from which a wrong guess is "na trave"
CURTA = 4  # words up to this many letters only hit the post one edit away


def _palavra(entrada: dict) -> Palavra:
    texto = entrada.get("texto", "")
    if not normalizar(texto):
        raise ValueError(f"palavra sem texto: {entrada!r}")
    if entrada.get("dificuldade") not in DIFICULDADES:
        raise ValueError(f"dificuldade inválida em {texto!r}: {entrada.get('dificuldade')!r}")
    if entrada.get("tipo") not in TIPOS:
        raise ValueError(f"tipo inválido em {texto!r}: {entrada.get('tipo')!r}")
    return Palavra(
        texto=texto,
        aceita=tuple(entrada.get("aceita", [])),
        dificuldade=entrada["dificuldade"],
        tipo=entrada["tipo"],
    )


def _contem(chute: str, alvo: str) -> bool:
    """Whole-word containment, so "o var" contains "var" but "variante" does not."""
    return f" {alvo} " in f" {chute} "


class BancoToml:
    """Implements `tipos.Banco` over a list of curated words."""

    def __init__(self, palavras: list[Palavra]):
        self.palavras = palavras
        self._por_dificuldade = {
            d: [p for p in palavras if p.dificuldade == d] for d in DIFICULDADES
        }

    def opcoes(self, rng: random.Random, usadas: set[str]) -> list[Palavra]:
        """One word per difficulty (easy, medium, hard), not yet used unless a level ran out."""
        escolhidas = []
        for dificuldade in DIFICULDADES:
            todas = self._por_dificuldade[dificuldade]
            livres = [p for p in todas if p.texto not in usadas]
            escolhidas.append(rng.choice(livres or todas))
        return escolhidas

    def julgar(self, chute: str, palavra: Palavra) -> Veredito:
        c = normalizar(chute)
        if not c:
            return "errado"
        alvos = {normalizar(a) for a in (palavra.texto, *palavra.aceita)} - {""}
        if c in alvos:
            return "certo"
        for alvo in alvos:
            if _contem(c, alvo):
                return "trave"
            if len(alvo.replace(" ", "")) <= CURTA:
                if Levenshtein.distance(c, alvo) == 1:
                    return "trave"
            elif fuzz.ratio(c, alvo) >= TRAVE:
                return "trave"
        return "errado"


def ler(path: Path) -> BancoToml:
    dados = tomllib.loads(path.read_text(encoding="utf-8"))
    return BancoToml([_palavra(e) for e in dados.get("palavra", [])])


@cache
def _padrao() -> BancoToml:
    return ler(PALAVRAS)


def carregar(path: Path | None = None) -> BancoToml:
    """The bank in `path`, or the default `palavras.toml` beside this module (cached)."""
    return _padrao() if path is None else ler(path)
