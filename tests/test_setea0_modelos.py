import pytest
from setea0_fake import dados_de_teste

from geral.games.setea0 import dados
from geral.games.setea0.dados import chaves
from geral.games.setea0.modelos import ESQUEMAS, PRIMEIRA_DECADA, Dados, Epoca, Jogador, epocas

ORDEM = ["GOL", "LAT", "ZAG", "MEI", "ATA"]


def test_esquemas_tem_11_vagas_e_1_goleiro():
    for nome, vagas in ESQUEMAS.items():
        assert len(vagas) == 11, nome
        assert vagas.count("GOL") == 1, nome
        indices = [ORDEM.index(v) for v in vagas]
        assert indices == sorted(indices), nome


def test_decadas_das_passagens():
    def jogador(passagens):
        return Jogador(id="Q1", nome="X", posicoes=["MEI"], passagens=passagens, forca=50)

    assert jogador([(1968, 1976), (1981, 1981)]).decadas() == {1960, 1970, 1980}
    assert jogador([]).decadas() == set()


def test_toda_edicao_tem_6_adversarios_e_final():
    edicoes = chaves()["edicao"]
    assert set(edicoes) == {"abc", "nautico", "csa", "flamengo", "vasco", "palmeiras"}
    for slug, edicao in edicoes.items():
        assert len(edicao["adversarios"]) == 6, slug
        assert edicao["final"] not in edicao["adversarios"], slug
        assert slug not in [*edicao["adversarios"], edicao["final"]], slug
        assert edicao["publicado"] is True, slug  # all six live since 2026-11-24 (dev)
        assert chaves()["clube"][slug]["origem"] == "ptwiki", slug


def test_slug_sem_clube_falha(tmp_path, monkeypatch):
    toml = tmp_path / "chaves.toml"
    toml.write_text(
        '[edicao.abc]\nnome = "ABC"\nadversarios = ["x"]\nfinal = "y"\npublicado = false\n'
        '[clube.abc]\nnome = "ABC"\norigem = "ptwiki"\ncategoria = "c"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dados, "CHAVES", toml)
    dados.chaves.cache_clear()
    try:
        with pytest.raises(ValueError, match="x"):
            dados.chaves()
    finally:
        dados.chaves.cache_clear()


def test_todo_clube_tem_wikidata():
    for slug, clube in chaves()["clube"].items():
        assert clube["wikidata"].startswith("Q"), slug


def test_passagem_ao_contrario_nao_vale():
    with pytest.raises(ValueError):
        Jogador(id="Q1", nome="X", posicoes=["MEI"], passagens=[(1990, 1980)], forca=50)


def test_geral_nao_tem_7a0():
    assert "geral" not in chaves()["edicao"]


def test_dados_de_teste_validam():
    fake = dados_de_teste()
    assert Dados.model_validate(fake.model_dump()) == fake
    abc = fake.clubes["abc"].jogadores
    assert sum(1940 in j.decadas() for j in abc) == 3
    for decada in (1970, 1980, 2000, 2010):
        da_decada = [j for j in abc if decada in j.decadas()]
        assert len(da_decada) >= 12
        assert {p for j in da_decada for p in j.posicoes} == {"GOL", "ZAG", "LAT", "MEI", "ATA"}
    assert any(len(j.decadas()) > 1 for j in abc)  # someone shows up in two decades
    for slug in [*chaves()["edicao"]["abc"]["adversarios"], "america-rn"]:
        assert len(fake.clubes[slug].jogadores) == 18


def test_dados_de_teste_com_outra_semente_e_escala():
    forte = dados_de_teste(semente=8, escala=1.2)
    base = dados_de_teste()
    assert forte != base
    media = lambda d: sum(j.forca for j in d.clubes["abc"].jogadores) / 63  # noqa: E731
    assert media(forte) > media(base) * 1.1
    assert all(j.forca <= 99 for j in forte.clubes["abc"].jogadores)


POSICOES = ["GOL", "LAT", "ZAG", "MEI", "ATA"]


def _com_decadas(contagem: dict[int, int], posicoes: list[str] = POSICOES) -> list[Jogador]:
    """`n` players per decade, positions cycled: 5 or more cover every position."""
    return [
        Jogador(
            id=f"Q{d}{i}",
            nome="X",
            posicoes=[posicoes[i % len(posicoes)]],
            passagens=[(d + 1, d + 2)],
            forca=50,
        )
        for d, n in contagem.items()
        for i in range(n)
    ]


def test_epocas_juntam_decadas_ralas():
    abc = _com_decadas({1920: 1, 1940: 1, 1960: 3, 1970: 3, 1980: 7, 1990: 9, 2000: 32, 2010: 110})
    # dev decision 2026-11-24: eras from 1970; the 20s-60s no longer open "anos 20 a 70"
    assert [(e.inicio, e.fim, e.rotulo) for e in epocas(abc)] == [
        (1970, 1980, "anos 70 a 80"),
        (1990, 1990, "anos 90"),
        (2000, 2000, "anos 2000"),
        (2010, 2010, "anos 2010"),
    ]


def test_epocas_comecam_em_1970():
    antes = _com_decadas({1950: 20, 1960: 20})
    virada = Jogador(id="Qv", nome="V", posicoes=["MEI"], passagens=[(1965, 1971)], forca=50)
    depois = _com_decadas({1970: 7, 1980: 8})
    eras = epocas([*antes, virada, *depois])
    assert PRIMEIRA_DECADA == 1970
    assert [(e.inicio, e.fim) for e in eras] == [(1970, 1970), (1980, 1980)]
    assert eras[0].contem(virada)  # played in the 70s too: counts there
    assert not any(e.contem(j) for e in eras for j in antes)
    assert epocas(antes) == []
    assert [e.inicio for e in epocas(antes, desde=1950)] == [1950, 1960]


def test_epoca_so_fecha_com_as_5_posicoes():
    linha = ["LAT", "ZAG", "MEI", "ATA"]
    elenco = [
        *_com_decadas({1970: 12, 1980: 10}, linha),  # plenty of players, no keeper
        *_com_decadas({1990: 1}, ["GOL"]),
        *_com_decadas({2000: 10}),
        *_com_decadas({2010: 3}, linha),  # a keeper-less tail joins the last era
    ]
    eras = epocas(elenco)
    assert [(e.inicio, e.fim) for e in eras] == [(1970, 1990), (2000, 2010)]
    for era in eras:
        assert {p for j in elenco if era.contem(j) for p in j.posicoes} == set(POSICOES)


def test_clube_que_nunca_tem_goleiro_fica_com_uma_epoca():
    elenco = _com_decadas({1970: 20, 1980: 20, 1990: 20}, ["LAT", "ZAG", "MEI", "ATA"])
    assert [(e.inicio, e.fim) for e in epocas(elenco)] == [(1970, 1990)]


def test_sobra_rala_no_fim_entra_na_ultima_epoca():
    assert [(e.inicio, e.fim) for e in epocas(_com_decadas({1990: 12, 2000: 9, 2010: 2}))] == [
        (1990, 1990),
        (2000, 2010),
    ]


def test_epoca_contem_o_jogador_de_qualquer_decada_dela():
    epoca = Epoca(inicio=1960, fim=1980, rotulo="anos 60 a 80")
    assert epoca.contem(_com_decadas({1970: 1})[0])
    assert not epoca.contem(_com_decadas({1990: 1})[0])


def test_escala_vale_para_todos_os_clubes():
    base, forte = dados_de_teste(), dados_de_teste(escala=1.2)
    for slug in base.clubes:
        antes = sum(j.forca for j in base.clubes[slug].jogadores)
        depois = sum(j.forca for j in forte.clubes[slug].jogadores)
        assert depois > antes, slug


def test_epoca_e_imutavel_e_serve_de_chave():
    a = Epoca(inicio=1960, fim=1980, rotulo="anos 60 a 80")
    b = Epoca(inicio=1960, fim=1980, rotulo="anos 60 a 80")
    assert {a: 1}[b] == 1
    with pytest.raises(ValueError):
        a.inicio = 1970
