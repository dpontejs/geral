"""Paths of a career: marks, risky decisions, arcs, a change of position."""

import dataclasses

import pytest
from test_carreira_motor import entrada

from geral.games.carreira import motor
from geral.games.carreira.dados import Condicao, Decisao, Efeito, Marca, Opcao, carregar
from geral.games.carreira.draft import JogadaInvalida, montar, oferta
from geral.games.carreira.motor import _Simulacao, chance_de, clube_inicial, simular

MARCAS = {
    "a": Marca("a", "Aço", "{nome} vira aço", Efeito(teto=1)),
    "b": Marca("b", "Barro", "{nome} vira barro"),
    "x": Marca("x", "Xis", "{nome} vira xis", Efeito(nota=5)),
}


def _decisao(id_="d1", *opcoes: Opcao, condicao=None, continua=False) -> Decisao:
    condicao = condicao or Condicao()
    opcoes = opcoes or (Opcao(texto="Sim", marca="a"), Opcao(texto="Não"))
    return Decisao(id_, "E agora, {nome}?", opcoes, condicao=condicao, continua=continua)


def _dados(*decisoes: Decisao, marcas=MARCAS):
    return dataclasses.replace(carregar(), decisoes=decisoes, marcas=marcas)


@pytest.fixture
def sempre(monkeypatch):
    """A question every season it can come."""
    monkeypatch.setattr(motor, "CHANCE_ESCOLHA", 1.0)


def _modo(e, modo):
    return e.model_copy(update={"modo": modo})


def _responder(dados, e, *respostas):
    return simular(dados, "geral", e.model_copy(update={"escolhas": list(respostas)}))


def _textos(carreira) -> list[str]:
    return [m for t in carreira.temporadas for m in t.marcas]


def test_marca_gravada_conforme_o_resultado(sempre) -> None:
    arriscada = Opcao(texto="Arriscar", chance=50, marca="a", marca_fracasso="b")
    dados = _dados(_decisao("d1", arriscada, Opcao(texto="Não")))
    vistas = set()
    for i in range(60):
        e = entrada(f"m{i}", dados=dados)
        assert simular(dados, "geral", e).pendente.id == "d1"
        textos = _textos(_responder(dados, e, 0))
        assert len(textos) == 1 and textos[0] in ("Zé vira aço", "Zé vira barro")
        vistas.add(textos[0])
    assert len(vistas) == 2

    certa = _dados(_decisao("d1", Opcao(texto="Sim", marca="a", marca_fracasso="b"), Opcao("N")))
    for i in range(10):
        assert _textos(_responder(certa, entrada(f"m{i}", dados=certa), 0)) == ["Zé vira aço"]


def _simulacao(dados) -> _Simulacao:
    e = entrada("u1", dados=dados)
    notas = montar(oferta(dados, "geral", e.semente_draft, e.craque.clube), e.roubos)
    return _Simulacao(dados, e, notas, clube_inicial(dados, "geral", e.craque.clube))


def test_marca_repetida_aplica_efeito_uma_vez() -> None:
    sim = _simulacao(_dados())
    nota = sim.nota

    sim._marcar("x")
    sim._marcar("x")

    assert sim.nota == nota + 5 and "x" in sim.historico
    assert sim.marcas_novas == ["Zé vira xis"]


def test_decisao_com_risco_mostra_chance_e_arriscada(sempre) -> None:
    arriscada = Opcao(texto="Arriscar", chance=20, sucesso=Efeito(teto=4), marca="a")
    dados = _dados(_decisao("d1", arriscada, Opcao(texto="Não")))
    e = entrada("r1", dados=dados)
    notas = montar(oferta(dados, "geral", e.semente_draft, e.craque.clube), e.roubos)

    pendente = simular(dados, "geral", e).pendente

    assert len(pendente.info) == 2
    assert pendente.info[0].chance == chance_de(arriscada, notas) and pendente.info[0].arriscada
    assert "Aço" in pendente.info[0].efeitos
    assert pendente.info[1].chance is None and not pendente.info[1].arriscada


def test_decisao_de_mercado_sem_risco_nao_mostra_info(sempre) -> None:
    dados = dataclasses.replace(carregar(), decisoes=carregar().decisoes[:1])
    for i in range(200):
        pendente = simular(dados, "geral", entrada(f"q{i}", melhor=True, dados=dados)).pendente
        if pendente and pendente.tipo == "decisao":
            assert pendente.info == []
            return
    pytest.fail("nenhuma decisão de mercado em 200 sementes")


def test_resposta_fora_das_opcoes_e_invalida(sempre) -> None:
    dados = _dados(_decisao())

    with pytest.raises(JogadaInvalida):
        _responder(dados, entrada("f1", dados=dados), 5)


def test_decisao_sem_clube_nao_segura_o_mercado(sempre) -> None:
    dados = _dados(_decisao(condicao=Condicao(idade_min=22)))
    for i in range(200):
        e = _modo(entrada(f"k{i}", dados=dados), "completa")
        while (antes := simular(dados, "geral", e)).pendente and antes.pendente.id != "d1":
            e = e.model_copy(update={"escolhas": [*e.escolhas, 0]})
        if antes.pendente is None:
            continue
        depois = _responder(dados, e, *e.escolhas, 0)
        if depois.pendente and depois.pendente.tipo == "mercado":
            assert len(depois.temporadas) == len(antes.temporadas)  # the decision's winter
            return
    pytest.fail("decisão 'ficar' nunca deixou o mercado rodar em 200 sementes")
