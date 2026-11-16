"""Duel by link: X creates, O joins by the link, others watch; the server owns clock and rules."""

import asyncio
from datetime import timedelta

import pytest
from webkit import make_client

from geral.games.velha.base import answers, load
from geral.games.velha.board import parse_board
from geral.web.velha_partidas import duel_events

API = "/api/jogos/velha/partidas"
BASE = load()


@pytest.fixture
def game(store, mailer, clock):
    return make_client(store, mailer, clock)


def new_duel(game):
    """A duel with both in: (id, X's token, O's token, board), whoever the creator was."""
    created = game.post(API).json()
    joined = game.post(f"{API}/{created['id']}/entrar").json()
    assert {created["lado"], joined["lado"]} == {"X", "O"}
    tokens = {created["lado"]: created["token"], joined["lado"]: joined["token"]}
    state = game.get(f"{API}/{created['id']}").json()
    return created["id"], tokens["X"], tokens["O"], parse_board(BASE, state["codigo"])


def right(board, casa, skip=()):
    return next(p.id for p in answers(BASE, *board.cell(casa)) if p.id not in skip)


def wrong(board, casa):
    return next(p.id for p in BASE.players.values() if p not in answers(BASE, *board.cell(casa)))


def move(game, duel_id, token, vez_n, casa, jogador):
    body = {"token": token, "vez_n": vez_n, "casa": casa, "jogador": jogador}
    return game.post(f"{API}/{duel_id}/jogada", json=body)


def test_the_creator_side_is_drawn(game) -> None:
    sides = {game.post(API).json()["lado"] for _ in range(20)}
    assert sides == {"X", "O"}


def test_duel_creator_is_x_and_the_first_to_join_is_o_then_others_only_watch(game) -> None:
    # The spec's name: the creator's side is drawn now (X or O); the rest of the rule stands.
    duel_id, x, o, _ = new_duel(game)

    assert x != o
    assert game.post(f"{API}/{duel_id}/entrar").status_code == 409
    page = game.get(f"/jogos/velha/p/{duel_id}")
    assert page.status_code == 200 and x not in page.text and o not in page.text
    state = game.get(f"{API}/{duel_id}").json()
    assert state["completo"] and state["vez"] == "X" and "x_token" not in state


def test_duel_move_out_of_turn_or_with_the_other_token_is_403(game) -> None:
    duel_id, x, o, board = new_duel(game)

    assert move(game, duel_id, o, 0, 4, right(board, 4)).status_code == 403
    assert move(game, duel_id, "watcher", 0, 4, right(board, 4)).status_code == 403
    assert move(game, duel_id, x, 0, 4, right(board, 4)).status_code == 200


def test_duel_wrong_answer_or_timeout_passes_the_turn(game, clock) -> None:
    duel_id, x, o, board = new_duel(game)

    state = move(game, duel_id, x, 0, 0, wrong(board, 0)).json()
    assert state["vez"] == "O" and state["casas"] == {}
    clock.now += timedelta(seconds=31)
    state = game.get(f"{API}/{duel_id}").json()
    assert state["vez"] == "X" and state["jogou"] == 2 and state["sem_casa"] == 2


def test_duel_three_in_a_row_wins_and_later_moves_are_409(game) -> None:
    duel_id, x, o, board = new_duel(game)
    used: list[str] = []
    for n, (token, casa) in enumerate([(x, 0), (o, 1), (x, 4), (o, 2), (x, 8)]):
        used.append(right(board, casa, used))
        state = move(game, duel_id, token, n, casa, used[-1]).json()

    assert state["over"] and state["vencedor"] == "X" and state["linha"] == [0, 4, 8]
    assert state["nomes"][used[0]]
    assert move(game, duel_id, o, 5, 3, right(board, 3, used)).status_code == 409


def test_rematch_swaps_the_sides_for_both_players(game) -> None:
    duel_id, x, o, board = new_duel(game)
    assert game.post(f"{API}/{duel_id}/revanche", json={"token": x}).status_code == 409
    used: list[str] = []
    for n, (token, casa) in enumerate([(x, 0), (o, 1), (x, 4), (o, 2), (x, 8)]):
        used.append(right(board, casa, used))
        move(game, duel_id, token, n, casa, used[-1])

    first = game.post(f"{API}/{duel_id}/revanche", json={"token": x}).json()
    assert game.get(f"{API}/{duel_id}").json()["revanche"] == first["id"]
    second = game.post(f"{API}/{duel_id}/revanche", json={"token": o}).json()

    assert first["id"] == second["id"] and (first["lado"], second["lado"]) == ("O", "X")
    assert game.get(f"{API}/{first['id']}").json()["completo"]
    assert game.post(f"{API}/{duel_id}/revanche", json={"token": "who"}).status_code == 403
    assert game.post(f"{API}/{first['id']}/entrar").status_code == 409  # nobody else sits in


def test_duel_ends_after_six_turns_without_a_cell_and_most_cells_wins(game, clock) -> None:
    duel_id, x, o, board = new_duel(game)
    move(game, duel_id, x, 0, 4, right(board, 4))
    clock.now += timedelta(seconds=30 * 6 + 1)  # nobody plays: six timeouts in a row

    state = game.get(f"{API}/{duel_id}").json()

    assert state["over"] and state["vencedor"] == "X" and state["prazo"] is None


def test_duel_same_move_twice_counts_once(game) -> None:
    duel_id, x, _, board = new_duel(game)
    pick = right(board, 4)

    move(game, duel_id, x, 0, 4, pick)
    again = move(game, duel_id, x, 0, 4, pick)

    assert again.status_code == 200 and again.json()["jogou"] == 1


def test_unknown_player_is_422(game) -> None:
    duel_id, x, _, _ = new_duel(game)
    assert move(game, duel_id, x, 0, 4, "Q0").status_code == 422


def test_unknown_or_old_duel_is_404(game, clock) -> None:
    duel_id, x, _, board = new_duel(game)
    clock.now += timedelta(hours=25)

    assert game.get(f"{API}/{duel_id}").status_code == 404
    assert game.post(f"{API}/{duel_id}/entrar").status_code == 404
    assert move(game, duel_id, x, 0, 4, right(board, 4)).status_code == 404
    assert game.get("/jogos/velha/p/nope").status_code == 404


def test_creating_duels_is_limited_per_network(game) -> None:
    codes = [game.post(API).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_duel_events_stream_sends_the_new_state_after_a_move() -> None:
    views = iter(
        [
            {"jogou": 0, "completo": True, "prazo": "t1", "over": False},
            {"jogou": 0, "completo": True, "prazo": "t1", "over": False},  # nothing new
            {"jogou": 1, "completo": True, "prazo": "t2", "over": False},  # a move
            {"jogou": 5, "completo": True, "prazo": None, "over": True},  # the end
            {"jogou": 5, "completo": True, "prazo": None, "over": True},  # waiting for a rematch
            {"jogou": 5, "completo": True, "prazo": None, "over": True, "revanche": "r1"},
        ]
    )

    async def load():
        return next(views)

    async def sleep(_):
        return None

    async def collect():
        return [event async for event in duel_events(load, sleep)]

    events = asyncio.run(collect())

    assert len(events) == 4 and all(e.startswith("data: {") and e.endswith("\n\n") for e in events)
    assert '"jogou": 1' in events[1] and '"over": true' in events[2]
    assert '"revanche": "r1"' in events[3]  # the stream stays open after the end for the rematch


def test_the_board_stays_hidden_until_o_joins(game) -> None:
    created = game.post(API).json()

    waiting = game.get(f"{API}/{created['id']}").json()
    game.post(f"{API}/{created['id']}/entrar")
    playing = game.get(f"{API}/{created['id']}").json()

    assert not waiting["completo"]
    assert waiting["codigo"] is None and waiting["linhas"] == ["?"] * 3
    assert waiting["colunas"] == ["?"] * 3
    assert playing["codigo"] and "?" not in playing["linhas"]


def test_passing_hands_the_turn_over(game) -> None:
    duel_id, x, _, _ = new_duel(game)
    body = {"token": x, "vez_n": 0, "pular": True}

    state = game.post(f"{API}/{duel_id}/jogada", json=body).json()

    assert state["vez"] == "O" and state["sem_casa"] == 1


def test_ending_and_a_new_draw_need_both_players(game) -> None:
    duel_id, x, o, board = new_duel(game)
    move(game, duel_id, x, 0, 4, right(board, 4))

    asked = game.post(f"{API}/{duel_id}/propor", json={"token": x, "tipo": "sortear"}).json()
    assert asked["proposta"] == {"tipo": "sortear", "lado": "X"}
    self_ok = {"token": x, "aceita": True}
    assert game.post(f"{API}/{duel_id}/responder", json=self_ok).status_code == 409
    wrong_kind = {"token": o, "aceita": True, "tipo": "encerrar"}
    assert game.post(f"{API}/{duel_id}/responder", json=wrong_kind).status_code == 409
    accept = {"token": o, "aceita": True, "tipo": "sortear"}
    redrawn = game.post(f"{API}/{duel_id}/responder", json=accept).json()
    assert redrawn["jogou"] == 0 and redrawn["casas"] == {} and redrawn["proposta"] is None

    game.post(f"{API}/{duel_id}/propor", json={"token": o, "tipo": "encerrar"})
    ended = game.post(f"{API}/{duel_id}/responder", json={"token": x, "aceita": True}).json()
    assert ended["over"] and ended["vencedor"] == "empate"

    bad = {"token": x, "tipo": "trocar"}
    assert game.post(f"{API}/{duel_id}/propor", json=bad).status_code == 422
