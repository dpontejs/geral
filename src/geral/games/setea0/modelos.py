"""The 7a0 contract: players, the draw, the matches and the campaign (`docs/features/setea0.md`)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

type Posicao = Literal["GOL", "ZAG", "LAT", "MEI", "ATA"]

# Slots go goalkeeper, full-backs, centre-backs, midfield, attack.
ESQUEMAS: dict[str, tuple[Posicao, ...]] = {
    "4-3-3": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "ATA", "ATA", "ATA"),
    "4-4-2": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "MEI", "ATA", "ATA"),
    "4-2-3-1": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "MEI", "MEI", "ATA"),
    "3-5-2": ("GOL", "ZAG", "ZAG", "ZAG", "MEI", "MEI", "MEI", "MEI", "MEI", "ATA", "ATA"),
    "5-3-2": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "ZAG", "MEI", "MEI", "MEI", "ATA", "ATA"),
}
MODOS: dict[str, int] = {"classico": 3, "almanaque": 1}  # decade rerolls per game


class Jogador(BaseModel):
    id: str
    nome: str
    posicoes: list[Posicao] = Field(min_length=1)
    # Years at the club, first and last; still there = the current year. Empty for the all-time
    # opponents of the velha base, who have no years.
    passagens: list[tuple[int, int]] = []
    forca: int = Field(ge=1, le=99)

    @field_validator("passagens")
    @classmethod
    def _em_ordem(cls, passagens: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if any(inicio > fim for inicio, fim in passagens):
            raise ValueError(f"passagem ao contrário: {passagens}")
        return passagens

    def decadas(self) -> set[int]:
        return {ano // 10 * 10 for inicio, fim in self.passagens for ano in range(inicio, fim + 1)}


class Clube(BaseModel):
    nome: str
    jogadores: list[Jogador]


class Dados(BaseModel):
    versao: str
    clubes: dict[str, Clube]  # slug -> club


class Rodada(BaseModel):
    rodada: int  # 0-10
    troca: int  # rerolls already used
    decada: int
    jogadores: list[Jogador]
    trocas_restantes: int


class Escolha(BaseModel):
    rodada: int
    troca: int
    jogador: str  # id
    vaga: int  # index in ESQUEMAS[esquema]


class Escalado(BaseModel):
    jogador: Jogador
    decada: int
    vaga: int


class Gol(BaseModel):
    minuto: int
    autor: str
    nosso: bool


class Cobranca(BaseModel):
    resultado: Literal["gol", "defesa", "fora", "trave", "motor"]


class Disputa(BaseModel):
    nossas: list[bool]  # True = goal
    deles: list[bool]


class Partida(BaseModel):
    n: int  # 1-7
    adversario: str  # slug
    gols: list[Gol]
    nosso: int
    deles: int
    disputa: Disputa | None
    venceu: bool


class PedidoDePenalti(BaseModel):
    n: int
    adversario: str
    nosso: int
    deles: int
    disputa: Disputa
    cobrador: str
    chance: int  # the kicker's strength, the minigame's difficulty


class Campanha(BaseModel):
    edicao: str
    modo: str
    esquema: str
    escalacao: list[Escalado]
    partidas: list[Partida]
    campeao: bool
    marcas: list[str]
    versao: str


class JogadaInvalida(ValueError):
    """A lineup or a call the draw does not allow."""
