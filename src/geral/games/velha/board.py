"""The 3×3 board: three row and three column categories, every cell with a few answers."""

import random
from dataclasses import dataclass

from geral.games.velha.base import COPA, SELECAO, Base, Category, category

MIN_ANSWERS = 3  # per cell
MAX_SOFT = 2  # positions and countries together: a board of only those is dull
MIN_POOL = 10  # players a country or position needs to be drawn
KIND_WEIGHTS = {"clube": 6, "selecao": 1, "copa": 1, "pais": 1, "posicao": 1}
TRIES = 2000


@dataclass(frozen=True)
class Board:
    rows: tuple[Category, ...]
    cols: tuple[Category, ...]

    @property
    def code(self) -> str:
        """'clube:Q17479|selecao:BRA|…': three rows then three columns."""
        return "|".join(c.code for c in (*self.rows, *self.cols))

    def cell(self, casa: int) -> tuple[Category, Category]:
        """Cell 0–8, row by row: (row category, column category)."""
        if not 0 <= casa <= 8:
            raise ValueError(f"no cell {casa}")
        return self.rows[casa // 3], self.cols[casa % 3]


def parse_board(base: Base, code: str) -> Board:
    cats = [category(base, part) for part in code.split("|")]
    if len(cats) != 6 or len(set(cats)) != 6:
        raise ValueError(f"a board has six distinct categories: {code!r}")
    return Board(tuple(cats[:3]), tuple(cats[3:]))


def _pool(base: Base) -> dict[str, list[Category]]:
    pool = {
        "clube": [category(base, f"clube:{q}") for q in sorted(base.clubs)],
        "selecao": [category(base, SELECAO)],
        "copa": [category(base, COPA)],
        "pais": [category(base, f"pais:{q}") for q in sorted(base.countries)],
        "posicao": [
            category(base, f"posicao:{p}")
            for p in sorted({p for player in base.players.values() for p in player.posicoes})
        ],
    }
    for kind in ("pais", "posicao"):
        pool[kind] = [c for c in pool[kind] if len(base.players_in(c)) >= MIN_POOL]
    return {kind: cats for kind, cats in pool.items() if cats}


def _valid(base: Base, board: Board) -> bool:
    cats = (*board.rows, *board.cols)
    if sum(c.kind in ("pais", "posicao") for c in cats) > MAX_SOFT:
        return False
    return all(
        len(base.players_in(r) & base.players_in(c)) >= MIN_ANSWERS
        for r in board.rows
        for c in board.cols
    )


def make_board(base: Base, rng: random.Random) -> Board:
    """A valid board drawn with `rng` (the same seed gives the same board)."""
    pool = _pool(base)
    kinds = sorted(pool)
    weights = [KIND_WEIGHTS[k] for k in kinds]
    if sum(len(cats) for cats in pool.values()) < 6:
        raise RuntimeError("no valid board: fewer than six categories")
    for _ in range(TRIES):
        chosen: list[Category] = []
        while len(chosen) < 6:
            cat = rng.choice(pool[rng.choices(kinds, weights)[0]])
            if cat not in chosen:
                chosen.append(cat)
        board = Board(tuple(chosen[:3]), tuple(chosen[3:]))
        if _valid(base, board):
            return board
    raise RuntimeError("no valid board: the base is too thin")
