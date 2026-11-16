import pytest
from velha_fakes import crossed

from geral.games.velha.duelo import MAX_DRY_TURNS, Move, judge_duel
from geral.games.velha.judge import GuessError

B, BOARD = crossed()


def hit(casa: int, k: int = 0) -> Move:
    return Move(casa=casa, jogador=f"Q{casa}{k}")


def miss(casa: int) -> Move:
    return Move(casa=casa, jogador=f"Q{(casa + 1) % 9}3")  # a player of the next cell


TIMEOUT = Move(estouro=True)


def test_duel_x_starts_and_a_right_answer_takes_the_cell() -> None:
    state = judge_duel(B, BOARD, [])
    assert state.vez == "X" and not state.over

    state = judge_duel(B, BOARD, [hit(4)])
    assert state.casas == {4: "X"} and state.jogadores == {4: "Q40"}
    assert state.vez == "O" and state.acertos == [True]


def test_duel_wrong_answer_or_timeout_passes_the_turn() -> None:
    state = judge_duel(B, BOARD, [miss(0), TIMEOUT])
    assert state.casas == {} and state.acertos == [False, False]
    assert state.vez == "X" and state.sem_casa == 2


def test_duel_player_used_by_the_other_is_a_miss() -> None:
    reused = Move(casa=0, jogador="Q00")
    state = judge_duel(B, BOARD, [reused, Move(casa=1, jogador="Q00")])
    assert state.casas == {0: "X"} and state.acertos == [True, False]


def test_duel_three_in_a_row_wins_and_later_moves_are_rejected() -> None:
    # X: 0, 4, 8 (diagonal); O: 1, 2
    moves = [hit(0), hit(1), hit(4), hit(2), hit(8)]
    state = judge_duel(B, BOARD, moves)
    assert state.over and state.vencedor == "X" and state.linha == [0, 4, 8]
    with pytest.raises(GuessError):
        judge_duel(B, BOARD, [*moves, hit(3)])


def test_duel_line_that_fills_the_board_is_a_win() -> None:
    # X 0,1,4,5 then 8 (diagonal 0-4-8) on the 9th move; O 2,3,6,7 never lines up
    moves = [hit(0), hit(2), hit(1), hit(3), hit(4), hit(6), hit(5), hit(7), hit(8)]
    state = judge_duel(B, BOARD, moves)
    assert state.vencedor == "X" and state.linha is not None and len(state.casas) == 9


def test_duel_full_board_without_a_line_goes_to_most_cells_or_empate() -> None:
    # X takes 0,1,5,6,8 and O takes 2,3,4,7: no three in a row for either
    moves = [hit(0), hit(2), hit(1), hit(3), hit(5), hit(4), hit(6), hit(7), hit(8)]
    state = judge_duel(B, BOARD, moves)
    assert state.over and state.linha is None
    assert state.vencedor == "X"  # 5 cells against 4


def test_duel_ends_after_six_turns_without_a_cell_and_most_cells_wins() -> None:
    dry = [miss(8)] * (MAX_DRY_TURNS - 1)
    state = judge_duel(B, BOARD, [hit(0), *dry])
    assert not state.over and state.sem_casa == MAX_DRY_TURNS - 1

    state = judge_duel(B, BOARD, [hit(0), *dry, TIMEOUT])
    assert state.over and state.vencedor == "X" and state.linha is None

    state = judge_duel(B, BOARD, [hit(0), hit(1), *dry, TIMEOUT])
    assert state.over and state.vencedor == "empate"


def test_duel_a_cell_taken_resets_the_dry_count() -> None:
    state = judge_duel(B, BOARD, [miss(8)] * 5 + [hit(0)])
    assert state.sem_casa == 0 and not state.over


@pytest.mark.parametrize(
    "moves",
    [
        [hit(0), Move(casa=0, jogador="Q01")],  # taken cell
        [Move(casa=0, jogador="Q404")],
        [Move(casa=9, jogador="Q00")],
        [Move(jogador="Q00")],  # no cell and no timeout
        [Move(casa=0)],
    ],
)
def test_duel_rejects_taken_cell_unknown_player_and_move_without_cell(moves) -> None:
    with pytest.raises(GuessError):
        judge_duel(B, BOARD, moves)


def test_an_agreed_end_goes_to_the_most_cells_then_takes_no_more_moves() -> None:
    state = judge_duel(B, BOARD, [hit(0), miss(8), hit(4), Move(encerrar=True)])
    assert state.over and state.vencedor == "X" and state.linha is None and state.acordo
    assert not judge_duel(B, BOARD, [hit(0)]).acordo

    tie = judge_duel(B, BOARD, [hit(0), hit(1), Move(encerrar=True)])
    assert tie.over and tie.vencedor == "empate"

    with pytest.raises(GuessError):
        judge_duel(B, BOARD, [Move(encerrar=True), hit(0)])


def test_passing_the_turn_counts_like_a_timeout() -> None:
    state = judge_duel(B, BOARD, [Move(estouro=True)])
    assert state.vez == "O" and state.sem_casa == 1 and state.acertos == [False]
