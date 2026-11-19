import httpx
import pytest
import respx

from geral.specials import sources
from geral.specials.sources import PTWIKI, passages
from geral.teams import get_team

FILLER = " ".join(["palavra"] * 90)
CLUB = f"""Introdução do clube. {FILLER}

== História ==

=== O hexacampeonato ===
Em 1968 o Náutico conquistou o hexa. {FILLER}

=== Curta ===
Só duas linhas.

== Símbolos ==

=== Mascote ===
A escolha do Timbu como mascote ocorreu em 19 de agosto de 1934. {FILLER}

== Títulos ==
Lista de títulos. {FILLER}
"""
CLASSIC = f"""Clássico. {FILLER}

== Outros jogos históricos ==
Em 14 de junho de 1947, o Náutico venceu o Sport por 7 a 3. {FILLER}

== Estatísticas ==
Números. {FILLER}
"""
BITA = f"""Bita é o maior ídolo da história do Náutico. {FILLER}

== Carreira ==
Marcou 221 gols pelo Timbu. {FILLER}

== Títulos ==
Vários. {FILLER}
"""
GARRINCHA = f"""Garrincha foi ídolo do Botafogo. {FILLER} Jogou um amistoso contra o Náutico.

== Carreira ==
Driblou muito. {FILLER}
"""
PAGES = {
    "Clube Náutico Capibaribe": CLUB,
    "Clássico dos Clássicos": CLASSIC,
    "Clássico das Emoções (Pernambuco)": "",
    "Bita": BITA,
    "Garrincha": GARRINCHA,
}


def wiki(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    if params.get("list") == "search":
        assert params["srsearch"] == '"ídolo" linksto:"Clube Náutico Capibaribe"'
        return httpx.Response(
            200, json={"query": {"search": [{"title": "Bita"}, {"title": "Garrincha"}]}}
        )
    title = params["titles"]
    return httpx.Response(
        200, json={"query": {"pages": [{"title": title, "extract": PAGES[title]}]}}
    )


@pytest.fixture
def found(monkeypatch):
    monkeypatch.setattr(sources.mediawiki.time, "sleep", lambda s: None)
    with respx.mock:
        respx.get(PTWIKI).mock(side_effect=wiki)
        with httpx.Client() as client:
            yield passages(client, get_team("nautico"))


def test_club_sections_become_clube_passages(found) -> None:
    [mascot] = [p for p in found if p.kind == "clube"]

    assert mascot.title == "Clube Náutico Capibaribe — Mascote"
    assert (
        mascot.key == "https://pt.wikipedia.org/wiki/Clube_N%C3%A1utico_Capibaribe#Símbolos/Mascote"
    )
    assert "19 de agosto de 1934" in mascot.text


def test_history_subsections_become_jogo_passages(found) -> None:
    games = {p.title: p for p in found if p.kind == "jogo"}

    assert set(games) == {
        "Clube Náutico Capibaribe — O hexacampeonato",
        "Clássico dos Clássicos — Outros jogos históricos",
    }
    assert "7 a 3" in games["Clássico dos Clássicos — Outros jogos históricos"].text


def test_idol_needs_idolo_near_the_club_name(found) -> None:
    [idol] = [p for p in found if p.kind == "idolo"]

    assert idol.title == "Bita"
    assert "221 gols" in idol.text and "Vários" not in idol.text  # intro + Carreira only


def test_short_passages_are_skipped(found) -> None:
    assert not any("Curta" in p.title for p in found)
    assert all(len(p.text.split()) >= 80 for p in found)


def test_level_4_headings_stay_inside_their_section() -> None:
    text = (
        "Intro.\n\n== História ==\n\n=== Anos 60 ===\nA.\n\n"
        "==== O hexa ====\nB.\n\n== Títulos ==\nC."
    )

    parts = sources.sections(text)

    assert [(s.h2, s.h3) for s in parts] == [
        ("", None),
        ("História", None),
        ("História", "Anos 60"),
        ("Títulos", None),
    ]
    assert "B." in parts[2].text


def test_keys_carry_both_heading_levels() -> None:
    text = (
        f"== História ==\n\n=== Torcida ===\n{FILLER}\n\n"
        f"== Símbolos ==\n\n=== Torcida ===\n{FILLER}"
    )

    keys = {p.key for p in sources._club("ABC Futebol Clube", text)}

    assert len(keys) == 2


def test_idol_passage_must_name_the_club_after_the_cut() -> None:
    career = " ".join(["Brilhou no Botafogo, alvinegro carioca."] * 120)
    text = f"Ídolo do Botafogo e do ABC. {FILLER}\n\n== Carreira ==\n{career} Encerrou no ABC."

    assert sources._idol("Fulano", text, ("ABC",)) is not None  # the intro names the club
    assert sources._idol("Fulano", text.replace("e do ABC", ""), ("ABC",)) is None


def test_a_subsection_under_a_club_section_is_a_clube_passage() -> None:
    text = f"== Sedes e estádios ==\n\n=== O Mutange ===\n{FILLER}"

    [p] = sources._club("Centro Sportivo Alagoano", text)

    assert (p.kind, p.title) == ("clube", "Centro Sportivo Alagoano — O Mutange")


def test_curiosities_are_clube_passages() -> None:
    text = f"== Curiosidades ==\n\n=== Fernando Collor de Mello ===\n{FILLER}"

    [p] = sources._club("Centro Sportivo Alagoano", text)

    assert p.kind == "clube" and p.title.endswith("Fernando Collor de Mello")


def test_other_sections_stay_out() -> None:
    text = f"== Títulos ==\n{FILLER}\n\n== Elenco atual ==\n\n=== Goleiros ===\n{FILLER}"

    assert sources._club("Centro Sportivo Alagoano", text) == []
