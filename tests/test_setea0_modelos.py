import pytest
from setea0_fake import dados_de_teste

from geral.games.setea0 import dados
from geral.games.setea0.dados import chaves
from geral.games.setea0.modelos import ESQUEMAS, Dados, Jogador

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
        assert edicao["publicado"] is False, slug
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
    with pytest.raises(ValueError, match="x"):
        dados.chaves()
    dados.chaves.cache_clear()


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
    for slug in [*chaves()["edicao"]["abc"]["adversarios"], "america-rn"]:
        assert len(fake.clubes[slug].jogadores) == 18
