import pytest

from geral.games.onde_jogou import Data, convert, judge, pool, resolve, team_clubs

PLAYERS = [
    {"nome": "Romário", "wikidata": "Q1"},
    {"nome": "Edmundo", "wikidata": "Q2"},
    {"nome": "Revelação", "wikidata": "Q3"},
]


def row(player, club, label, start="", end="", national=False, short="", position="atacante"):
    return {
        "player": player,
        "club": club,
        "clubLabel": label,
        "clubShort": short,
        "start": start,
        "end": end,
        "national": national,
        "position": position,
    }


ROWS = [
    row("Q1", "Q100", "Club de Regatas Vasco da Gama", "1985", "1988", short="Vasco"),
    row("Q1", "Q900", "Seleção Brasileira de Futebol", "1987", "2005"),
    row("Q1", "Q901", "Seleção Brasileira Sub-20", "1987", "1987", national=True),
    row("Q1", "Q101", "PSV Eindhoven", "1988", "1993"),
    row("Q1", "Q102", "Amsterdamsche Football Club Ajax"),  # no year: dropped
    row("Q1", "Q103", "Clube de Regatas do Flamengo", "1995", "1996", short="Flamengo"),
    row("Q1", "Q103", "Clube de Regatas do Flamengo", "1997", "1997", short="Flamengo"),
    row("Q1", "Q104", "Valencia Club de Fútbol", "1996", "1997"),
    row("Q1", "Q100", "Club de Regatas Vasco da Gama", "2000", "2002", short="Vasco"),
    row("Q2", "Q100", "Club de Regatas Vasco da Gama", "1990", "1992", short="Vasco"),
    row("Q2", "Q100", "Club de Regatas Vasco da Gama", "1992", "1992", short="Vasco"),
    row("Q2", "Q105", "Sociedade Esportiva Palmeiras", "1993", "1995", short="Palmeiras"),
    row("Q2", "Q103", "Clube de Regatas do Flamengo", "1995", "1995", short="Flamengo"),
    row("Q2", "Q107", "Sport Club Corinthians Paulista", "1996", "1996", short="Corinthians"),
    row("Q2", "Q108", "ACF Fiorentina", "1997", "1999"),
    row("Q3", "Q100", "Club de Regatas Vasco da Gama", "2020", "", short="Vasco"),
    row("Q3", "Q106", "Vasco da Gama B", "2019", "2020"),
]
OVERRIDES = {"Q101": {"nome": "PSV", "apelidos": ["PSV Eindhoven"]}}
TEAMS = {"vasco": "Vasco", "palmeiras": "Palmeiras", "abc": "ABC"}  # slug -> teams.toml name


@pytest.fixture
def data() -> Data:
    return Data.from_dict(convert(PLAYERS, ROWS, OVERRIDES))


def player(data, nome):
    return next(p for p in data.jogadores if p.nome == nome)


def test_convert_drops_national_and_youth_teams(data) -> None:
    clubs = {s.clube for s in player(data, "Romário").clubes}

    assert "Q900" not in clubs and "Q901" not in clubs
    assert "Q106" not in {s.clube for s in player(data, "Revelação").clubes}


def test_convert_drops_stints_without_a_start_year(data) -> None:
    assert "Q102" not in {s.clube for s in player(data, "Romário").clubes}


def test_convert_merges_back_to_back_stints(data) -> None:
    edmundo = player(data, "Edmundo")

    assert [(s.clube, s.inicio, s.fim) for s in edmundo.clubes] == [
        ("Q100", 1990, 1992),
        ("Q105", 1993, 1995),
        ("Q103", 1995, 1995),
        ("Q107", 1996, 1996),
        ("Q108", 1997, 1999),
    ]


def test_convert_keeps_stints_in_order_and_open_ended_careers(data) -> None:
    romario = player(data, "Romário")

    assert [s.inicio for s in romario.clubes] == [1985, 1988, 1995, 1996, 1997, 2000]
    assert player(data, "Revelação").clubes[0].fim is None
    assert romario.posicao == "Atacante"


def test_convert_names_clubs_short_with_overrides_first(data) -> None:
    assert data.clubes["Q100"].nome == "Vasco"
    assert data.clubes["Q101"].nome == "PSV"
    assert data.clubes["Q104"].nome == "Valencia Club de Fútbol"


def test_resolve_accepts_short_names_and_accents(data) -> None:
    assert resolve(data, "vasco") == "Q100"
    assert resolve(data, "  Club de Regatas Vasco da Gama ") == "Q100"
    assert resolve(data, "psv eindhoven") == "Q101"
    assert resolve(data, "valência club de futbol") == "Q104"
    assert resolve(data, "Ajax") is None


def test_judge_lights_every_stint_of_a_found_club(data) -> None:
    verdict = judge(data, player(data, "Romário"), ["Q103"], desistiu=False)

    assert [s.clube for s in verdict.slots] == [None, None, "Flamengo", None, "Flamengo", None]
    assert verdict.achados == 1 and verdict.total == 4 and not verdict.over


def test_judge_ends_after_three_wrong_clubs_or_giving_up_and_reveals(data) -> None:
    romario = player(data, "Romário")

    lost = judge(data, romario, ["Q100", "Q105", "Q107", "Q108"], desistiu=False)
    gave_up = judge(data, romario, ["Q100"], desistiu=True)
    won = judge(data, romario, ["Q100", "Q101", "Q103", "Q104"], desistiu=False)

    assert lost.over and lost.erros == ["Palmeiras", "Corinthians", "ACF Fiorentina"]
    assert all(s.clube for s in lost.slots)  # revealed
    assert gave_up.over and not gave_up.solved
    assert won.over and won.solved and won.achados == 4


def test_judge_ignores_a_repeated_guess(data) -> None:
    verdict = judge(data, player(data, "Romário"), ["Q105", "Q105", "Q105"], desistiu=False)

    assert verdict.erros == ["Palmeiras"] and not verdict.over


def test_team_edition_has_only_players_who_played_there(data) -> None:
    assert {p.nome for p in pool(data, "palmeiras", TEAMS)} == {"Edmundo"}
    assert pool(data, "abc", TEAMS) == []


def test_geral_needs_three_clubs(data) -> None:
    assert {p.nome for p in pool(data, "geral", TEAMS)} == {"Romário", "Edmundo"}


def test_convert_skips_clubs_marked_to_ignore() -> None:
    fixes = {"Q101": {"ignorar": True}}

    data = Data.from_dict(convert(PLAYERS, ROWS, fixes))

    assert "Q101" not in data.clubes
    assert "Q101" not in {s.clube for s in player(data, "Romário").clubes}


def test_real_careers_are_sane() -> None:
    from geral.games.onde_jogou import load

    real = load()
    for jogador in real.jogadores:
        starts = [s.inicio for s in jogador.clubes]
        assert starts == sorted(starts), jogador.nome
        assert all(s.clube in real.clubes for s in jogador.clubes), jogador.nome
    names = [c.nome for c in real.clubes.values()]
    assert not [n for n in names if n.lower().startswith("seleção") or n in {"Brasil", "BRA"}]


def test_convert_keeps_clubs_whose_name_contains_national_words() -> None:
    rows = [
        row("Q2", "Q100", "Club de Regatas Vasco da Gama", "1990", "1992", short="Vasco"),
        row("Q2", "Q110", "Football Club Internazionale Milano", "1995", "1996"),
    ]

    data = Data.from_dict(convert(PLAYERS, rows, {}))

    assert "Q110" in {s.clube for s in player(data, "Edmundo").clubes}


def test_convert_uses_the_end_year_when_the_start_is_unknown() -> None:
    rows = [
        row("Q2", "Q100", "Club de Regatas Vasco da Gama", "1990", "1992", short="Vasco"),
        row("Q2", "Q111", "FC Anji Makhachkala", "0001-01-01T00:00:00Z", "2012-01-01T00:00:00Z"),
    ]

    edmundo = player(Data.from_dict(convert(PLAYERS, rows, {})), "Edmundo")

    assert [(s.clube, s.inicio, s.fim) for s in edmundo.clubes] == [
        ("Q100", 1990, 1992),
        ("Q111", 2012, 2012),
    ]


def test_convert_keeps_the_club_country_with_fixes_first() -> None:
    rows = [
        {**row("Q2", "Q100", "Club de Regatas Vasco da Gama", "1990", "1992"), "country": "Brasil"},
        {**row("Q2", "Q108", "ACF Fiorentina", "1997", "1999"), "country": "Itália"},
        row("Q2", "Q112", "Clube Sem País", "2000", "2001"),
    ]

    data = Data.from_dict(convert(PLAYERS, rows, {"Q108": {"pais": "Itália (Florença)"}}))

    assert data.clubes["Q100"].pais == "Brasil"
    assert data.clubes["Q108"].pais == "Itália (Florença)"
    assert data.clubes["Q112"].pais == "Outros"


def test_team_edition_gives_the_team_stints_without_scoring_them(data) -> None:
    romario = player(data, "Romário")
    given = team_clubs(data, "Flamengo")

    start = judge(data, romario, [], desistiu=False, dados=given)
    done = judge(data, romario, ["Q100", "Q101", "Q104"], desistiu=False, dados=given)

    assert given == {"Q103"}
    assert [s.clube for s in start.slots] == [None, None, "Flamengo", None, "Flamengo", None]
    assert [s.dado for s in start.slots] == [False, False, True, False, True, False]
    assert start.achados == 0 and start.total == 3 and not start.over
    assert done.solved and done.achados == 3


def test_guessing_a_given_club_is_not_an_error(data) -> None:
    verdict = judge(data, player(data, "Edmundo"), ["Q103"], desistiu=False, dados={"Q103"})

    assert verdict.erros == [] and verdict.achados == 0


def test_convert_swaps_a_stint_that_ends_before_it_starts() -> None:
    rows = [row("Q2", "Q113", "Independiente Medellín", "2017", "2015")]

    edmundo = player(Data.from_dict(convert(PLAYERS, rows, {})), "Edmundo")

    assert [(s.inicio, s.fim) for s in edmundo.clubes] == [(2015, 2017)]


def test_convert_prefers_the_known_end_of_duplicate_statements() -> None:
    rows = [
        row("Q2", "Q107", "Sport Club Corinthians Paulista", "2010", "2011"),
        row("Q2", "Q107", "Sport Club Corinthians Paulista", "2010", ""),
    ]

    edmundo = player(Data.from_dict(convert(PLAYERS, rows, {})), "Edmundo")

    assert [(s.inicio, s.fim) for s in edmundo.clubes] == [(2010, 2011)]


def test_real_club_names_are_unique() -> None:
    from collections import Counter

    from geral.games.onde_jogou import load, normalize

    names = Counter(normalize(c.nome) for c in load().clubes.values())

    assert [n for n, k in names.items() if k > 1] == []


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("wing half", "Meia-atacante"),  # Neymar, Robinho, Arrascaeta: never a volante
        ("Winger", "Ponta"),
        ("defesa central", "Zagueiro"),
        ("Attacking midfielder", "Meia"),
        ("ponteiro", "Ponta"),
        ("atacante", "Atacante"),
        ("Lateral (futebol)", "Lateral"),
    ],
)
def test_convert_writes_positions_in_brazilian_portuguese(raw, shown) -> None:
    rows = [row("Q2", "Q100", "Vasco", "1990", "1992", position=raw)]

    assert player(Data.from_dict(convert(PLAYERS, rows, {})), "Edmundo").posicao == shown


ABC_ONLY = {
    "clubes": {
        "Q100": {"nome": "Vasco", "apelidos": ["Vasco da Gama (pt)"], "pais": "Brasil"},
        "Q200": {"nome": "ABC", "apelidos": ["ABC Futebol Clube"], "pais": "Brasil"},
        "Q201": {"nome": "Alecrim", "apelidos": [], "pais": "Brasil"},
        "Q202": {"nome": "América-RN", "apelidos": [], "pais": "Brasil"},
    },
    "jogadores": [
        {
            "wikidata": "Q50",
            "nome": "Alberi",
            "posicao": "Atacante",
            "edicoes": ["abc"],
            "clubes": [
                {"clube": "Q200", "inicio": 1968, "fim": 1975},
                {"clube": "Q100", "inicio": 1976, "fim": 1976},
                {"clube": "Q201", "inicio": 1979, "fim": 1981},
                {"clube": "Q202", "inicio": 1982, "fim": 1983},
            ],
        },
        {  # already in the main file: the main career wins
            "wikidata": "Q2",
            "nome": "Edmundo (pt)",
            "posicao": "Atacante",
            "edicoes": ["abc"],
            "clubes": [{"clube": "Q200", "inicio": 2009, "fim": 2009}],
        },
    ],
}


@pytest.fixture
def merged(data, tmp_path) -> Data:
    import json

    from geral.games.onde_jogou import load

    main, extra = tmp_path / "carreiras.json", tmp_path / "carreiras_pt.json"
    main.write_text(json.dumps(convert(PLAYERS, ROWS, OVERRIDES)), encoding="utf-8")
    extra.write_text(json.dumps(ABC_ONLY), encoding="utf-8")
    return load(main, extra)


def test_load_adds_the_extra_careers_and_keeps_the_main_ones(merged) -> None:
    assert player(merged, "Alberi").edicoes == ("abc",)
    assert player(merged, "Edmundo").edicoes == ()  # the main career, not the extra one
    assert not [p for p in merged.jogadores if p.nome == "Edmundo (pt)"]
    assert merged.clubes["Q100"].nome == "Vasco"
    assert "Vasco da Gama (pt)" in merged.clubes["Q100"].apelidos  # aliases add up
    assert resolve(merged, "alecrim") == "Q201"


def test_load_works_without_the_extra_file(tmp_path) -> None:
    import json

    from geral.games.onde_jogou import load

    main = tmp_path / "carreiras.json"
    main.write_text(json.dumps(convert(PLAYERS, ROWS, OVERRIDES)), encoding="utf-8")

    assert len(load(main, tmp_path / "nada.json").jogadores) == 3


def test_extra_players_play_only_in_their_own_edition(merged) -> None:
    assert "Alberi" in {p.nome for p in pool(merged, "abc", TEAMS)}
    assert "Alberi" not in {p.nome for p in pool(merged, "geral", TEAMS)}
    assert "Alberi" not in {p.nome for p in pool(merged, "vasco", TEAMS)}


def test_real_abc_edition_has_a_month_of_players() -> None:
    from geral.games.onde_jogou import load
    from geral.teams import load_teams

    names = {slug: team.name for slug, team in load_teams().items()}

    assert len(pool(load(), "abc", names)) >= 30


def test_real_player_names_are_unique() -> None:
    from collections import Counter

    from geral.games.onde_jogou import load

    names = Counter(j.nome for j in load().jogadores)

    assert [n for n, k in names.items() if k > 1] == []


def test_load_keeps_the_extra_short_name_of_a_known_club(tmp_path) -> None:
    import json

    from geral.games.onde_jogou import load

    main, extra = tmp_path / "carreiras.json", tmp_path / "carreiras_pt.json"
    main.write_text(json.dumps(convert(PLAYERS, ROWS, OVERRIDES)), encoding="utf-8")
    renamed = {"clubes": {"Q105": {"nome": "Verdão", "apelidos": [], "pais": "Brasil"}}}
    extra.write_text(json.dumps({**renamed, "jogadores": []}), encoding="utf-8")

    assert resolve(load(main, extra), "verdao") == "Q105"


def test_resolve_prefers_a_club_name_and_drops_shared_aliases() -> None:
    data = Data.from_dict(
        {
            "clubes": {
                "Q1": {"nome": "Nacional", "apelidos": [], "pais": "Uruguai"},
                "Q2": {"nome": "CD Nacional", "apelidos": ["Nacional"], "pais": "Portugal"},
                "Q3": {"nome": "América-SP", "apelidos": ["América FC"], "pais": "Brasil"},
                "Q4": {"nome": "América-TO", "apelidos": ["América FC"], "pais": "Brasil"},
            },
            "jogadores": [],
        }
    )

    assert resolve(data, "nacional") == "Q1"
    assert resolve(data, "america fc") is None  # which one? not a wrong guess either
    assert resolve(data, "america-to") == "Q4"


def test_real_nautico_edition_has_a_month_of_players() -> None:
    from geral.games.onde_jogou import load
    from geral.teams import load_teams

    names = {slug: team.name for slug, team in load_teams().items()}

    assert len(pool(load(), "nautico", names)) >= 30
