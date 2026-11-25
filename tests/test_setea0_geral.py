"""The 7a0 da Geral: the die draws a club and an era among the published editions (dev,
2026-11-24) and the mixed team plays the grandes."""

import pytest
from setea0_fake import DUPLAS, dados_geral_de_teste
from setea0_times import gulosas

from geral.games.setea0 import motor
from geral.games.setea0.dados import chaves
from geral.games.setea0.modelos import Escolha, JogadaInvalida

DADOS = dados_geral_de_teste()
GERAL = motor.GERAL
SEMENTES = [f"g{i}" for i in range(60)]


def test_grandes_da_geral_no_chaves():
    grandes = chaves()["geral"]["grandes"]
    assert set(grandes) == {
        "corinthians",
        "santos",
        "sao-paulo",
        "gremio",
        "internacional",
        "cruzeiro",
        "atletico-mg",
    }
    for slug in grandes:
        assert chaves()["clube"][slug]["origem"] == "velha", slug


def test_geral_sorteia_clube_e_epoca_entre_os_publicados():
    publicados = {s for s, e in chaves()["edicao"].items() if e["publicado"]}
    assert set(motor.clubes_da_geral(DADOS)) == publicados
    vistos = set()
    for semente in SEMENTES:
        r = motor.oferta(DADOS, GERAL, semente, 0, 0)
        assert r.epoca.clube in publicados
        do_clube = {j.id for j in DADOS.clubes[r.epoca.clube].jogadores}
        for j in r.jogadores:
            assert j.id in do_clube
            assert any(r.epoca.inicio <= d <= r.epoca.fim for d in j.decadas())
        assert {p for j in r.jogadores for p in j.posicoes} == {"GOL", "LAT", "ZAG", "MEI", "ATA"}
        vistos.add(r.epoca.clube)
    assert vistos == publicados  # every club comes up


def test_epocas_da_geral_sao_as_dos_clubes():
    eras = motor.epocas_do_clube(DADOS, GERAL)
    for slug in motor.clubes_da_geral(DADOS):
        do_clube = [(e.inicio, e.fim, e.rotulo) for e in motor.epocas_do_clube(DADOS, slug)]
        assert [(e.inicio, e.fim, e.rotulo) for e in eras if e.clube == slug] == do_clube
    assert all(e.clube is None for e in motor.epocas_do_clube(DADOS, "abc"))


def test_clube_despublicado_sai_da_geral(monkeypatch):
    monkeypatch.setitem(chaves()["edicao"]["csa"], "publicado", False)
    assert "csa" not in motor.clubes_da_geral(DADOS)
    for semente in SEMENTES:
        assert motor.oferta(DADOS, GERAL, semente, 0, 0).epoca.clube != "csa"


def _semente_com_a_dupla(id_: str) -> tuple[str, list[int]]:
    """A seed whose draw (no rerolls) offers `id_` in two rounds: (seed, those rounds)."""
    for i in range(3000):
        semente = f"d{i}"
        rodadas = [
            r
            for r in range(11)
            if any(j.id == id_ for j in motor.oferta(DADOS, GERAL, semente, r, 0).jogadores)
        ]
        if len(rodadas) >= 2:
            return semente, rodadas[:2]
    raise AssertionError(f"{id_} never offered twice")


def test_jogador_de_dois_clubes_aparece_em_cada_um_mas_entra_uma_vez():
    id_, um, outro, _ = DUPLAS[0]
    assert id_ in {j.id for j in DADOS.clubes[um].jogadores}
    assert id_ in {j.id for j in DADOS.clubes[outro].jogadores}
    semente, rodadas = _semente_com_a_dupla(id_)
    forjadas = [
        e.model_copy(update={"jogador": id_}) if e.rodada in rodadas else e
        for e in gulosas(DADOS, GERAL, semente)
    ]
    with pytest.raises(JogadaInvalida, match="já está no time"):
        motor.escalar(DADOS, GERAL, semente, "classico", "4-4-2", forjadas)


def test_adversarios_da_geral_sao_os_grandes_do_mais_fraco_ao_mais_forte():
    chave = motor.adversarios(DADOS, GERAL)
    assert sorted(chave) == sorted(chaves()["geral"]["grandes"]) and len(chave) == 7
    refs = [motor.referencia(DADOS, s) for s in chave]
    assert refs == sorted(refs)  # the final is the strongest of the seven
    assert chave != chaves()["geral"]["grandes"]  # sorted by strength, not by the file


def test_geral_jogos_1_a_6_em_ordem_crescente_e_final_ao_menos_tao_forte():
    forcas = [motor.forca_do_adversario(DADOS, GERAL, n) for n in range(1, 8)]
    assert forcas[:6] == sorted(forcas[:6]) and len(set(forcas[:6])) == 6
    assert forcas[6] >= forcas[5]


def test_referencia_da_geral_e_a_media_dos_clubes():
    clubes = motor.clubes_da_geral(DADOS)
    media = sum(motor.referencia(DADOS, s) for s in clubes) / len(clubes)
    assert motor.referencia(DADOS, GERAL) == pytest.approx(media)


def test_campanha_da_geral_e_deterministica():
    es = gulosas(DADOS, GERAL, "igual")
    a = motor.campanha_motor(DADOS, GERAL, "igual", "classico", "4-4-2", es)
    b = motor.campanha_motor(DADOS, GERAL, "igual", "classico", "4-4-2", es)
    assert a == b and a.edicao == GERAL
    assert all(e.epoca.clube for e in a.escalacao)
    grandes = set(chaves()["geral"]["grandes"])
    assert {p.adversario for p in a.partidas} <= grandes


def test_escolha_fora_da_oferta_da_geral_e_invalida():
    es = gulosas(DADOS, GERAL, "x")
    es[0] = Escolha(rodada=0, troca=0, jogador="Qninguem", vaga=es[0].vaga)
    with pytest.raises(JogadaInvalida):
        motor.escalar(DADOS, GERAL, "x", "classico", "4-4-2", es)
