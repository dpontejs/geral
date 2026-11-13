import httpx
import pytest
import respx

from geral.games import ptwiki
from geral.games.wikipedia import Stint

ALBERI = """{{Info/Futebolista
|nome              = Alberi
|nomecompleto      = Alberi José Ferreira de Matos
|posição           = [[Atacante (futebol)|atacante]]<ref>fonte</ref>
|jovemanos         = 1963
|jovemclubes       = [[Santa Cruz Futebol Clube|Santa Cruz]]
|ano               = 1968<br />1968–1975<br />1974<br />1981–1984
|clubes            = [[Santa Cruz Futebol Clube|Santa Cruz]]<br /> {{Futebol ABC}}<br />
 {{seta fut}} [[Atlético Rio Negro Clube (Manaus)|Rio Negro]] {{emp fut}}<br /> {{Futebol ABC}}
|anoselecao        = 1973
|selecaonacional   = [[Seleção Brasileira de Futebol|Brasil]]
}}
'''Alberi José Ferreira de Matos''' foi um futebolista."""

EXPANDED = (
    "[[Santa Cruz Futebol Clube|Santa Cruz]]<br /> [[ABC Futebol Clube|ABC]]<br />\n"
    " → [[Atlético Rio Negro Clube (Manaus)|Rio Negro]] ([[Empréstimo (esportes)|emp.]])"
    "<br /> [[ABC Futebol Clube|ABC]]"
)


def test_infobox_reads_the_first_info_template() -> None:
    params = ptwiki.infobox(ALBERI)
    assert params["nome"] == "Alberi"
    assert "{{Futebol ABC}}" in params["clubes"]


def test_infobox_reads_a_coach_infobox_too() -> None:
    text = "{{Info/Treinador\n|nome = Fulano\n|ano = 2001\n|clubes = [[ABC Futebol Clube|ABC]]\n}}"
    assert ptwiki.infobox(text)["clubes"] == "[[ABC Futebol Clube|ABC]]"


def test_infobox_is_empty_without_one() -> None:
    assert ptwiki.infobox("'''Fulano''' foi um futebolista.") == {}


def test_parse_career_pairs_years_and_clubs_line_by_line_loans_included() -> None:
    assert ptwiki.parse_career("1968<br />1968–1975<br />1974<br />1981–1984", EXPANDED) == [
        Stint(1968, 1968, "Santa Cruz Futebol Clube"),
        Stint(1968, 1975, "ABC Futebol Clube"),
        Stint(1974, 1974, "Atlético Rio Negro Clube (Manaus)"),
        Stint(1981, 1984, "ABC Futebol Clube"),
    ]


def test_parse_career_reads_open_ended_and_unlinked_clubs() -> None:
    assert ptwiki.parse_career(
        "2016–2018<br/>2025–", "Santa Cruz-SGA<br>[[ABC Futebol Clube|ABC]]"
    ) == [
        Stint(2016, 2018, "Santa Cruz-SGA"),
        Stint(2025, None, "ABC Futebol Clube"),
    ]


def test_parse_career_refuses_years_and_clubs_that_do_not_pair_up() -> None:
    assert ptwiki.parse_career("2005<br />2006<br />2007", "[[A]]<br />[[B]]") is None
    assert ptwiki.parse_career("", "") is None


def test_shown_names_keep_the_text_the_article_shows() -> None:
    assert ptwiki.shown_names(EXPANDED) == {
        "Santa Cruz Futebol Clube": "Santa Cruz",
        "ABC Futebol Clube": "ABC",
        "Atlético Rio Negro Clube (Manaus)": "Rio Negro",
    }


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("[[Atacante (futebol)|atacante]]<ref>fonte</ref>", "Atacante"),
        ("lateral-esquerdo", "Lateral-esquerdo"),
        ("Ex-atacante", "Atacante"),  # a retired player's article; the game is about the career
        ("ex-lateral-direito", "Lateral-direito"),
        ("Goleiro<br /> treinador", "Goleiro"),  # the coach years are not a position
        ("Treinador<br />", ""),
        ("[[Auxiliar técnico]] e [[atacante]]", "Atacante"),
        ("Técnico (ex-zagueiro)", "Zagueiro"),
        ("[[Treinador]] (ex [[meio-campista]])", "Meio-campista"),
        (
            "ex-[[Treinador de futebol|Treinador]]<br />(ex-[[Volante (futebol)|Volante]])",
            "Volante",
        ),
        ("Volante, lateral, meia", "Volante, lateral e meia"),
        ("zagueiro / treinador", "Zagueiro"),
        ("treinador, ex-atacante e volante", "Atacante e volante"),
        ("[[Goleiro]] e [[treinador]]", "Goleiro"),
        ("", ""),
    ],
)
def test_position_is_the_shown_text_capitalized(raw, shown) -> None:
    assert ptwiki.position(raw) == shown


def test_build_writes_the_careers_file_for_the_players_edition() -> None:
    players = [{"pagina": "Alberi", "nome": "Alberi", "edicao": "abc"}]
    pages = {"Alberi": {"qid": "Q9", "text": ALBERI, "clubes": EXPANDED}}
    clubs = {
        "Santa Cruz Futebol Clube": "Q508440",
        "ABC Futebol Clube": "Q1",
        "Atlético Rio Negro Clube (Manaus)": "Q2",
    }
    info = {
        "Q508440": {"label": "Santa Cruz Futebol Clube", "country": "Brasil"},
        "Q1": {"label": "ABC Futebol Clube", "country": "Brasil"},
        "Q2": {"label": "Atlético Rio Negro Clube", "country": "Brasil"},
    }
    careers, report = ptwiki.build(players, pages, clubs, info, fixes={})
    assert report == []
    [alberi] = careers["jogadores"]
    assert alberi["wikidata"] == "Q9"
    assert alberi["nome"] == "Alberi"
    assert alberi["posicao"] == "Atacante"
    assert alberi["edicoes"] == ["abc"]
    assert [(s["clube"], s["inicio"], s["fim"]) for s in alberi["clubes"]] == [
        ("Q508440", 1968, 1968),
        ("Q1", 1968, 1975),
        ("Q2", 1974, 1974),
        ("Q1", 1981, 1984),
    ]
    assert careers["clubes"]["Q2"]["nome"] == "Rio Negro"
    assert "Atlético Rio Negro Clube" in careers["clubes"]["Q2"]["apelidos"]


def test_build_reports_and_leaves_out_what_it_cannot_read() -> None:
    players = [
        {"pagina": "Sem Quadro", "nome": "Sem Quadro", "edicao": "abc"},
        {"pagina": "Desencontrado", "nome": "Desencontrado", "edicao": "abc"},
        {"pagina": "Sumido", "nome": "Sumido", "edicao": "abc"},
    ]
    pages = {
        "Sem Quadro": {"qid": "Q7", "text": "nada", "clubes": ""},
        "Desencontrado": {
            "qid": "Q8",
            "text": "{{Info/Futebolista\n|ano = 2001<br />2002\n|clubes = [[A]]\n}}",
            "clubes": "[[A]]",
        },
    }
    careers, report = ptwiki.build(players, pages, {}, {}, fixes={})
    assert careers["jogadores"] == []
    assert report == [
        "Sem Quadro: sem quadro de carreira",
        "Desencontrado: anos e clubes não batem",
        "Sumido: página não encontrada",
    ]


def test_build_reports_clubs_without_a_wikidata_id() -> None:
    players = [{"pagina": "Alberi", "nome": "Alberi", "edicao": "abc"}]
    pages = {"Alberi": {"qid": "Q9", "text": ALBERI, "clubes": EXPANDED}}
    clubs = {"ABC Futebol Clube": "Q1"}
    info = {"Q1": {"label": "ABC Futebol Clube", "country": "Brasil"}}
    careers, report = ptwiki.build(players, pages, clubs, info, fixes={})
    assert [s["clube"] for s in careers["jogadores"][0]["clubes"]] == ["Q1"]
    assert report == [
        "Alberi: clube sem Wikidata: Santa Cruz Futebol Clube",
        "Alberi: clube sem Wikidata: Atlético Rio Negro Clube (Manaus)",
    ]


@respx.mock
def test_fetch_pages_reads_wikitext_and_wikidata_id_following_redirects() -> None:
    respx.get(ptwiki.API).respond(
        json={
            "query": {
                "redirects": [{"from": "Marinho", "to": "Marinho Chagas"}],
                "pages": [
                    {
                        "title": "Marinho Chagas",
                        "pageprops": {"wikibase_item": "Q929290"},
                        "revisions": [{"slots": {"main": {"content": "{{Info/Futebolista}}"}}}],
                    },
                    {"title": "Sumido", "missing": True},
                ],
            }
        }
    )
    with httpx.Client() as client:
        pages = ptwiki.fetch_pages(client, ["Marinho", "Sumido"], pause=0)
    assert pages == {"Marinho": {"qid": "Q929290", "text": "{{Info/Futebolista}}"}}


@respx.mock
def test_expand_turns_club_templates_into_links() -> None:
    route = respx.post(ptwiki.API).respond(
        json={"expandtemplates": {"wikitext": "[[ABC Futebol Clube|ABC]]"}}
    )
    with httpx.Client() as client:
        assert ptwiki.expand(client, "{{Futebol ABC}}", pause=0) == "[[ABC Futebol Clube|ABC]]"
        assert ptwiki.expand(client, "[[Alecrim Futebol Clube|Alecrim]]", pause=0) == (
            "[[Alecrim Futebol Clube|Alecrim]]"
        )
    assert route.call_count == 1  # nothing to expand: no call


@respx.mock
def test_page_ids_map_titles_and_redirects_to_wikidata() -> None:
    respx.get(ptwiki.API).respond(
        json={
            "query": {
                "redirects": [{"from": "ABC FC", "to": "ABC Futebol Clube"}],
                "pages": [
                    {"title": "ABC Futebol Clube", "pageprops": {"wikibase_item": "Q1"}},
                    {"title": "Clube Sem Item"},
                ],
            }
        }
    )
    with httpx.Client() as client:
        ids = ptwiki.page_ids(client, ["ABC FC", "ABC Futebol Clube", "Clube Sem Item"], pause=0)
    assert ids == {"ABC FC": "Q1", "ABC Futebol Clube": "Q1"}


@respx.mock
def test_club_info_reads_the_portuguese_label_and_country() -> None:
    respx.get(ptwiki.WIKIDATA, params={"ids": "Q1"}).respond(
        json={
            "entities": {
                "Q1": {
                    "labels": {"pt-br": {"value": "ABC Futebol Clube"}},
                    "claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q155"}}}}]},
                }
            }
        }
    )
    respx.get(ptwiki.WIKIDATA, params={"ids": "Q155"}).respond(
        json={"entities": {"Q155": {"labels": {"pt": {"value": "Brasil"}}, "claims": {}}}}
    )
    with httpx.Client() as client:
        info = ptwiki.club_info(client, ["Q1"], pause=0)
    assert info == {"Q1": {"label": "ABC Futebol Clube", "country": "Brasil"}}


@respx.mock
def test_requests_wait_and_retry_when_wikimedia_says_too_many(monkeypatch) -> None:
    waits = []
    monkeypatch.setattr(ptwiki.time, "sleep", waits.append)
    respx.post(ptwiki.API).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"expandtemplates": {"wikitext": "[[ABC]]"}}),
        ]
    )
    with httpx.Client() as client:
        assert ptwiki.expand(client, "{{Futebol ABC}}", pause=0) == "[[ABC]]"
    assert 7 in waits


@respx.mock
def test_expand_many_sends_several_texts_in_one_call() -> None:
    def answer(request):
        text = dict(httpx.QueryParams(request.content.decode()))["text"]
        return httpx.Response(
            200, json={"expandtemplates": {"wikitext": text.replace("{{Futebol ABC}}", "[[ABC]]")}}
        )

    route = respx.post(ptwiki.API).mock(side_effect=answer)
    texts = ["{{Futebol ABC}}", "[[Alecrim]]", "", "{{Futebol ABC}}<br />[[X]]"]
    with httpx.Client() as client:
        assert ptwiki.expand_many(client, texts, pause=0) == [
            "[[ABC]]",
            "[[Alecrim]]",
            "",
            "[[ABC]]<br />[[X]]",
        ]
    assert route.call_count == 1


def test_build_names_a_club_in_full_when_its_short_name_is_taken() -> None:
    text = "{{Info/Futebolista\n|ano = 2001<br />2002<br />2003\n|clubes = x\n}}"
    clubes = "[[Nacional A|Nacional]]<br />[[Nacional B|Nacional]]<br />[[Vasco PT|Vasco]]"
    players = [{"pagina": "P", "nome": "P", "edicao": "abc"}]
    pages = {"P": {"qid": "Q9", "text": text, "clubes": clubes}}
    clubs = {"Nacional A": "Q1", "Nacional B": "Q2", "Vasco PT": "Q3"}
    info = {
        "Q1": {"label": "Clube Desportivo Nacional", "country": "Portugal"},
        "Q2": {"label": "Club Nacional de Football", "country": "Uruguai"},
        "Q3": {"label": "Vasco Esporte Clube", "country": "Brasil"},
    }
    careers, _ = ptwiki.build(players, pages, clubs, info, fixes={}, taken={"Q100": "Vasco"})
    names = {qid: c["nome"] for qid, c in careers["clubes"].items()}
    assert names == {
        "Q1": "Nacional",  # same number of players: the lowest id keeps the short name
        "Q2": "Club Nacional de Football",
        "Q3": "Vasco Esporte Clube",  # the main file's Vasco keeps "Vasco"
    }
    assert "Nacional" in careers["clubes"]["Q2"]["apelidos"]


def test_build_leaves_clubs_of_the_main_file_to_it() -> None:
    text = "{{Info/Futebolista\n|ano = 2001<br />2002\n|clubes = x\n}}"
    players = [{"pagina": "P", "nome": "P", "edicao": "abc"}]
    pages = {"P": {"qid": "Q9", "text": text, "clubes": "[[Rayo|Rayo]]<br />[[ABC|ABC]]"}}
    clubs = {"Rayo": "Q1", "ABC": "Q2"}
    info = {"Q1": {"label": "Rayo Vallecano", "country": "Espanha"}, "Q2": {"label": "ABC"}}
    careers, _ = ptwiki.build(players, pages, clubs, info, fixes={}, taken={"Q1": "Rayo Vallecano"})
    assert careers["clubes"]["Q1"]["nome"] == "Rayo"  # the main file's name wins when merged


@respx.mock
def test_page_ids_skip_disambiguation_pages() -> None:
    respx.get(ptwiki.API).respond(
        json={
            "query": {
                "pages": [
                    {
                        "title": "Bela Vista Futebol Clube",
                        "pageprops": {"wikibase_item": "Q9653018", "disambiguation": ""},
                    }
                ]
            }
        }
    )
    with httpx.Client() as client:
        assert ptwiki.page_ids(client, ["Bela Vista Futebol Clube"], pause=0) == {}


def test_parse_career_does_not_take_the_loan_mark_for_a_club() -> None:
    clubes = "[[ABC Futebol Clube|ABC]]<br />→ Potiguar de Mossoró ([[Empréstimo (esportes)|emp.]])"
    assert ptwiki.parse_career("2010<br />2011", clubes) == [
        Stint(2010, 2010, "ABC Futebol Clube"),
        Stint(2011, 2011, "Potiguar de Mossoró"),
    ]
    assert ptwiki.shown_names(clubes) == {"ABC Futebol Clube": "ABC"}


def test_build_puts_a_player_listed_twice_in_both_editions() -> None:
    players = [
        {"pagina": "Alberi", "nome": "Alberi", "edicao": "abc"},
        {"pagina": "Alberi", "nome": "Alberi", "edicao": "nautico"},
    ]
    pages = {"Alberi": {"qid": "Q9", "text": ALBERI, "clubes": EXPANDED}}
    clubs = {"ABC Futebol Clube": "Q1", "Santa Cruz Futebol Clube": "Q2"}
    info = {"Q1": {"label": "ABC Futebol Clube"}, "Q2": {"label": "Santa Cruz Futebol Clube"}}
    careers, _ = ptwiki.build(players, pages, clubs, info, fixes={})
    [alberi] = careers["jogadores"]
    assert alberi["edicoes"] == ["abc", "nautico"]


@respx.mock
def test_category_members_follow_continue() -> None:
    respx.get(ptwiki.API).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "continue": {"cmcontinue": "page|X", "continue": "-||"},
                    "query": {"categorymembers": [{"title": "Kuki"}]},
                },
            ),
            httpx.Response(200, json={"query": {"categorymembers": [{"title": "Lopeu"}]}}),
        ]
    )
    with httpx.Client() as client:
        assert ptwiki.category_members(client, "Futebolistas do Náutico", pause=0) == [
            "Kuki",
            "Lopeu",
        ]


def test_plain_keeps_the_shown_text_only() -> None:
    assert ptwiki.plain("[[Kuki (futebolista)|Kuki]]<ref>x</ref> e ''Treinador''") == (
        "Kuki e Treinador"
    )


def test_requests_say_who_we_are_as_wikimedia_asks() -> None:
    # https://meta.wikimedia.org/wiki/User-Agent_policy: a name and a way to reach the operator
    assert "https://github.com/dpontejs/geral" in ptwiki.HEADERS["User-Agent"]


def test_build_adds_the_country_when_the_full_name_is_taken_too() -> None:
    text = "{{Info/Futebolista\n|ano = 2001<br />2002<br />2003\n|clubes = x\n}}"
    clubes = "[[A|Athletic]]<br />[[B|Athletic]]<br />[[C|Athletic]]"
    players = [{"pagina": "P", "nome": "P", "edicao": "abc"}]
    pages = {"P": {"qid": "Q9", "text": text, "clubes": clubes}}
    clubs = {"A": "Q1", "B": "Q2", "C": "Q3"}
    info = {
        "Q1": {"label": "Athletic Club", "country": "Espanha"},
        "Q2": {"label": "Athletic Club", "country": "Brasil"},
        "Q3": {"label": "Athletic Club", "country": "Estados Unidos"},
    }
    careers, _ = ptwiki.build(players, pages, clubs, info, fixes={})
    assert {q: c["nome"] for q, c in careers["clubes"].items()} == {
        "Q1": "Athletic",
        "Q2": "Athletic Club (Brasil)",
        "Q3": "Athletic Club (Estados Unidos)",
    }


def test_build_lets_the_club_with_more_players_keep_a_shared_short_name() -> None:
    text = "{{Info/Futebolista\n|ano = 2001\n|clubes = x\n}}"
    players = [{"pagina": p, "nome": p, "edicao": "abc"} for p in ("A", "B", "C")]
    pages = {
        "A": {"qid": "Q91", "text": text, "clubes": "[[Peñarol U|Peñarol]]"},
        "B": {"qid": "Q92", "text": text, "clubes": "[[Peñarol U|Peñarol]]"},
        "C": {"qid": "Q93", "text": text, "clubes": "[[Penarol AM|Penarol]]"},
    }
    clubs = {"Peñarol U": "Q1", "Penarol AM": "Q2"}
    info = {
        "Q1": {"label": "Club Atlético Peñarol", "country": "Uruguai"},
        "Q2": {"label": "Penarol Atlético Clube", "country": "Brasil"},
    }
    careers, _ = ptwiki.build(players, pages, clubs, info, fixes={})
    assert careers["clubes"]["Q1"]["nome"] == "Peñarol"
    assert careers["clubes"]["Q2"]["nome"] == "Penarol Atlético Clube"
