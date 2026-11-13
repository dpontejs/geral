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


MANY_CLUBS = {f"Q{100 + i}": f"Clube {i}" for i in range(8)}
POSITIONS = ("goleiro", "zagueiro", "lateral", "meio-campo", "atacante")


def synthetic(size: int = 300, seed: int = 7) -> Base:
    """A random but fixed base with 8 clubs, both countries and every position."""
    import random

    rng = random.Random(seed)
    players = [
        player(
            f"Q{1000 + n}",
            clubes=tuple(rng.sample(sorted(MANY_CLUBS), rng.randint(1, 4))),
            selecao=rng.random() < 0.3,
            copa=rng.random() < 0.3,
            paises=(rng.choice(sorted(COUNTRIES)),) if rng.random() < 0.2 else (),
            posicoes=(rng.choice(POSITIONS),),
            fama=rng.randint(1, 100),
        )
        for n in range(size)
    ]
    return base(*players, clubs=MANY_CLUBS)
