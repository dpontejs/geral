"""Small jogo da velha bases built in the tests (no base.json)."""

from geral.games.velha.base import Base, Player

CLUBS = {"Q5014111": "Vasco", "Q221695": "Grêmio", "Q17479": "Flamengo"}
COUNTRIES = {"Q77": "Uruguai", "Q414": "Argentina"}


def player(
    id: str,
    nome: str = "",
    *,
    clubes: tuple[str, ...] = (),
    selecao: bool = False,
    copa: bool = False,
    paises: tuple[str, ...] = (),
    posicoes: tuple[str, ...] = (),
    fama: int = 10,
    anos: str = "",
) -> Player:
    return Player(
        id=id,
        nome=nome or id,
        anos=anos,
        posicoes=posicoes,
        paises=paises,
        fama=fama,
        clubes=frozenset(clubes),
        selecao=selecao,
        copa=copa,
    )


def base(*players: Player, clubs: dict[str, str] = CLUBS) -> Base:
    return Base(players={p.id: p for p in players}, clubs=clubs, countries=COUNTRIES)
