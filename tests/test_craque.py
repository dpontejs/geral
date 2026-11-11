from pathlib import Path

import pytest

from geral.games.craque import (
    CRAQUES,
    judge,
    load_lists,
    normalize,
    pool,
    valid_guess,
)

FIXTURES = Path(__file__).parent / "fixtures" / "craques"


@pytest.fixture
def lists():
    return load_lists(FIXTURES)


def named(lists, nome):
    return next(c for team in lists.values() for c in team if c.nome == nome)


def test_normalize_drops_accents_and_case() -> None:
    assert normalize("Nenê") == "NENE" and normalize(" zico ") == "ZICO"


def test_judge_marks_letters_like_wordle(lists) -> None:
    zico = named(lists, "Zico")

    assert judge(zico, ["COCO"]).rows == [["nao", "nao", "certo", "certo"]]
    assert judge(zico, ["OCIZ"]).rows == [["existe", "existe", "existe", "existe"]]


def test_judge_counts_repeated_letters_once(lists) -> None:
    nene = named(lists, "Nenê")  # NENE

    assert judge(nene, ["EEEE"]).rows == [["nao", "certo", "nao", "certo"]]
    assert judge(nene, ["ENNN"]).rows == [["existe", "existe", "certo", "nao"]]


def test_judge_accepts_accents_in_the_guess(lists) -> None:
    assert judge(named(lists, "Nenê"), ["nenê"]).solved


def test_judge_reveals_only_when_over(lists) -> None:
    zico = named(lists, "Zico")

    assert judge(zico, ["COCO"]).reveal is None
    won = judge(zico, ["COCO", "ZICO"])
    lost = judge(zico, ["COCO"] * 6)
    assert won.solved and won.over and won.reveal.completo == "Arthur Antunes Coimbra"
    assert lost.over and not lost.solved and lost.reveal.nome == "Zico"


def test_judge_gives_hints_after_misses(lists) -> None:
    zico = named(lists, "Zico")

    assert judge(zico, ["COCO"] * 2).hints == []
    assert judge(zico, ["COCO"] * 3).hints == ["Posição: Meia"]
    assert judge(zico, ["COCO"] * 4).hints == ["Posição: Meia", "Época: anos 70 e 80"]


def test_valid_guess_needs_the_answer_length_and_letters_only(lists) -> None:
    zico = named(lists, "Zico")

    assert valid_guess(zico, "zicó")
    assert not valid_guess(zico, "ZICOS") and not valid_guess(zico, "Z1CO")
    assert not valid_guess(zico, "ZI O")


def test_team_edition_only_has_its_list(lists) -> None:
    assert {c.nome for c in pool(lists, "vasco", min_list=1)} == {"Dinamite", "Edmundo", "Nenê"}


def test_short_list_is_a_draft_without_its_own_edition(lists) -> None:
    assert pool(lists, "vasco", min_list=4) == []
    assert "Dinamite" in {c.nome for c in pool(lists, "geral")}


def test_geral_mixes_all_lists_without_repeating_a_name(lists) -> None:
    names = [c.nome for c in pool(lists, "geral")]

    assert sorted(names) == ["Dinamite", "Edmundo", "Nenê", "Zico"]


def test_unknown_edition_has_no_pool(lists) -> None:
    assert pool(lists, "xyz") == []


def test_list_with_a_two_word_name_is_rejected(tmp_path) -> None:
    (tmp_path / "x.toml").write_text(
        '[[craque]]\nnome = "Roberto Dinamite"\ncompleto = "a"\nposicao = "b"\nepoca = "c"\n'
        'fato = "d"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Roberto Dinamite"):
        load_lists(tmp_path)


def test_lists_follow_the_rules() -> None:
    lists = load_lists(CRAQUES)  # the real, curated lists

    for slug, craques in lists.items():
        names = [normalize(c.nome) for c in craques]
        assert len(names) == len(set(names)), slug
    editions = [slug for slug in lists if pool(lists, slug)]
    assert len(editions) >= 3, "at least three fanbases with a month of puzzles"
