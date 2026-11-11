import pytest
from test_onde_jogou import OVERRIDES, PLAYERS, ROWS, TEAMS

from geral.games import onde_jogou, quem_e
from geral.games.onde_jogou import Data, convert


@pytest.fixture
def data() -> Data:
    return Data.from_dict(convert(PLAYERS, ROWS, OVERRIDES))


def player(data, nome):
    return next(p for p in data.jogadores if p.nome == nome)


def test_judge_marks_each_guess_and_reveals_only_when_over(data) -> None:
    romario = player(data, "Romário")

    miss = quem_e.judge(data, romario, ["Q2"])
    hit = quem_e.judge(data, romario, ["Q2", "Q1"])
    lost = quem_e.judge(data, romario, ["Q2", "Q3", "Q2b", "Q4", "Q5", "Q6"])

    assert [(r.nome, r.certo) for r in miss.rows] == [("Edmundo", False)]
    assert miss.reveal is None and not miss.over
    assert hit.solved and hit.over and hit.reveal.nome == "Romário"
    assert lost.over and not lost.solved and lost.reveal.posicao == "Atacante"


def test_judge_gives_position_then_initial_after_misses(data) -> None:
    romario = player(data, "Romário")

    assert quem_e.judge(data, romario, ["Q2", "Q3"]).hints == []
    assert quem_e.judge(data, romario, ["Q2", "Q3", "X1"]).hints == ["Posição: Atacante"]
    assert quem_e.judge(data, romario, ["Q2", "Q3", "X1", "X2"]).hints == [
        "Posição: Atacante",
        "Começa com R",
    ]


def test_judge_ignores_a_repeated_guess(data) -> None:
    verdict = quem_e.judge(data, player(data, "Romário"), ["Q2", "Q2", "Q2"])

    assert len(verdict.rows) == 1


def test_quem_e_order_differs_from_onde_jogou(data) -> None:
    who = quem_e.pool(data, "geral", TEAMS)
    where = onde_jogou.pool(data, "geral", TEAMS)

    assert sorted(p.nome for p in who) == sorted(p.nome for p in where)
    assert onde_jogou.pool(data, "geral", TEAMS, game="onde-jogou") == where
