from datetime import UTC, datetime, timedelta

import pytest
from velha_fakes import crossed

from geral.games.velha.board import parse_board
from geral.games.velha.duelo import Move, judge_duel
from geral.web.velha_partidas import DuelConflict, DuelNotFound, DuelStore, NotYourTurn

B, BOARD = crossed()
T0 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def judge(code: str, jogadas: list[dict]):
    return judge_duel(B, parse_board(B, code), [Move(**m) for m in jogadas])


@pytest.fixture
def duels(tmp_path):
    return DuelStore(tmp_path / "geral.db")


def started(duels, creator="X"):
    """A duel with both players in: returns (id, X's token, O's token)."""
    duel_id, first, side = duels.create(BOARD.code, T0, creator)
    second, other = duels.join(duel_id, T0)
    assert {side, other} == {"X", "O"}
    return (duel_id, first, second) if side == "X" else (duel_id, second, first)


@pytest.mark.parametrize("creator, joiner", [("X", "O"), ("O", "X")])
def test_the_creator_gets_the_drawn_side_and_the_first_to_join_the_other(
    duels, creator, joiner
) -> None:
    duel_id, mine, side = duels.create(BOARD.code, T0, creator)

    theirs, other = duels.join(duel_id, T0)

    assert (side, other) == (creator, joiner) and mine != theirs
    assert duels.join(duel_id, T0) is None  # then nobody
    row = duels.get(duel_id, T0, judge)
    assert row.complete and {row.x_token, row.o_token} == {mine, theirs}


def test_clock_starts_when_o_joins(duels) -> None:
    duel_id, _, _ = duels.create(BOARD.code, T0, "O")
    assert duels.get(duel_id, T0 + timedelta(minutes=5), judge).prazo is None

    duels.join(duel_id, T0 + timedelta(minutes=5))

    assert duels.get(duel_id, T0 + timedelta(minutes=5), judge).prazo == T0 + timedelta(
        minutes=5, seconds=30
    )


def test_expired_turns_become_timeouts_on_read(duels) -> None:
    duel_id, _, _ = started(duels)

    row = duels.get(duel_id, T0 + timedelta(seconds=65), judge)

    assert row.jogadas == [{"estouro": True}, {"estouro": True}]
    assert row.prazo == T0 + timedelta(seconds=90)
    assert judge(row.tabuleiro, row.jogadas).vez == "X"


def test_six_timeouts_end_the_duel_and_stop_the_clock(duels) -> None:
    duel_id, _, _ = started(duels)

    row = duels.get(duel_id, T0 + timedelta(hours=1), judge)

    assert len(row.jogadas) == 6 and row.prazo is None
    assert judge(row.tabuleiro, row.jogadas).vencedor == "empate"


def test_a_move_takes_the_cell_and_restarts_the_clock(duels) -> None:
    duel_id, x, _ = started(duels)

    row = duels.play(
        duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0 + timedelta(seconds=10), judge
    )

    assert judge(row.tabuleiro, row.jogadas).casas == {4: "X"}
    assert row.prazo == T0 + timedelta(seconds=40)


def test_same_move_twice_counts_once(duels) -> None:
    duel_id, x, _ = started(duels)
    move = {"casa": 4, "jogador": "Q40"}

    duels.play(duel_id, x, 0, move, T0, judge)
    row = duels.play(duel_id, x, 0, move, T0, judge)  # the retry still says "I saw 0 moves"

    assert len(row.jogadas) == 1


def test_only_the_side_on_turn_plays(duels) -> None:
    duel_id, x, o = started(duels)
    with pytest.raises(NotYourTurn):
        duels.play(duel_id, o, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)
    with pytest.raises(NotYourTurn):
        duels.play(duel_id, "someone-else", 0, {"casa": 4, "jogador": "Q40"}, T0, judge)
    duels.play(duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)
    with pytest.raises(DuelConflict):  # taken cell
        duels.play(duel_id, o, 1, {"casa": 4, "jogador": "Q41"}, T0, judge)


def test_x_waits_for_o(duels) -> None:
    duel_id, x, _ = duels.create(BOARD.code, T0, "X")
    with pytest.raises(DuelConflict):
        duels.play(duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)


def win_for_x(duels, duel_id, x, o) -> None:
    for n, (token, casa) in enumerate([(x, 0), (o, 1), (x, 4), (o, 2), (x, 8)]):
        duels.play(duel_id, token, n, {"casa": casa, "jogador": f"Q{casa}0"}, T0, judge)


def test_rematch_swaps_the_sides_and_both_players_land_in_the_same_duel(duels) -> None:
    duel_id, x, o = started(duels)
    win_for_x(duels, duel_id, x, o)

    new_id, x_now_o, side = duels.rematch(duel_id, x, T0, judge, BOARD.code)
    again = duels.rematch(duel_id, x, T0, judge, BOARD.code)  # a retry: the same answer
    same_id, o_now_x, other = duels.rematch(duel_id, o, T0, judge, BOARD.code)

    assert (side, other) == ("O", "X") and again == (new_id, x_now_o, side)
    assert same_id == new_id and duels.get(duel_id, T0, judge).revanche == new_id
    row = duels.get(new_id, T0, judge)
    assert row.complete and (row.x_token, row.o_token) == (o_now_x, x_now_o)
    assert row.prazo == T0 + timedelta(seconds=30)  # the clock starts when the second is in


def test_rematch_needs_a_finished_duel_and_a_player(duels) -> None:
    duel_id, x, o = started(duels)
    with pytest.raises(DuelConflict):
        duels.rematch(duel_id, x, T0, judge, BOARD.code)
    win_for_x(duels, duel_id, x, o)
    with pytest.raises(NotYourTurn):
        duels.rematch(duel_id, "watcher", T0, judge, BOARD.code)


def test_old_duels_are_gone_after_24_hours(duels) -> None:
    duel_id, _, _ = started(duels)
    later = T0 + timedelta(hours=24, seconds=1)

    with pytest.raises(DuelNotFound):
        duels.get(duel_id, later, judge)
    with pytest.raises(DuelNotFound):
        duels.get("nope", T0, judge)
    duels.purge(later)
    with pytest.raises(DuelNotFound):
        duels.get(duel_id, T0, judge)  # deleted, not only hidden


_parts = BOARD.code.split("|")
OTHER = parse_board(B, "|".join(_parts[3:] + _parts[:3]))  # rows and columns swapped


def test_ending_needs_the_other_player(duels) -> None:
    duel_id, x, o = started(duels)
    duels.play(duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)

    duels.propose(duel_id, o, "encerrar", T0, judge)
    assert duels.get(duel_id, T0, judge).proposta == {"tipo": "encerrar", "lado": "O"}
    with pytest.raises(DuelConflict):  # the one who asked cannot accept it
        duels.answer(duel_id, o, True, T0, judge, BOARD.code)
    row = duels.answer(duel_id, x, True, T0, judge, BOARD.code)

    state = judge(row.tabuleiro, row.jogadas)
    assert state.over and state.vencedor == "X" and row.proposta is None and row.prazo is None


def test_a_new_draw_restarts_the_board_and_keeps_the_sides(duels) -> None:
    duel_id, x, o = started(duels)
    duels.play(duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)
    duels.propose(duel_id, x, "sortear", T0, judge)

    later = T0 + timedelta(seconds=5)
    row = duels.answer(duel_id, o, True, later, judge, OTHER.code)

    assert row.tabuleiro == OTHER.code and row.jogadas == []
    assert (row.x_token, row.o_token) == (x, o) and row.prazo == later + timedelta(seconds=30)


def test_a_proposal_can_be_refused_withdrawn_or_dropped_by_a_move(duels) -> None:
    duel_id, x, o = started(duels)
    duels.propose(duel_id, x, "sortear", T0, judge)
    assert duels.answer(duel_id, o, False, T0, judge, OTHER.code).proposta is None  # refused
    duels.propose(duel_id, x, "encerrar", T0, judge)
    assert duels.answer(duel_id, x, False, T0, judge, OTHER.code).proposta is None  # withdrawn
    duels.propose(duel_id, o, "encerrar", T0, judge)
    row = duels.play(duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)
    assert row.proposta is None  # a move goes on with the game
    with pytest.raises(DuelConflict):
        duels.answer(duel_id, x, True, T0, judge, OTHER.code)  # nothing to answer
    with pytest.raises(NotYourTurn):
        duels.propose(duel_id, "watcher", "encerrar", T0, judge)


def test_the_player_on_turn_can_pass(duels) -> None:
    duel_id, x, _ = started(duels)
    row = duels.play(duel_id, x, 0, {"estouro": True}, T0, judge)
    assert judge(row.tabuleiro, row.jogadas).vez == "O"
