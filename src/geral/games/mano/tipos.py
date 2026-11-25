"""Types shared by the Mano a Mano rules, bot and shootout."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Lado = Literal["esquerda", "fica", "direita"]
Trajetoria = Literal["rasteira", "por_cima", "pelo_lado"]
Resultado = Literal["gol", "defesa", "trave", "fora", "barreira"]
Modo = Literal["penaltis", "faltas"]
Nivel = Literal["facil", "medio", "dificil"]

Coord = Annotated[int, Field(ge=0, le=1000)]


class Chute(BaseModel):
    alvo: tuple[Coord, Coord]
    barra: Coord
    trajetoria: Trajetoria | None = None
    curva: float = Field(default=0, ge=-1, le=1)


class Defesa(BaseModel):
    lado: Lado
    saida: bool


class Barreira(BaseModel):
    n: int = Field(ge=2, le=5)
    x: Coord


class Posicao(BaseModel):
    nome: Literal["meia_lua", "entrada_esquerda", "entrada_direita"]
    desvio: int = Field(ge=-80, le=80)


class Lance(BaseModel):
    chute: Chute
    defesa: Defesa
    barreira: Barreira | None
    posicao: Posicao | None
    onde: tuple[int, int]
    resultado: Resultado
