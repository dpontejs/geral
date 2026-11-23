"""Paths of a career: marks, risky decisions, arcs, a change of position."""

import dataclasses
import random

import pytest
from test_carreira_motor import entrada

from geral.games.carreira import motor, regras
from geral.games.carreira.codigo import codificar, decodificar, resumir
from geral.games.carreira.dados import PASTA, Condicao, Decisao, Efeito, Marca, Opcao, carregar
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


def _ate_a_decisao(dados, e, alvo: str, resposta=lambda p: 0):
    """Answer until the question `alvo` is pending (or the career ends)."""
    while (carreira := simular(dados, "geral", e)).final is None:
        if carreira.pendente.id == alvo:
            break
        e = e.model_copy(update={"escolhas": [*e.escolhas, resposta(carreira.pendente)]})
    return carreira, e


def _arco(**condicao_passo):
    passo = _decisao(
        "d2",
        Opcao(texto="Seguir", marca="b"),
        Opcao(texto="Parar"),
        condicao=Condicao(requer=("a",), **condicao_passo),
        continua=True,
    )
    return _decisao("d1"), passo


@pytest.mark.parametrize("modo", ["rapida", "completa"])
def test_arco_continua_na_temporada_seguinte(sempre, monkeypatch, modo) -> None:
    monkeypatch.setattr(motor, "MAX_ESCOLHAS", {"rapida": 1, "completa": 1})  # the cap is full
    dados = _dados(*_arco())
    for i in range(10):
        e = _modo(entrada(f"a{i}", dados=dados), modo)
        antes, e = _ate_a_decisao(dados, e, "d1")
        e = e.model_copy(update={"escolhas": [*e.escolhas, 0]})
        depois, _ = _ate_a_decisao(dados, e, "d2", lambda p: 0)

        assert depois.pendente and depois.pendente.id == "d2"
        assert len(depois.temporadas) == len(antes.temporadas) + 1


def test_arco_segue_a_ordem(sempre) -> None:
    dados = _dados(*_arco())
    for i in range(20):
        e = entrada(f"o{i}", dados=dados)
        _, e = _ate_a_decisao(dados, e, "d1")
        sem_marca = e.model_copy(update={"escolhas": [*e.escolhas, 1]})  # no mark: no arc
        carreira, _ = _ate_a_decisao(dados, sem_marca, "d2")
        assert carreira.final and "d2" not in carreira.final.perguntas


def test_arco_que_nao_casa_morre(sempre) -> None:
    for espera, chega in ((2, True), (3, False)):  # two seasons of tries, then the arc dies
        primeiro, passo = _arco(idade_min=20 + espera)
        dados = _dados(dataclasses.replace(primeiro, condicao=Condicao(idade_min=20)), passo)
        for i in range(10):
            e = entrada(f"n{i}", dados=dados)
            antes, e = _ate_a_decisao(dados, e, "d1")
            if antes.final or antes.temporadas[-1].idade != 20:
                continue
            e = e.model_copy(update={"escolhas": [*e.escolhas, 0]})
            carreira, _ = _ate_a_decisao(dados, e, "d2")
            if chega:
                assert carreira.pendente and carreira.temporadas[-1].idade == 22
            else:
                assert carreira.final and "d2" not in carreira.final.perguntas


@pytest.mark.parametrize(("modo", "teto"), [("rapida", 5), ("completa", 8)])
def test_teto_por_modo(sempre, modo, teto) -> None:
    dados = _dados(*(_decisao(f"t{i}", Opcao(texto="a"), Opcao(texto="b")) for i in range(30)))
    for i in range(10):
        carreira, _ = _ate_a_decisao(dados, _modo(entrada(f"t{i}", dados=dados), modo), "-")
        assert len(carreira.final.perguntas) == teto


MEIA = MARCAS | {"v": Marca("v", "Virou meia", "{nome} vira meia", Efeito(posicao="meia"))}


def test_virou_meia_muda_posicao_e_nota() -> None:
    sim = _simulacao(_dados(marcas=MEIA))
    nota, atacante = sim.nota, regras.geral(sim.notas, "atacante")

    sim._marcar("v")

    assert sim.posicao == "meia"
    assert sim.nota == nota + regras.geral(sim.notas, "meia") - atacante


def test_virou_meia_vai_para_o_card(sempre) -> None:
    dados = _dados(_decisao("d1", Opcao(texto="Virar meia", marca="v"), Opcao("Não")), marcas=MEIA)
    e = entrada("v1", dados=dados)
    _, e = _ate_a_decisao(dados, e, "d1")
    e = e.model_copy(update={"escolhas": [*e.escolhas, 0]})
    carreira, e = _ate_a_decisao(dados, e, "-")

    assert carreira.final.posicao == "meia" and carreira.final.marcas == ["Virou meia"]
    resumo = resumir(e, carreira)
    assert resumo.posicao == "meia"
    assert decodificar(codificar(dados.versao, "geral", e, resumo, dados)).entrada == e


def test_final_por_marca(sempre) -> None:
    capitao = {"rotulo": "Capitão eterno", "descricao": "Braçadeira para sempre.", "requer": ["a"]}
    dados = dataclasses.replace(_dados(_decisao()), finais=(capitao, *carregar().finais))
    for resposta, rotulo in ((0, True), (1, False)):
        e = entrada("f1", dados=dados)
        _, e = _ate_a_decisao(dados, e, "d1")
        e = e.model_copy(update={"escolhas": [*e.escolhas, resposta]})
        carreira, _ = _ate_a_decisao(dados, e, "-")
        assert (carreira.final.rotulo == "Capitão eterno") == rotulo


def test_dados_rejeitam_final_com_marca_inexistente(tmp_path) -> None:
    for nome in ("lendas.toml", "mundo.toml", "eventos.toml", "escolhas.toml", "marcas.toml"):
        (tmp_path / nome).write_text((PASTA / nome).read_text(encoding="utf-8"), encoding="utf-8")
    finais = '[[final]]\nrotulo = "X"\ndescricao = "Y"\nrequer = ["nao-existe"]\n'
    (tmp_path / "finais.toml").write_text(finais, encoding="utf-8")

    with pytest.raises(ValueError, match="nao-existe"):
        carregar(tmp_path)


def test_manchete_nao_repete_na_carreira() -> None:
    dados = carregar()
    eventos = {e.id: e for e in dados.eventos}
    for i in range(200):
        rng = random.Random(i)
        e = entrada(f"h{i}", posicao=regras.POSICOES[i % 5])
        while (carreira := simular(dados, "geral", e)).final is None:
            resposta = rng.randrange(len(carreira.pendente.opcoes))
            e = e.model_copy(update={"escolhas": [*e.escolhas, resposta]})
        vistas: dict[str, list[str]] = {}  # principal event -> its headlines so far
        for t in carreira.temporadas:
            if not t.eventos:
                continue
            depois = [x for x in t.eventos if eventos[x].momento == "depois"]
            principal = (depois or t.eventos)[0]
            antes = vistas.setdefault(principal, [])
            if len(antes) < len(eventos[principal].manchetes):
                assert t.manchete not in antes, (f"h{i}", principal, t.manchete)
            antes.append(t.manchete)
