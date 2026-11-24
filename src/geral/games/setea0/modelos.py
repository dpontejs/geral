"""The 7a0 contract: players, the draw, the matches and the campaign (`docs/features/setea0.md`)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

type Posicao = Literal["GOL", "ZAG", "LAT", "MEI", "ATA"]
POSICOES: frozenset[Posicao] = frozenset(("GOL", "ZAG", "LAT", "MEI", "ATA"))

# Slots go goalkeeper, full-backs, centre-backs, midfield, attack.
ESQUEMAS: dict[str, tuple[Posicao, ...]] = {
    "4-3-3": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "ATA", "ATA", "ATA"),
    "4-4-2": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "MEI", "ATA", "ATA"),
    "4-2-3-1": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "MEI", "MEI", "MEI", "MEI", "MEI", "ATA"),
    "3-5-2": ("GOL", "ZAG", "ZAG", "ZAG", "MEI", "MEI", "MEI", "MEI", "MEI", "ATA", "ATA"),
    "5-3-2": ("GOL", "LAT", "LAT", "ZAG", "ZAG", "ZAG", "MEI", "MEI", "MEI", "ATA", "ATA"),
}
MODOS: dict[str, int] = {"classico": 3, "almanaque": 1}  # era rerolls per game
MIN_EPOCA = 8  # players an era needs; thin decades join the next ones until it has them
PRIMEIRA_DECADA = 1970  # older decades never draw (dev, 2026-11-24)


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


class Epoca(BaseModel):
    """What the die draws: one decade, or a run of thin ones ("anos 60 a 80"). Frozen: a key."""

    model_config = ConfigDict(frozen=True)

    inicio: int  # first decade, 1960
    fim: int  # last decade, inclusive
    rotulo: str

    def contem(self, jogador: Jogador) -> bool:
        return any(self.inicio <= d <= self.fim for d in jogador.decadas())


def _curta(decada: int) -> str:
    return str(decada) if decada >= 2000 else f"{decada % 100:02d}"


def _epoca(inicio: int, fim: int) -> Epoca:
    rotulo = f"anos {_curta(inicio)}" + (f" a {_curta(fim)}" if fim != inicio else "")
    return Epoca(inicio=inicio, fim=fim, rotulo=rotulo)


def epocas(
    jogadores: list[Jogador], minimo: int = MIN_EPOCA, desde: int = PRIMEIRA_DECADA
) -> list[Epoca]:
    """A club's eras, oldest first: decades from `desde` in order, joined until an era has
    `minimo` players and someone for every position (an offer always has a keeper to give).

    A thin run left at the end joins the last era; a club that never fills an era has a single
    one. Eras never start before `desde`, so whoever only played earlier is in none.
    """
    por_decada: dict[int, dict[str, Jogador]] = {}
    for jogador in jogadores:
        for decada in jogador.decadas():
            if decada >= desde:
                por_decada.setdefault(decada, {})[jogador.id] = jogador
    grupos: list[tuple[int, int]] = []
    aberto: tuple[int, dict[str, Jogador]] | None = None
    for decada in sorted(por_decada):
        inicio, elenco = aberto or (decada, {})
        elenco = elenco | por_decada[decada]
        posicoes = {p for j in elenco.values() for p in j.posicoes}
        if len(elenco) >= minimo and posicoes >= POSICOES:
            grupos.append((inicio, decada))
            aberto = None
        else:
            aberto = (inicio, elenco)
    if aberto:
        inicio = grupos.pop()[0] if grupos else aberto[0]
        grupos.append((inicio, max(por_decada)))
    return [_epoca(inicio, fim) for inicio, fim in grupos]


class Clube(BaseModel):
    nome: str
    jogadores: list[Jogador]


class Dados(BaseModel):
    versao: str
    clubes: dict[str, Clube]  # slug -> club


class Rodada(BaseModel):
    rodada: int  # 0-10
    troca: int  # rerolls already used
    epoca: Epoca
    jogadores: list[Jogador]
    trocas_restantes: int


class Escolha(BaseModel):
    rodada: int
    troca: int
    jogador: str  # id
    vaga: int  # index in ESQUEMAS[esquema]


class Escalado(BaseModel):
    jogador: Jogador
    epoca: Epoca
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
