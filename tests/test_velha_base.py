import pytest
from velha_fakes import base, player

from geral.games.velha.base import answers, category, fits

VASCO, GREMIO = "clube:Q5014111", "clube:Q221695"


def test_fits_crosses_club_selecao_copa_country_and_position() -> None:
    b = base(
        player("Q1", clubes=("Q5014111",), selecao=True, posicoes=("atacante",)),
        player("Q2", clubes=("Q221695",), copa=True, paises=("Q77",)),
    )
    vasco, gremio = category(b, VASCO), category(b, GREMIO)
    selecao, copa, uruguai = (category(b, c) for c in ("selecao:BRA", "copa:FIFA", "pais:Q77"))
    atacante = category(b, "posicao:atacante")
    assert fits(b, "Q1", vasco, selecao)
    assert fits(b, "Q1", atacante, vasco)
    assert not fits(b, "Q1", vasco, gremio)
    assert fits(b, "Q2", uruguai, copa)
    assert fits(b, "Q2", gremio, uruguai)
    assert not fits(b, "Q2", selecao, copa)
    assert not fits(b, "Q404", vasco, selecao)


def test_categories_have_pt_br_labels_and_codes() -> None:
    b = base()
    assert category(b, VASCO).label == "Vasco"
    assert category(b, "selecao:BRA").label == "Seleção Brasileira"
    assert category(b, "copa:FIFA").label == "Jogou uma Copa"
    assert category(b, "pais:Q77").label == "Uruguai"
    assert category(b, "posicao:meio-campo").label == "Meio-campo"
    assert category(b, "posicao:goleiro").code == "posicao:goleiro"


def test_player_without_position_or_country_fits_neither() -> None:
    b = base(player("Q1", clubes=("Q5014111",)))
    vasco = category(b, VASCO)
    assert not fits(b, "Q1", vasco, category(b, "posicao:goleiro"))
    assert not fits(b, "Q1", vasco, category(b, "pais:Q77"))


@pytest.mark.parametrize(
    "code", ["clube:Q1", "cor:azul", "selecao:ARG", "copa:", "pais:Q1", "posicao:ponta", "x"]
)
def test_category_rejects_unknown_codes(code) -> None:
    with pytest.raises(ValueError):
        category(base(), code)


def test_answers_come_most_famous_first() -> None:
    b = base(
        player("Q1", "Bebeto", clubes=("Q5014111", "Q17479"), fama=40),
        player("Q2", "Romário", clubes=("Q5014111", "Q17479"), fama=90),
        player("Q3", "Edmundo", clubes=("Q5014111",), fama=50),
    )
    found = answers(b, category(b, VASCO), category(b, "clube:Q17479"))
    assert [p.nome for p in found] == ["Romário", "Bebeto"]
