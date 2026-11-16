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


def started(duels):
    duel_id, x = duels.create(BOARD.code, T0)
    o = duels.join(duel_id, T0)
    return duel_id, x, o


def test_creator_is_x_and_the_first_to_join_is_o_then_nobody(duels) -> None:
    duel_id, x = duels.create(BOARD.code, T0)

    o = duels.join(duel_id, T0)

    assert x and o and x != o
    assert duels.join(duel_id, T0) is None
    row = duels.get(duel_id, T0, judge)
    assert (row.x_token, row.o_token, row.tabuleiro) == (x, o, BOARD.code)


def test_clock_starts_when_o_joins(duels) -> None:
    duel_id, _ = duels.create(BOARD.code, T0)
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
    duel_id, x = duels.create(BOARD.code, T0)
    with pytest.raises(DuelConflict):
        duels.play(duel_id, x, 0, {"casa": 4, "jogador": "Q40"}, T0, judge)


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
