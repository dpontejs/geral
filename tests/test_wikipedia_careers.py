import pytest

from geral.games.wikipedia import Stint, career_rows, parse_career, years

CANO = """{{Infobox football biography
| name = Germán Cano
| youthyears1 = 2004–2007 | youthclubs1 = [[Club Atlético Lanús|Lanús]]
| years1 = 2007–2012 | clubs1 = [[Club Atlético Lanús|Lanús]] | caps1 = 12 | goals1 = 1
| years2 = 2009–2010 | clubs2 = → [[Chacarita Juniors]] (loan)
| years3 = {{0}}2011 | clubs3 = → Deportivo Pereira (loan)
| years4 = 2020–2022 | clubs4 = [[CR Vasco da Gama|Vasco da Gama]]<!-- hidden -->
| years5 = 2022– | clubs5 = [[Fluminense FC|Fluminense]]
| nationalyears1 = 2019 | nationalteam1 = [[Argentina national football team|Argentina]]
}}
'''Germán Ezequiel Cano''' is an Argentine footballer."""


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2007–2012", (2007, 2012)),
        ("2011", (2011, 2011)),
        ("2022–", (2022, None)),
        ("2019–present", (2019, None)),
        ("{{0}}2015–2016", (2015, 2016)),
        ("2014-2015", (2014, 2015)),
        ("1978&ndash;1990", (1978, 1990)),
        ("{{nowrap|1978–1990}}", (1978, 1990)),
        ("", None),
        ("?", None),
    ],
)
def test_years_reads_the_infobox_ranges(text, expected) -> None:
    assert years(text) == expected


def test_parse_career_reads_senior_clubs_and_loans_only() -> None:
    assert parse_career(CANO) == [
        Stint(2007, 2012, "Club Atlético Lanús"),
        Stint(2009, 2010, "Chacarita Juniors"),
        Stint(2011, 2011, "Deportivo Pereira"),
        Stint(2020, 2022, "CR Vasco da Gama"),
        Stint(2022, None, "Fluminense FC"),
    ]


def test_parse_career_without_infobox_is_empty() -> None:
    assert parse_career("'''Someone''' is a footballer.") == []


def test_career_rows_use_the_club_ids_and_report_the_unknown() -> None:
    stints = parse_career(CANO)
    clubs = {
        "Club Atlético Lanús": "Q1",
        "Chacarita Juniors": "Q2",
        "CR Vasco da Gama": "Q5014111",
        "Fluminense FC": "Q217070",
    }
    info = {
        "Q1": {"label": "Lanús", "short": "", "country": "Argentina"},
        "Q2": {"label": "Chacarita", "short": "", "country": "Argentina"},
        "Q5014111": {"label": "Vasco da Gama", "short": "Vasco", "country": "Brasil"},
        "Q217070": {"label": "Fluminense", "short": "", "country": "Brasil"},
    }

    rows, unknown = career_rows("Q3761170", stints, clubs, info, "Atacante")

    assert unknown == ["Deportivo Pereira"]
    assert [(r["club"], r["start"], r["end"]) for r in rows] == [
        ("Q1", "2007", "2012"),
        ("Q2", "2009", "2010"),
        ("Q5014111", "2020", "2022"),
        ("Q217070", "2022", ""),
    ]
    vasco = rows[2]
    assert vasco["player"] == "Q3761170" and vasco["position"] == "Atacante"
    assert (vasco["clubLabel"], vasco["clubShort"], vasco["country"]) == (
        "Vasco da Gama",
        "Vasco",
        "Brasil",
    )
    assert vasco["national"] is False


@pytest.mark.parametrize("path", ["/jogos/onde-jogou", "/jogos/quem-e"])
def test_career_games_credit_wikipedia_and_its_licence(client, path) -> None:
    page = client.get(path).text

    assert 'href="https://en.wikipedia.org/"' in page and "CC BY-SA" in page
    assert 'href="https://www.wikidata.org/"' in page


def test_career_rows_take_hand_made_links_for_pages_without_an_id() -> None:
    stints = [Stint(1992, 1994, "Clube Atlético Bragantino")]

    rows, unknown = career_rows(
        "Q1", stints, {}, {}, "", links={"Clube Atlético Bragantino": "Q541744"}
    )

    assert unknown == [] and rows[0]["club"] == "Q541744"
