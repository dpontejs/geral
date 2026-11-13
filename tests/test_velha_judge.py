import pytest
from velha_fakes import CLUBS, base, player

from geral.games.velha.base import category
from geral.games.velha.board import Board
from geral.games.velha.judge import MAX_GUESSES, Guess, GuessError, judge_solo

ROWS = sorted(CLUBS)  # Flamengo, Grêmio, Vasco ids
COLS = ("selecao", "copa", "atacante")


def _cell_players(casa: int) -> list:
    club, col = ROWS[casa // 3], COLS[casa % 3]
    return [
        player(
            f"Q{casa}{k}",
            f"Jogador {casa}{k}",
            clubes=(club,),
            selecao=col == "selecao",
            copa=col == "copa",
            posicoes=("atacante",) if col == "atacante" else (),
            fama=10 * k,
        )
        for k in range(4)
    ]


B = base(*(p for casa in range(9) for p in _cell_players(casa)))
BOARD = Board(
    tuple(category(B, f"clube:{q}") for q in ROWS),
    tuple(category(B, c) for c in ("selecao:BRA", "copa:FIFA", "posicao:atacante")),
)


def g(casa: int, jogador: str) -> Guess:
    return Guess(casa=casa, jogador=jogador)


def test_solo_judge_fills_cells_counts_misses_and_reveals_only_at_the_end() -> None:
    chutes = [g(0, "Q00"), g(1, "Q20"), g(1, "Q10")]  # Q20 is from another row
    verdict = judge_solo(B, BOARD, chutes)
    assert verdict.casas == {0: "Q00", 1: "Q10"}
    assert verdict.acertos == [True, False, True]
    assert not verdict.over
    assert verdict.revelacao is None

    full = [g(casa, f"Q{casa}0") for casa in range(9)]
    verdict = judge_solo(B, BOARD, full)
    assert verdict.over
    assert verdict.acertos == [True] * 9
    assert verdict.revelacao is not None
    cell4 = verdict.revelacao[4]
    assert [a.id for a in cell4.top] == ["Q43", "Q42", "Q41"]
    assert cell4.top[0].nome == "Jogador 43"
    assert cell4.total == 4


def test_solo_reusing_a_player_is_a_miss() -> None:
    reused = player("Q99", clubes=tuple(ROWS), selecao=True, copa=True)
    b = base(*B.players.values(), reused)
    verdict = judge_solo(b, BOARD, [g(0, "Q99"), g(1, "Q99")])
    assert verdict.casas == {0: "Q99"}
    assert verdict.acertos == [True, False]


def test_solo_twelve_guesses_end_the_game() -> None:
    misses = [g(0, "Q10")] * (MAX_GUESSES - 1)
    assert not judge_solo(B, BOARD, misses).over
    verdict = judge_solo(B, BOARD, [*misses, g(0, "Q00")])
    assert verdict.over
    assert verdict.acertos[-1] is True
    assert verdict.revelacao is not None


def test_solo_twelfth_guess_filling_the_ninth_cell_is_a_hit() -> None:
    chutes = [g(0, "Q10")] * 3 + [g(casa, f"Q{casa}0") for casa in range(9)]
    verdict = judge_solo(B, BOARD, chutes)
    assert len(chutes) == MAX_GUESSES
    assert verdict.over and len(verdict.casas) == 9
    assert verdict.acertos == [False] * 3 + [True] * 9


@pytest.mark.parametrize(
    "chutes",
    [
        [g(0, "Q00"), g(0, "Q01")],  # cell already taken
        [g(9, "Q00")],
        [g(-1, "Q00")],
        [g(0, "Q404")],  # not in the base
        [g(casa, f"Q{casa}0") for casa in range(9)] + [g(0, "Q01")],  # after the end
        [g(0, "Q10")] * (MAX_GUESSES + 1),
    ],
)
def test_solo_rejects_taken_cell_bad_cell_unknown_player_and_guess_after_the_end(chutes) -> None:
    with pytest.raises(GuessError):
        judge_solo(B, BOARD, chutes)
