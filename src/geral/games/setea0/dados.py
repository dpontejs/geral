"""Loading the 7a0 data: the brackets (`chaves.toml`) and the squads (`setea0.json`)."""

import tomllib
from functools import cache
from pathlib import Path

from geral.games.setea0.modelos import Dados

HERE = Path(__file__).parent
CHAVES = HERE / "chaves.toml"
DADOS = HERE / "setea0.json"


@cache
def chaves() -> dict:
    """The brackets; fails early when a bracket names a club with no `[clube.*]` source."""
    data = tomllib.loads(CHAVES.read_text(encoding="utf-8"))
    for slug, edicao in data["edicao"].items():
        for citado in [slug, *edicao["adversarios"], edicao["final"]]:
            if citado not in data["clube"]:
                raise ValueError(f"chaves.toml: {slug} cita {citado}, sem [clube.{citado}]")
    return data


@cache
def carregar(path: Path = DADOS) -> Dados:
    return Dados.model_validate_json(path.read_text(encoding="utf-8"))
