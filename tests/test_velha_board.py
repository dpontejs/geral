import random

import pytest
from velha_fakes import synthetic

from geral.games.velha.base import answers
from geral.games.velha.board import make_board, parse_board

BASE = synthetic()


def test_make_board_gives_every_cell_three_answers() -> None:
    for seed in range(200):
        board = make_board(BASE, random.Random(seed))
        categories = [*board.rows, *board.cols]
        assert len(set(categories)) == 6
        assert sum(c.kind in ("posicao", "pais") for c in categories) <= 2
        for casa in range(9):
            assert len(answers(BASE, *board.cell(casa))) >= 3, (seed, casa)


def test_make_board_is_the_same_for_the_same_seed() -> None:
    first = make_board(BASE, random.Random("velha:3"))
    assert make_board(BASE, random.Random("velha:3")) == first
    assert make_board(BASE, random.Random("velha:4")) != first


def test_board_code_round_trips() -> None:
    board = make_board(BASE, random.Random(1))
    assert board.code.count("|") == 5
    assert parse_board(BASE, board.code) == board


def test_cell_is_row_then_column() -> None:
    board = make_board(BASE, random.Random(1))
    assert board.cell(0) == (board.rows[0], board.cols[0])
    assert board.cell(5) == (board.rows[1], board.cols[2])
    assert board.cell(8) == (board.rows[2], board.cols[2])


@pytest.mark.parametrize(
    "code",
    [
        "selecao:BRA|copa:FIFA|clube:Q100|clube:Q101|clube:Q102",
        "selecao:BRA|copa:FIFA|clube:Q100|clube:Q101|clube:Q102|clube:Q100",
        "selecao:BRA|copa:FIFA|clube:Q100|clube:Q101|clube:Q102|clube:Q999",
    ],
)
def test_parse_board_rejects_wrong_size_repeats_and_unknown(code) -> None:
    with pytest.raises(ValueError):
        parse_board(BASE, code)


def test_make_board_on_a_tiny_base_fails_instead_of_looping() -> None:
    from velha_fakes import base, player

    tiny = base(player("Q1", clubes=("Q5014111",)), clubs={"Q5014111": "Vasco"})
    with pytest.raises(RuntimeError):
        make_board(tiny, random.Random(1))
