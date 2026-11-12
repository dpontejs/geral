import json

from geral.games import calendario
from geral.games.daily import pick, shuffled


def ordered(ids: list[str]) -> list[str]:
    return shuffled(sorted(ids), "quem-e:geral")


def test_frozen_numbers_keep_their_answer_when_the_pool_changes() -> None:
    before = ordered([f"Q{i}" for i in range(1, 11)])
    frozen = [pick(before, n) for n in (1, 2, 3)]
    after = ordered([f"Q{i}" for i in range(1, 13)])  # two players added: a new shuffle

    picks = [calendario.pick(after, n, frozen, key=str) for n in (1, 2, 3, 4)]

    assert picks[:3] == frozen
    assert picks[3] == pick(after, 4)


def test_a_frozen_answer_no_longer_in_the_pool_falls_back_to_the_order() -> None:
    order = ordered(["Q1", "Q2", "Q3"])

    assert calendario.pick(order, 1, ["Q99"], key=str) == pick(order, 1)


def test_freeze_extends_but_never_rewrites_the_past(tmp_path) -> None:
    path = tmp_path / "calendario.json"
    path.write_text(json.dumps({"quem-e": {"geral": ["Q7"]}}))

    calendario.freeze(path, "quem-e", "geral", ["Q1", "Q2", "Q3"])
    calendario.freeze(path, "quem-e", "vasco", ["Q5"])

    assert calendario.load(path) == {"quem-e": {"geral": ["Q7", "Q2", "Q3"], "vasco": ["Q5"]}}


def test_missing_calendar_is_empty(tmp_path) -> None:
    assert calendario.load(tmp_path / "nada.json") == {}
    assert calendario.answers({}, "quem-e", "geral") == []


def test_freeze_games_records_today_for_every_game_and_edition(tmp_path) -> None:
    from test_onde_jogou import OVERRIDES, PLAYERS, ROWS, TEAMS

    from geral.games import onde_jogou, quem_e
    from geral.games.onde_jogou import Data, convert

    data = Data.from_dict(convert(PLAYERS, ROWS, OVERRIDES))
    path = tmp_path / "calendario.json"

    calendario.freeze_games(path, data, TEAMS, until=3)

    frozen = calendario.load(path)
    for game, pool in (("onde-jogou", onde_jogou.pool), ("quem-e", quem_e.pool)):
        players = pool(data, "geral", TEAMS)
        assert frozen[game]["geral"] == [pick(players, n).wikidata for n in (1, 2, 3)]
        for slug in TEAMS:
            if pool(data, slug, TEAMS):
                assert len(frozen[game][slug]) == 3
